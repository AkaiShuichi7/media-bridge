// 设置页面 - 115 轮询配置、媒体配置、媒体库、清理规则与访问令牌
// 独立卡片已抽出：访问令牌（AccessTokensCard）、系统状态（SystemStatusCard）、
// 通用字符串列表编辑（StringListCard，视频格式与清理关键词共用）；本页只保留
// 表单状态、媒体库编辑与保存编排
import { useState, useEffect } from 'react'
import { Loader2, Save, Film, Clock, FolderOpen, Plus, Pencil, Trash2, Tag } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { PageContainer } from '@/components/shared/PageContainer'
import { AccessTokensCard } from '@/components/settings/AccessTokensCard'
import { SystemStatusCard } from '@/components/settings/SystemStatusCard'
import { StringListCard } from '@/components/settings/StringListCard'
import { useConfig, useUpdateConfig, useStatus } from '@/hooks/queries'
import type { UpdateConfigRequest, LibraryItem } from '@/types/api'

interface LibraryDialogState {
  open: boolean
  mode: 'add' | 'edit'
  editingIndex: number
  form: LibraryItem
}

/** 媒体库删除/覆盖的二次确认状态（沿用原 ConfirmDialog 样式化对话框） */
interface ConfirmDialogState {
  open: boolean
  type: 'delete' | 'edit' | 'add'
  title: string
  description: string
  confirmText: string
  onConfirm: () => void
}

const INITIAL_CONFIRM: ConfirmDialogState = {
  open: false,
  type: 'delete',
  title: '',
  description: '',
  confirmText: '',
  onConfirm: () => {},
}

const EMPTY_LIBRARY: LibraryItem = {
  name: '',
  download_path: '',
  target_path: '',
  type: 'system',
  min_transfer_size: 0,
}

