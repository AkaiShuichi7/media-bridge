// 字符串列表编辑卡片 - 「支持的视频格式」与「文件清理关键词」的通用实现
// 两处 UI 与交互完全同构（添加/编辑/删除 + 重复项二次确认），差异仅在
// 标题文案与取值规范化（格式小写、关键词原样），因此收拢为单个组件
import { useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

interface StringListCardProps {
  icon: LucideIcon
  title: string
  description: string
  addButtonLabel: string
  addDialogTitle: string
  editDialogTitle: string
  inputLabel: string
  inputPlaceholder: string
  emptyText: string
  /** 列表值（受控，来自配置表单状态） */
  items: string[]
  /** 列表变更回调（父层负责标记表单 dirty） */
  onItemsChange: (items: string[]) => void
  /** 输入规范化：格式列传 trim+小写，关键词列传 trim */
  normalize: (value: string) => string
}

/** 重复项二次确认的对话框状态 */
interface ConfirmState {
  open: boolean
  title: string
  description: string
  confirmText: string
  onConfirm: () => void
}

export function StringListCard({
  icon: Icon,
  title,
  description,
  addButtonLabel,
  addDialogTitle,
  editDialogTitle,
  inputLabel,
  inputPlaceholder,
  emptyText,
  items,
  onItemsChange,
  normalize,
}: StringListCardProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<'add' | 'edit'>('add')
  const [editingItem, setEditingItem] = useState('')
  const [draft, setDraft] = useState('')
  const [confirm, setConfirm] = useState<ConfirmState>({
    open: false,
    title: '',
    description: '',
    confirmText: '',
    onConfirm: () => {},
  })

  /** 关闭确认框的小工具 */
  const closeConfirm = () => setConfirm((prev) => ({ ...prev, open: false }))

  /** 打开添加/编辑对话框 */
  const openDialog = (mode: 'add' | 'edit', item?: string) => {
    setDialogMode(mode)
    if (mode === 'edit' && item) {
      setEditingItem(item)
      setDraft(item)
    } else {
      setEditingItem('')
      setDraft('')
    }
    setDialogOpen(true)
  }

  /** 保存对话框输入：重复项走二次确认，其余直接写入并标记 dirty */
  const handleSave = () => {
    if (!draft.trim()) return

    const value = normalize(draft)
    if (dialogMode === 'add') {
      if (items.includes(value)) {
        setConfirm({
          open: true,
          title: '已存在',
          description: `"${value}" 已存在，是否仍要添加？`,
          confirmText: '仍要添加',
          onConfirm: () => {
            onItemsChange([...items, value])
            closeConfirm()
            setDialogOpen(false)
          },
        })
        return
      }
      onItemsChange([...items, value])
    } else {
      if (value !== editingItem && items.includes(value)) {
        setConfirm({
          open: true,
          title: '已存在',
          description: `"${value}" 已存在，是否仍要修改？`,
          confirmText: '仍要修改',
          onConfirm: () => {
            onItemsChange(items.map((item) => (item === editingItem ? value : item)))
            closeConfirm()
            setDialogOpen(false)
          },
        })
        return
      }
      onItemsChange(items.map((item) => (item === editingItem ? value : item)))
    }
    setDialogOpen(false)
  }

  /** 删除确认框（destructive 按钮） */
  const confirmDelete = (item: string) => {
    setConfirm({
      open: true,
      title: `删除${inputLabel}`,
      description: `确定要删除 "${item}" 吗？此操作可能会影响文件整理功能。`,
      confirmText: '确认删除',
      onConfirm: () => {
        onItemsChange(items.filter((existing) => existing !== item))
        closeConfirm()
      },
    })
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5" />
            <CardTitle>{title}</CardTitle>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm" onClick={() => openDialog('add')}>
                <Plus className="h-4 w-4 mr-1" />
                {addButtonLabel}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{dialogMode === 'add' ? addDialogTitle : editDialogTitle}</DialogTitle>
                <DialogDescription>{inputLabel}</DialogDescription>
              </DialogHeader>
              <div className="py-4">
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={inputPlaceholder}
                  onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  取消
                </Button>
                <Button onClick={handleSave}>
                  {dialogMode === 'add' ? '添加' : '保存'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {items.length > 0 ? (
            items.map((item) => (
              <div
                key={item}
                className="group flex items-center gap-1 px-2 py-1 text-sm bg-secondary rounded-md"
              >
                <span>{item}</span>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => openDialog('edit', item)}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 text-red-500 hover:text-red-600"
                    onClick={() => confirmDelete(item)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ))
          ) : (
            <span className="text-muted-foreground text-sm">{emptyText}</span>
          )}
        </div>
      </CardContent>

      {/* 重复项 / 删除的二次确认 */}
      <Dialog open={confirm.open} onOpenChange={(open) => setConfirm({ ...confirm, open })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirm.title}</DialogTitle>
            <DialogDescription>{confirm.description}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm({ ...confirm, open: false })}>
              取消
            </Button>
            <Button
              variant={confirm.title.startsWith('删除') ? 'destructive' : 'default'}
              onClick={confirm.onConfirm}
            >
              {confirm.confirmText}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
