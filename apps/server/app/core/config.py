"""
@description 配置管理模块
@responsibility 加载和验证 config.yaml，支持环境变量覆盖
"""

import os
import sys
from errno import EBUSY, EXDEV
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class P115Config(BaseModel):
    """115 网盘专属配置"""

    cookies: str = Field(..., description="115 账号 Cookies 字符串")


class CloudConfig(BaseModel):
    """云盘配置，按服务商分子块"""

    # 离线任务监控轮询间隔，与具体云盘服务商无关
    poll_interval_min: int = Field(60, description="离线任务监控轮询间隔最小值（秒）")
    poll_interval_max: int = Field(80, description="离线任务监控轮询间隔最大值（秒）")
    p115: P115Config = Field(..., description="115 网盘配置")

    @model_validator(mode="after")
    def validate_poll_interval(self):
        if self.poll_interval_min <= 0 or self.poll_interval_max <= 0:
            raise ValueError("轮询间隔必须大于 0")
        if self.poll_interval_min > self.poll_interval_max:
            raise ValueError("最小轮询间隔不能大于最大轮询间隔")
        return self


class LibraryConfig(BaseModel):
    """媒体库配置"""

    name: str = Field(..., description="媒体库名称")
    download_path: str = Field(..., description="下载目录路径")
    target_path: str = Field(..., description="目标目录路径")
    type: str = Field(..., description="媒体库类型（system/xx-{studio}）")
    min_transfer_size: int = Field(
        default=0, description="最小传输大小（MB），<=0 使用默认值"
    )


class XXConfig(BaseModel):
    """成人片库（xx）配置"""

    remove_keywords: list[str] = Field(
        default_factory=list, description="需要移除的关键词列表"
    )


class MediaConfig(BaseModel):
    """媒体相关配置"""

    min_transfer_size: int = Field(..., description="默认最小传输大小（MB）")
    libraries: list[LibraryConfig] = Field(..., description="媒体库列表")
    video_formats: list[str] = Field(..., description="支持的视频格式列表")
    xx: XXConfig = Field(default_factory=XXConfig, description="成人片库配置")


class DatabaseConfig(BaseModel):
    """数据库配置"""

    url: str = Field(
        "sqlite+aiosqlite:///./db/data.db",
        description="数据库连接 URL（支持环境变量 DATABASE_URL 覆盖）",
    )


class Config(BaseModel):
    """全局配置"""

    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig, description="数据库配置"
    )
    cloud: CloudConfig = Field(..., description="云盘账户配置")
    media: MediaConfig = Field(..., description="媒体配置")

    @model_validator(mode='before')
    @classmethod
    def _support_legacy_p115_key(cls, values):
        """向后兼容：支持旧 YAML 中多种旧结构的自动迁移"""
        if not isinstance(values, dict):
            return values
        # 兼容旧 YAML: p115: {cookies, ...} -> cloud: {p115: {cookies, ...}}
        if 'p115' in values and 'cloud' not in values:
            values['cloud'] = {'p115': values.pop('p115')}
        # 兼容旧扁平 cloud 结构: cloud: {cookies, rotation_training_interval_*}
        if 'cloud' in values and isinstance(values['cloud'], dict):
            cloud = values['cloud']
            if 'cookies' in cloud and 'p115' not in cloud:
                # poll_interval 字段提升到 cloud 层
                new_cloud = {
                    'poll_interval_min': cloud.get(
                        'poll_interval_min',
                        cloud.get('rotation_training_interval_min', 60),
                    ),
                    'poll_interval_max': cloud.get(
                        'poll_interval_max',
                        cloud.get('rotation_training_interval_max', 80),
                    ),
                    'p115': {
                        'cookies': cloud.get('cookies'),
                    },
                }
                values['cloud'] = new_cloud
            # 兼容旧 cloud.p115.poll_interval_* 结构，将 poll_interval 提升到 cloud 层
            elif 'p115' in cloud and isinstance(cloud.get('p115'), dict):
                p115 = cloud['p115']
                if 'poll_interval_min' in p115 and 'poll_interval_min' not in cloud:
                    cloud['poll_interval_min'] = p115.pop('poll_interval_min')
                if 'poll_interval_max' in p115 and 'poll_interval_max' not in cloud:
                    cloud['poll_interval_max'] = p115.pop('poll_interval_max')
        return values


def get_config_path() -> Path:
    """获取配置文件路径"""
    # 优先使用 CONFIG_PATH 环境变量，否则使用项目根目录的 config.yaml
    if config_path_str := os.environ.get("CONFIG_PATH"):
        return Path(config_path_str)
    return Path(__file__).parent.parent.parent / "config.yaml"