export default function Settings() {
  const { data: configData, isLoading: configLoading } = useConfig()
  const { data: statusData } = useStatus()
  const updateConfig = useUpdateConfig()

  const [formData, setFormData] = useState<UpdateConfigRequest>({})
  const [isDirty, setIsDirty] = useState(false)

  const [videoFormats, setVideoFormats] = useState<string[]>([])
  const [libraries, setLibraries] = useState<LibraryItem[]>([])
  const [removeKeywords, setRemoveKeywords] = useState<string[]>([])

  const [libraryDialog, setLibraryDialog] = useState<LibraryDialogState>({
    open: false,
    mode: 'add',
    editingIndex: -1,
    form: { ...EMPTY_LIBRARY },
  })

  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState>(INITIAL_CONFIRM)

  useEffect(() => {
    if (configData) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 配置查询结果需同步到可编辑表单的本地状态。
      setFormData({
        p115: {
          poll_interval_min: configData.p115.poll_interval_min,
          poll_interval_max: configData.p115.poll_interval_max,
        },
        media: {
          min_transfer_size: configData.media.min_transfer_size,
        },
      })
      setVideoFormats([...configData.media.video_formats])
      setLibraries([...configData.media.libraries])
      setRemoveKeywords([...configData.media.xx.remove_keywords])
    }
  }, [configData])

  const handleInputChange = (section: 'p115' | 'media', field: string, value: number) => {
    setFormData((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] as object || {}),
        [field]: value,
      },
    }))
    setIsDirty(true)
  }

  const handleSave = async () => {
    const updateData: UpdateConfigRequest = {
      p115: formData.p115,
      media: {
        min_transfer_size: formData.media?.min_transfer_size,
        video_formats: videoFormats,
        libraries: libraries,
        xx: {
          remove_keywords: removeKeywords,
        },
      },
    }
    await updateConfig.mutateAsync(updateData)
    setIsDirty(false)
  }

  /** 打开媒体库添加/编辑对话框 */
  const openLibraryDialog = (mode: 'add' | 'edit', index?: number) => {
    if (mode === 'edit' && index !== undefined && index >= 0) {
      setLibraryDialog({ open: true, mode, editingIndex: index, form: { ...libraries[index] } })
    } else {
      setLibraryDialog({ open: true, mode, editingIndex: -1, form: { ...EMPTY_LIBRARY } })
    }
  }

  /** 保存媒体库：重名走覆盖确认，其余直接写入并标记 dirty */
  const handleLibrarySave = () => {
    const { form, mode, editingIndex } = libraryDialog
    if (!form.name.trim() || !form.download_path.trim() || !form.target_path.trim()) {
      return
    }

    const lib: LibraryItem = {
      name: form.name.trim(),
      download_path: form.download_path.trim(),
      target_path: form.target_path.trim(),
      type: form.type.trim() || 'system',
      min_transfer_size: form.min_transfer_size || 0,
    }

    const closeConfirm = () => setConfirmDialog((prev) => ({ ...prev, open: false }))

    if (mode === 'add') {
      const existingIndex = libraries.findIndex((l) => l.name === lib.name)
      if (existingIndex >= 0) {
        // 重名 → 样式化对话框二次确认后覆盖
        setConfirmDialog({
          open: true,
          type: 'add',
          title: '媒体库已存在',
          description: `媒体库 "${lib.name}" 已存在，是否仍要添加？`,
          confirmText: '仍要添加',
          onConfirm: () => {
            const newLibraries = [...libraries]
            newLibraries[existingIndex] = lib
            setLibraries(newLibraries)
            setIsDirty(true)
            closeConfirm()
            setLibraryDialog((prev) => ({ ...prev, open: false }))
          },
        })
        return
      }
      setLibraries([...libraries, lib])
    } else {
      const newLibraries = [...libraries]
      newLibraries[editingIndex] = lib
      setLibraries(newLibraries)
    }
    setIsDirty(true)
    setLibraryDialog((prev) => ({ ...prev, open: false }))
  }

  const confirmDeleteLibrary = (index: number) => {
    const lib = libraries[index]
    setConfirmDialog({
      open: true,
      type: 'delete',
      title: '删除媒体库',
      description: `确定要删除媒体库 "${lib.name}" 吗？此操作可能会影响文件整理功能。`,
      confirmText: '确认删除',
      onConfirm: () => {
        setLibraries(libraries.filter((_, i) => i !== index))
        setIsDirty(true)
        setConfirmDialog((prev) => ({ ...prev, open: false }))
      },
    })
  }

  if (configLoading) {
    return (
      <PageContainer>
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-40 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      </PageContainer>
    )
  }

  if (!configData) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64 text-muted-foreground">
          加载配置失败
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <div className="space-y-6">
        <AccessTokensCard />
        <SystemStatusCard statusData={statusData} />

        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              <CardTitle>115 网盘配置</CardTitle>
            </div>
            <CardDescription>离线下载监控轮询间隔设置</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="minInterval">最小轮询间隔（秒）</Label>
                <Input
                  id="minInterval"
                  type="number"
                  min={10}
                  max={300}
                  value={formData.p115?.poll_interval_min || ''}
                  onChange={(e) => handleInputChange('p115', 'poll_interval_min', parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="maxInterval">最大轮询间隔（秒）</Label>
                <Input
                  id="maxInterval"
                  type="number"
                  min={10}
                  max={600}
                  value={formData.p115?.poll_interval_max || ''}
                  onChange={(e) => handleInputChange('p115', 'poll_interval_max', parseInt(e.target.value) || 0)}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Film className="h-5 w-5" />
              <CardTitle>媒体配置</CardTitle>
            </div>
            <CardDescription>视频文件处理相关设置</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="minTransferSize">最小传输大小（MB）</Label>
              <Input
                id="minTransferSize"
                type="number"
                min={0}
                max={10000}
                value={formData.media?.min_transfer_size || ''}
                onChange={(e) => handleInputChange('media', 'min_transfer_size', parseInt(e.target.value) || 0)}
              />
              <p className="text-xs text-muted-foreground">小于此大小的视频文件将不会被自动整理</p>
            </div>
            <div className="space-y-2">
              <Label>支持的视频格式</Label>
              {/* 视频格式与清理关键词共用 StringListCard：差异仅文案与取值规范化 */}
              <StringListCard
                icon={Film}
                title="支持的视频格式"
                description="参与文件筛选的视频扩展名"
                addButtonLabel="添加格式"
                addDialogTitle="添加视频格式"
                editDialogTitle="编辑视频格式"
                inputLabel="输入要添加的视频格式扩展名（如 mp4、mkv）"
                inputPlaceholder="请输入格式（如 mp4）"
                emptyText="暂无视频格式"
                items={videoFormats}
                onItemsChange={(items) => { setVideoFormats(items); setIsDirty(true) }}
                normalize={(value) => value.trim().toLowerCase()}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderOpen className="h-5 w-5" />
                <CardTitle>媒体库列表</CardTitle>
              </div>
              <Dialog open={libraryDialog.open} onOpenChange={(open) => setLibraryDialog((prev) => ({ ...prev, open }))}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" onClick={() => openLibraryDialog('add')}>
                    <Plus className="h-4 w-4 mr-1" />
                    添加媒体库
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>
                      {libraryDialog.mode === 'add' ? '添加媒体库' : '编辑媒体库'}
                    </DialogTitle>
                    <DialogDescription>
                      配置媒体库的下载目录和目标目录
                    </DialogDescription>
                  </DialogHeader>
                  <div className="py-4 space-y-4">
                    <div className="space-y-2">
                      <Label>媒体库名称</Label>
                      <Input
                        value={libraryDialog.form.name}
                        onChange={(e) => setLibraryDialog((prev) => ({ ...prev, form: { ...prev.form, name: e.target.value } }))}
                        placeholder="如：电影、成人片库"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>下载目录</Label>
                      <Input
                        value={libraryDialog.form.download_path}
                        onChange={(e) => setLibraryDialog((prev) => ({ ...prev, form: { ...prev.form, download_path: e.target.value } }))}
                        placeholder="如：/115/下载/电影"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>目标目录</Label>
                      <Input
                        value={libraryDialog.form.target_path}
                        onChange={(e) => setLibraryDialog((prev) => ({ ...prev, form: { ...prev.form, target_path: e.target.value } }))}
                        placeholder="如：/媒体库/电影"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>类型</Label>
                      <Input
                        value={libraryDialog.form.type}
                        onChange={(e) => setLibraryDialog((prev) => ({ ...prev, form: { ...prev.form, type: e.target.value } }))}
                        placeholder="如：system、xx-ABC"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>最小传输大小（MB）</Label>
                      <Input
                        type="number"
                        min={0}
                        value={libraryDialog.form.min_transfer_size || ''}
                        onChange={(e) => setLibraryDialog((prev) => ({ ...prev, form: { ...prev.form, min_transfer_size: parseInt(e.target.value) || 0 } }))}
                        placeholder="0 表示不限制"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setLibraryDialog((prev) => ({ ...prev, open: false }))}>
                      取消
                    </Button>
                    <Button onClick={() => handleLibrarySave()}>
                      {libraryDialog.mode === 'add' ? '添加' : '保存'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
            <CardDescription>已配置的媒体库信息</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {libraries.length > 0 ? (
                libraries.map((library, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{library.name}</span>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => openLibraryDialog('edit', index)}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-red-500 hover:text-red-600"
                          onClick={() => confirmDeleteLibrary(index)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-muted-foreground">
                      <div>
                        <span className="text-foreground/70">类型：</span>
                        <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-xs">
                          {library.type}
                        </span>
                      </div>
                      <div>
                        <span className="text-foreground/70">最小传输：</span>
                        {library.min_transfer_size > 0 ? `${library.min_transfer_size} MB` : '不限制'}
                      </div>
                      <div className="md:col-span-2">
                        <span className="text-foreground/70">下载目录：</span>
                        {library.download_path}
                      </div>
                      <div className="md:col-span-2">
                        <span className="text-foreground/70">目标目录：</span>
                        {library.target_path}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  暂无媒体库配置
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 清理关键词：与视频格式共用通用列表编辑卡片 */}
        <StringListCard
          icon={Tag}
          title="文件清理规则"
          description="整理时需要从文件名中移除的关键词"
          addButtonLabel="添加关键词"
          addDialogTitle="添加清理关键词"
          editDialogTitle="编辑清理关键词"
          inputLabel="包含此关键词的文件名将不会被清理"
          inputPlaceholder="请输入关键词（如 hhd800.com@）"
          emptyText="未配置清理关键词"
          items={removeKeywords}
          onItemsChange={(items) => { setRemoveKeywords(items); setIsDirty(true) }}
          normalize={(value) => value.trim()}
        />

        {/* 媒体库删除/覆盖的二次确认 */}
        <Dialog open={confirmDialog.open} onOpenChange={(open) => setConfirmDialog({ ...confirmDialog, open })}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{confirmDialog.title}</DialogTitle>
              <DialogDescription>{confirmDialog.description}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmDialog({ ...confirmDialog, open: false })}>
                取消
              </Button>
              <Button
                variant={confirmDialog.type === 'delete' ? 'destructive' : 'default'}
                onClick={confirmDialog.onConfirm}
              >
                {confirmDialog.confirmText}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {isDirty && (
          <div className="sticky bottom-4 flex justify-end">
            <Button
              onClick={handleSave}
              disabled={updateConfig.isPending}
              className="shadow-lg"
            >
              {updateConfig.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              保存配置
            </Button>
          </div>
        )}
      </div>
    </PageContainer>
  )
}
