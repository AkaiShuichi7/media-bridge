import { useState, useEffect } from 'react'
import { Loader2, Save, Film, Clock, Tag, FolderOpen, Plus, Pencil, Trash2, KeyRound, Copy } from 'lucide-react'
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
import { useConfig, useUpdateConfig, useStatus } from '@/hooks/queries'
import type { UpdateConfigRequest, LibraryItem } from '@/types/api'
import { api } from '@/lib/api'

type ConfirmDialogType = 'delete' | 'edit' | 'add'

interface ConfirmDialogState {
  open: boolean
  type: ConfirmDialogType
  title: string
  description: string
  confirmText: string
  item?: string
  onConfirm: () => void
}

interface AccessTokenItem {
  id: number
  name: string
  created_at: string
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
}

export default function Settings() {
  const { data: configData, isLoading: configLoading } = useConfig()
  const { data: statusData } = useStatus()
  const updateConfig = useUpdateConfig()

  const [formData, setFormData] = useState<UpdateConfigRequest>({})
  const [isDirty, setIsDirty] = useState(false)
  const [accessTokens, setAccessTokens] = useState<AccessTokenItem[]>([])
  const [tokenName, setTokenName] = useState('')
  const [newAccessToken, setNewAccessToken] = useState('')
  const [tokenBusy, setTokenBusy] = useState(false)

  const [videoFormats, setVideoFormats] = useState<string[]>([])
  const [libraries, setLibraries] = useState<LibraryItem[]>([])
  const [removeKeywords, setRemoveKeywords] = useState<string[]>([])

  const [formatDialogOpen, setFormatDialogOpen] = useState(false)
  const [formatDialogMode, setFormatDialogMode] = useState<'add' | 'edit'>('add')
  const [editingFormat, setEditingFormat] = useState<string>('')
  const [newFormat, setNewFormat] = useState('')

  const [libraryDialogOpen, setLibraryDialogOpen] = useState(false)
  const [libraryDialogMode, setLibraryDialogMode] = useState<'add' | 'edit'>('add')
  const [editingLibraryIndex, setEditingLibraryIndex] = useState<number>(-1)
  const [libraryForm, setLibraryForm] = useState<LibraryItem>({
    name: '',
    download_path: '',
    target_path: '',
    type: 'system',
    min_transfer_size: 0,
  })

  const [keywordDialogOpen, setKeywordDialogOpen] = useState(false)
  const [keywordDialogMode, setKeywordDialogMode] = useState<'add' | 'edit'>('add')
  const [editingKeyword, setEditingKeyword] = useState<string>('')
  const [newKeyword, setNewKeyword] = useState('')

  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState>({
    open: false,
    type: 'delete',
    title: '',
    description: '',
    confirmText: '',
    onConfirm: () => {},
  })

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

  const loadAccessTokens = async () => {
    const { data } = await api.get('/api/auth/tokens')
    setAccessTokens(data.data)
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 页面挂载后异步加载并展示访问令牌。
    void loadAccessTokens()
  }, [])

  const createAccessToken = async () => {
    if (!tokenName.trim()) return
    setTokenBusy(true)
    try {
      const { data } = await api.post('/api/auth/tokens', { name: tokenName.trim() })
      setNewAccessToken(data.data.token)
      setTokenName('')
      await loadAccessTokens()
    } finally {
      setTokenBusy(false)
    }
  }

  const revokeAccessToken = async (id: number) => {
    await api.delete(`/api/auth/tokens/${id}`)
    await loadAccessTokens()
  }

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

  const openFormatDialog = (mode: 'add' | 'edit', format?: string) => {
    setFormatDialogMode(mode)
    if (mode === 'edit' && format) {
      setEditingFormat(format)
      setNewFormat(format)
    } else {
      setEditingFormat('')
      setNewFormat('')
    }
    setFormatDialogOpen(true)
  }

  const handleFormatSave = () => {
    if (!newFormat.trim()) return
    
    const format = newFormat.trim().toLowerCase()
    if (formatDialogMode === 'add') {
      if (videoFormats.includes(format)) {
        setConfirmDialog({
          open: true,
          type: 'add',
          title: '格式已存在',
          description: `格式 "${format}" 已存在，是否仍要添加？`,
          confirmText: '仍要添加',
          item: format,
          onConfirm: () => {
            setVideoFormats([...videoFormats, format])
            setIsDirty(true)
            setConfirmDialog(prev => ({ ...prev, open: false }))
            setFormatDialogOpen(false)
          },
        })
        return
      }
      setVideoFormats([...videoFormats, format])
    } else {
      if (format !== editingFormat && videoFormats.includes(format)) {
        setConfirmDialog({
          open: true,
          type: 'edit',
          title: '格式已存在',
          description: `格式 "${format}" 已存在，是否仍要修改？`,
          confirmText: '仍要修改',
          item: format,
          onConfirm: () => {
            const newFormats = videoFormats.map(f => f === editingFormat ? format : f)
            setVideoFormats(newFormats)
            setIsDirty(true)
            setConfirmDialog(prev => ({ ...prev, open: false }))
            setFormatDialogOpen(false)
          },
        })
        return
      }
      const newFormats = videoFormats.map(f => f === editingFormat ? format : f)
      setVideoFormats(newFormats)
    }
    setIsDirty(true)
    setFormatDialogOpen(false)
  }

  const confirmDeleteFormat = (format: string) => {
    setConfirmDialog({
      open: true,
      type: 'delete',
      title: '删除视频格式',
      description: `确定要删除视频格式 "${format}" 吗？此操作可能会影响文件整理功能。`,
      confirmText: '确认删除',
      item: format,
      onConfirm: () => {
        setVideoFormats(videoFormats.filter(f => f !== format))
        setIsDirty(true)
        setConfirmDialog(prev => ({ ...prev, open: false }))
      },
    })
  }

  const openLibraryDialog = (mode: 'add' | 'edit', index?: number) => {
    setLibraryDialogMode(mode)
    if (mode === 'edit' && index !== undefined && index >= 0) {
      setEditingLibraryIndex(index)
      setLibraryForm({ ...libraries[index] })
    } else {
      setEditingLibraryIndex(-1)
      setLibraryForm({
        name: '',
        download_path: '',
        target_path: '',
        type: 'system',
        min_transfer_size: 0,
      })
    }
    setLibraryDialogOpen(true)
  }

  const handleLibrarySave = () => {
    if (!libraryForm.name.trim() || !libraryForm.download_path.trim() || !libraryForm.target_path.trim()) {
      return
    }

    const lib: LibraryItem = {
      name: libraryForm.name.trim(),
      download_path: libraryForm.download_path.trim(),
      target_path: libraryForm.target_path.trim(),
      type: libraryForm.type.trim() || 'system',
      min_transfer_size: libraryForm.min_transfer_size || 0,
    }

    if (libraryDialogMode === 'add') {
      const existingIndex = libraries.findIndex(l => l.name === lib.name)
      if (existingIndex >= 0) {
        setConfirmDialog({
          open: true,
          type: 'add',
          title: '媒体库已存在',
          description: `媒体库 "${lib.name}" 已存在，是否仍要添加？`,
          confirmText: '仍要添加',
          item: lib.name,
          onConfirm: () => {
            const newLibraries = [...libraries]
            newLibraries[existingIndex] = lib
            setLibraries(newLibraries)
            setIsDirty(true)
            setConfirmDialog(prev => ({ ...prev, open: false }))
            setLibraryDialogOpen(false)
          },
        })
        return
      }
      setLibraries([...libraries, lib])
    } else {
      const newLibraries = [...libraries]
      newLibraries[editingLibraryIndex] = lib
      setLibraries(newLibraries)
    }
    setIsDirty(true)
    setLibraryDialogOpen(false)
  }

  const confirmDeleteLibrary = (index: number) => {
    const lib = libraries[index]
    setConfirmDialog({
      open: true,
      type: 'delete',
      title: '删除媒体库',
      description: `确定要删除媒体库 "${lib.name}" 吗？此操作可能会影响文件整理功能。`,
      confirmText: '确认删除',
      item: lib.name,
      onConfirm: () => {
        setLibraries(libraries.filter((_, i) => i !== index))
        setIsDirty(true)
        setConfirmDialog(prev => ({ ...prev, open: false }))
      },
    })
  }

  const openKeywordDialog = (mode: 'add' | 'edit', keyword?: string) => {
    setKeywordDialogMode(mode)
    if (mode === 'edit' && keyword) {
      setEditingKeyword(keyword)
      setNewKeyword(keyword)
    } else {
      setEditingKeyword('')
      setNewKeyword('')
    }
    setKeywordDialogOpen(true)
  }

  const handleKeywordSave = () => {
    if (!newKeyword.trim()) return
    
    const keyword = newKeyword.trim()
    if (keywordDialogMode === 'add') {
      if (removeKeywords.includes(keyword)) {
        setConfirmDialog({
          open: true,
          type: 'add',
          title: '关键词已存在',
          description: `关键词 "${keyword}" 已存在，是否仍要添加？`,
          confirmText: '仍要添加',
          item: keyword,
          onConfirm: () => {
            setRemoveKeywords([...removeKeywords, keyword])
            setIsDirty(true)
            setConfirmDialog(prev => ({ ...prev, open: false }))
            setKeywordDialogOpen(false)
          },
        })
        return
      }
      setRemoveKeywords([...removeKeywords, keyword])
    } else {
      if (keyword !== editingKeyword && removeKeywords.includes(keyword)) {
        setConfirmDialog({
          open: true,
          type: 'edit',
          title: '关键词已存在',
          description: `关键词 "${keyword}" 已存在，是否仍要修改？`,
          confirmText: '仍要修改',
          item: keyword,
          onConfirm: () => {
            const newKeywords = removeKeywords.map(k => k === editingKeyword ? keyword : k)
            setRemoveKeywords(newKeywords)
            setIsDirty(true)
            setConfirmDialog(prev => ({ ...prev, open: false }))
            setKeywordDialogOpen(false)
          },
        })
        return
      }
      const newKeywords = removeKeywords.map(k => k === editingKeyword ? keyword : k)
      setRemoveKeywords(newKeywords)
    }
    setIsDirty(true)
    setKeywordDialogOpen(false)
  }

  const confirmDeleteKeyword = (keyword: string) => {
    setConfirmDialog({
      open: true,
      type: 'delete',
      title: '删除关键词',
      description: `确定要删除关键词 "${keyword}" 吗？包含此关键词的文件名将不会被清理。`,
      confirmText: '确认删除',
      item: keyword,
      onConfirm: () => {
        setRemoveKeywords(removeKeywords.filter(k => k !== keyword))
        setIsDirty(true)
        setConfirmDialog(prev => ({ ...prev, open: false }))
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
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2"><KeyRound className="h-5 w-5" /><CardTitle>访问令牌</CardTitle></div>
            <CardDescription>为后续浏览器插件或 Agent 创建独立、可撤销的访问凭据。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={tokenName} onChange={(event) => setTokenName(event.target.value)} placeholder="例如：我的 Chrome 插件" maxLength={128} />
              <Button onClick={createAccessToken} disabled={tokenBusy || !tokenName.trim()}>{tokenBusy ? '创建中…' : '创建令牌'}</Button>
            </div>
            {newAccessToken && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                <p className="mb-2 font-medium">请立即保存此令牌；关闭后将无法再次查看。</p>
                <div className="flex items-center gap-2"><code className="min-w-0 flex-1 break-all rounded bg-background p-2">{newAccessToken}</code><Button variant="outline" size="icon" onClick={() => void navigator.clipboard.writeText(newAccessToken)} aria-label="复制令牌"><Copy className="size-4" /></Button></div>
              </div>
            )}
            {accessTokens.length > 0 && <div className="space-y-2">{accessTokens.filter((token) => !token.revoked_at).map((token) => <div key={token.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm"><span className="font-medium">{token.name}</span><span className="text-muted-foreground">创建于 {new Date(token.created_at).toLocaleString('zh-CN')}</span>{token.last_used_at && <span className="text-muted-foreground">最近使用 {new Date(token.last_used_at).toLocaleString('zh-CN')}</span>}<Button className="ml-auto" variant="outline" size="sm" onClick={() => void revokeAccessToken(token.id)}>撤销</Button></div>)}</div>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${statusData?.monitor_running ? 'bg-green-500' : 'bg-red-500'}`} />
              <CardTitle>系统状态</CardTitle>
            </div>
            <CardDescription>后台监控运行状态</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">监控状态：</span>
                <span className={statusData?.monitor_running ? 'text-green-600' : 'text-red-600'}>
                  {statusData?.monitor_running ? '运行中' : '已停止'}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">活跃任务：</span>
                <span className="font-medium">{statusData?.active_tasks || 0}</span>
              </div>
              <div>
                <span className="text-muted-foreground">最后检查：</span>
                <span className="font-medium">
                  {statusData?.last_check_time ? new Date(statusData.last_check_time).toLocaleString('zh-CN') : '-'}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

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
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Film className="h-5 w-5" />
                <CardTitle>媒体配置</CardTitle>
              </div>
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
              <div className="flex items-center justify-between">
                <Label>支持的视频格式</Label>
                <Dialog open={formatDialogOpen} onOpenChange={setFormatDialogOpen}>
                  <DialogTrigger asChild>
                    <Button variant="outline" size="sm" onClick={() => openFormatDialog('add')}>
                      <Plus className="h-4 w-4 mr-1" />
                      添加格式
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>
                        {formatDialogMode === 'add' ? '添加视频格式' : '编辑视频格式'}
                      </DialogTitle>
                      <DialogDescription>
                        输入要添加的视频格式扩展名（如 mp4、mkv）
                      </DialogDescription>
                    </DialogHeader>
                    <div className="py-4">
                      <Input
                        value={newFormat}
                        onChange={(e) => setNewFormat(e.target.value)}
                        placeholder="请输入格式（如 mp4）"
                        onKeyDown={(e) => e.key === 'Enter' && handleFormatSave()}
                      />
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setFormatDialogOpen(false)}>
                        取消
                      </Button>
                      <Button onClick={handleFormatSave}>
                        {formatDialogMode === 'add' ? '添加' : '保存'}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
              <div className="flex flex-wrap gap-2">
                {videoFormats.length > 0 ? (
                  videoFormats.map((format) => (
                    <div
                      key={format}
                      className="group flex items-center gap-1 px-2 py-1 text-sm bg-secondary rounded-md"
                    >
                      <span>{format}</span>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          onClick={() => openFormatDialog('edit', format)}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-red-500 hover:text-red-600"
                          onClick={() => confirmDeleteFormat(format)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))
                ) : (
                  <span className="text-muted-foreground text-sm">暂无视频格式</span>
                )}
              </div>
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
              <Dialog open={libraryDialogOpen} onOpenChange={setLibraryDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" onClick={() => openLibraryDialog('add')}>
                    <Plus className="h-4 w-4 mr-1" />
                    添加媒体库
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>
                      {libraryDialogMode === 'add' ? '添加媒体库' : '编辑媒体库'}
                    </DialogTitle>
                    <DialogDescription>
                      配置媒体库的下载目录和目标目录
                    </DialogDescription>
                  </DialogHeader>
                  <div className="py-4 space-y-4">
                    <div className="space-y-2">
                      <Label>媒体库名称</Label>
                      <Input
                        value={libraryForm.name}
                        onChange={(e) => setLibraryForm({ ...libraryForm, name: e.target.value })}
                        placeholder="如：电影、成人片库"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>下载目录</Label>
                      <Input
                        value={libraryForm.download_path}
                        onChange={(e) => setLibraryForm({ ...libraryForm, download_path: e.target.value })}
                        placeholder="如：/115/下载/电影"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>目标目录</Label>
                      <Input
                        value={libraryForm.target_path}
                        onChange={(e) => setLibraryForm({ ...libraryForm, target_path: e.target.value })}
                        placeholder="如：/媒体库/电影"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>类型</Label>
                      <Input
                        value={libraryForm.type}
                        onChange={(e) => setLibraryForm({ ...libraryForm, type: e.target.value })}
                        placeholder="如：system、xx-ABC"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>最小传输大小（MB）</Label>
                      <Input
                        type="number"
                        min={0}
                        value={libraryForm.min_transfer_size || ''}
                        onChange={(e) => setLibraryForm({ ...libraryForm, min_transfer_size: parseInt(e.target.value) || 0 })}
                        placeholder="0 表示不限制"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setLibraryDialogOpen(false)}>
                      取消
                    </Button>
                    <Button onClick={handleLibrarySave}>
                      {libraryDialogMode === 'add' ? '添加' : '保存'}
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

        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Tag className="h-5 w-5" />
                <CardTitle>文件清理规则</CardTitle>
              </div>
              <Dialog open={keywordDialogOpen} onOpenChange={setKeywordDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" onClick={() => openKeywordDialog('add')}>
                    <Plus className="h-4 w-4 mr-1" />
                    添加关键词
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>
                      {keywordDialogMode === 'add' ? '添加清理关键词' : '编辑清理关键词'}
                    </DialogTitle>
                  </DialogHeader>
                  <div className="py-4">
                    <Input
                      value={newKeyword}
                      onChange={(e) => setNewKeyword(e.target.value)}
                      placeholder="请输入关键词（如 hhd800.com@）"
                      onKeyDown={(e) => e.key === 'Enter' && handleKeywordSave()}
                    />
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setKeywordDialogOpen(false)}>
                      取消
                    </Button>
                    <Button onClick={handleKeywordSave}>
                      {keywordDialogMode === 'add' ? '添加' : '保存'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
            <CardDescription>整理时需要从文件名中移除的关键词</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {removeKeywords.length > 0 ? (
                removeKeywords.map((keyword) => (
                  <div
                    key={keyword}
                    className="group flex items-center gap-1 px-2 py-1 text-sm bg-secondary rounded-md"
                  >
                    <span>{keyword}</span>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5"
                        onClick={() => openKeywordDialog('edit', keyword)}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 text-red-500 hover:text-red-600"
                        onClick={() => confirmDeleteKeyword(keyword)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))
              ) : (
                <span className="text-muted-foreground text-sm">未配置清理关键词</span>
              )}
            </div>
          </CardContent>
        </Card>

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