def load_config() -> Config:
    """加载配置文件并应用环境变量覆盖"""
    config_path = get_config_path()

    # Docker 文件挂载陷阱：宿主机不存在该文件时，Docker 会自动创建同名
    # 目录挂进容器，导致 open() 抛 IsADirectoryError；提前给出可读错误
    if config_path.is_dir():
        print(f"错误: 配置路径是一个目录而非文件: {config_path}")
        print("常见原因: Docker 挂载时宿主机上 config.yaml 不存在，"
              "Docker 自动创建了同名空目录。")
        print(f"修复: 在宿主机上删除该目录，创建真正的配置文件后重启：")
        print(f"  rm -rf {config_path}")
        print(f"  cp config.example.yaml {config_path}  # 然后编辑填入实际配置")
        sys.exit(1)

    # 配置文件不存在时生成模板并退出
    if not config_path.is_file():
        _generate_config_template(config_path)
        print(f"错误: 配置文件不存在: {config_path}")
        print(f"已生成配置模板: {config_path.parent / 'config.example.yaml'}")
        sys.exit(1)

    # 加载 YAML 配置
    with open(config_path, encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # 解析为 Pydantic 模型（验证数据结构）
    config = Config(**config_data)

    # 应用环境变量覆盖
    if cookies := os.environ.get("P115_COOKIES"):
        config.cloud.p115.cookies = cookies

    return config


def save_config(config: Config) -> None:
    """Persist Web UI changes, including to Docker bind-mounted config files."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    serialized_config = yaml.safe_dump(
        config.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=config_path.parent, delete=False
    ) as temp_file:
        temp_file.write(serialized_config)
        temp_path = Path(temp_file.name)
    try:
        temp_path.replace(config_path)
    except OSError as exc:
        if exc.errno not in {EBUSY, EXDEV}:
            raise
        # A file mounted from the Docker host cannot be replaced with rename(2),
        # but it can be updated in place when the mount is read-write.
        config_path.write_text(serialized_config, encoding="utf-8")
        temp_path.unlink(missing_ok=True)


def _generate_config_template(config_path: Path) -> None:
    """生成配置模板文件"""
    template_path = config_path.parent / "config.example.yaml"

    if template_path.exists():
        return

    template_content = """# 数据库配置
database:
  # 数据库连接 URL，支持 SQLite / PostgreSQL 等
  # 环境变量 DATABASE_URL 可覆盖此配置
  url: "sqlite+aiosqlite:///./db/data.db"

# 云盘相关配置
cloud:
  # 离线任务监控轮询间隔最小值（秒），与具体云盘服务商无关
  poll_interval_min: 60
  # 离线任务监控轮询间隔最大值（秒），与具体云盘服务商无关
  poll_interval_max: 80
  # 115 网盘配置
  p115:
    # 账号 Cookies（从浏览器开发者工具中获取）
    cookies: "UID=your_uid; CID=your_cid; SEID=your_seid; KID=your_kid"

# 媒体相关配置
media:
  # 默认文件大小阈值（MB），大于此大小的视频文件才会被移动
  min_transfer_size: 200
  # 媒体库列表配置
  libraries:
    # 下载地址和下载完成后移动文件的目标目录映射
    - name: "测试"
      download_path: "/云下载/测试/下载" # 离线下载文件的存放目录
      target_path: "/云下载/测试/目标" # 下载完成后移动文件的目标目录
      min_transfer_size: 100 # 覆盖默认的最小传输大小（MB），小于等于0表示使用默认值
      # 媒体库类型，决定了如何处理下载完成的视频文件，目前支持以下类型：
      # system：表示媒体服务器创建的可搜刮媒体库，不需要对其进行特殊处理，直接将视频文件移动到目标目录即可
      # xx-片商：标识成人片库，xx表示为成人片库，我们要对其进行特殊处理（重命名等操作），片商表示成人片库的片商名称
      type: "system"
  # xx库配置，xx表示成人片库，我们需要对其进行特殊处理（重命名等操作）
  xx:
    # 需要移除视频文件名中的哪些关键词
    remove_keywords: ["hhd800.com@", "_X1080X", "[98t.tv]", "_60FPS", "-4k"]

  # 视频文件格式列表，只有这些格式的视频文件才会被移动
  video_formats:
    [
      "mp4",
      "mkv",
      "ts",
      "iso",
      "rmvb",
      "avi",
      "mov",
      "mpeg",
      "mpg",
      "wmv",
      "3gp",
      "asf",
      "m4v",
      "flv",
      "m2ts",
      "tp",
      "f4v",
    ]
"""

    with open(template_path, "w", encoding="utf-8") as f:
        f.write(template_content)
