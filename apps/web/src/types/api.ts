// MediaBridge API 类型定义

/** 统一 API 响应格式 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}

/**
 * 任务状态常量与判定函数。
 * 云端契约（与后端 monitor.py 一致）：2=完成，负数（如 -1）=失败，其余（0/1 等）=进行中；
 * 后端对 115 原始状态值透传，负数语义只在 UI 判定层归一化。
 */
export const TASK_STATUS = {
  /** 进行中（代表值；0、1 等非负且非完成的状态均为进行中） */
  PENDING: 0,
  /** 完成 */
  COMPLETED: 2,
} as const

/** 云端任务状态原始值：2=完成，负数=失败，其余=进行中 */
export type TaskStatus = number

/** 判断任务是否失败：任何负数状态（如 -1、-2）都表示失败 */
export function isTaskFailed(status: number): boolean {
  return status < 0
}

/** 判断任务是否已完成（status === 2） */
export function isTaskCompleted(status: number): boolean {
  return status === TASK_STATUS.COMPLETED
}

/** 判断任务是否进行中（非完成且非失败，含 0/1 等状态） */
export function isTaskPending(status: number): boolean {
  return !isTaskCompleted(status) && !isTaskFailed(status)
}

/** 整理记录状态枚举 */
export const ORGANIZE_STATUS = {
  SUCCESS: 'success',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const

export type OrganizeStatus = (typeof ORGANIZE_STATUS)[keyof typeof ORGANIZE_STATUS]

/** 添加任务请求体 */
export interface AddTaskRequest {
  /** 磁力链接 */
  magnet: string
  /** 媒体库名称 */
  library_name: string
  /** 任务名称（可选） */
  name?: string
}

/** 任务列表项 - 匹配后端返回的实际字段 */
export interface TaskItem {
  /** 任务 ID (哈希字符串) */
  task_id: string
  /** 任务名称 */
  name: string
  /** 任务状态: 2=完成, 负数=失败(如 -1), 其余=进行中（云端原始值透传） */
  status: TaskStatus
  /** 下载进度（百分比） */
  progress: number
  /** 添加时间 */
  add_time: string
  /** 本地整理失败原因（合并自数据库记录，可能为空） */
  error_message?: string | null
}

/** 任务列表响应 */
export interface TaskListResponse {
  tasks: TaskItem[]
  total: number
}

/** 任务详情响应（扩展任务列表项） */
export type TaskDetailResponse = TaskItem

/** 整理记录项 */
export interface OrganizeRecordItem {
  /** 记录 ID */
  id: number
  /** 原始文件名 */
  original_name: string
  /** 整理后文件名 */
  organized_name: string
  /** 源路径 */
  source_path: string
  /** 目标路径 */
  target_path: string
  /** 整理状态 */
  status: OrganizeStatus
  /** 错误信息（失败时） */
  error_message: string | null
  /** 整理时间 ISO 字符串 */
  created_at: string
}

/** 整理记录列表响应 */
export interface OrganizeRecordsResponse {
  records: OrganizeRecordItem[]
  total: number
  page: number
  page_size: number
}

/** 115网盘配置 */
export interface P115Config {
  /** 轮询最小间隔（秒） */
  poll_interval_min: number
  /** 轮询最大间隔（秒） */
  poll_interval_max: number
}

/** 媒体库项 */
export interface LibraryItem {
  /** 媒体库名称 */
  name: string
  /** 下载目录路径 */
  download_path: string
  /** 目标目录路径 */
  target_path: string
  /** 媒体库类型 */
  type: string
  /** 最小传输大小（MB） */
  min_transfer_size: number
}

/** XX类型配置（成人影片） */
export interface XXConfig {
  /** 需清理的关键词列表 */
  remove_keywords: string[]
}

/** 媒体配置 */
export interface MediaConfig {
  min_transfer_size: number
  video_formats: string[]
  libraries: LibraryItem[]
  xx: XXConfig
}

/** 系统配置响应 */
export interface ConfigResponse {
  p115: P115Config
  media: MediaConfig
}

/** 更新配置请求体 - 支持所有媒体配置字段 */
export interface UpdateConfigRequest {
  p115?: Partial<P115Config>
  media?: {
    /** 最小传输大小（MB） */
    min_transfer_size?: number
    /** 支持的视频格式列表 */
    video_formats?: string[]
    /** 媒体库列表 */
    libraries?: LibraryItem[]
    /** XX类型配置 */
    xx?: Partial<XXConfig>
  }
}

/** 系统状态响应 */
export interface StatusResponse {
  /** 监控是否运行中 */
  monitor_running: boolean
  /** 活跃任务数量 */
  active_tasks: number
  /** 最后检查时间 ISO 字符串（可能为 null） */
  last_check_time: string | null
}
