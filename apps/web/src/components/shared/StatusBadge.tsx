import { Badge } from '@/components/ui/badge'
import { ORGANIZE_STATUS, isTaskFailed, isTaskCompleted } from '@/types/api'
import { cn } from '@/lib/utils'

interface TaskStatusBadgeProps { status: number; className?: string }

export function TaskStatusBadge({ status, className }: TaskStatusBadgeProps) {
  // 云端契约：负数=失败，2=完成，其余=进行中（负数原始值透传，此处归一分类）
  type StatusKind = 'pending' | 'failed' | 'completed'
  const statusKind: StatusKind = isTaskFailed(status)
    ? 'failed'
    : isTaskCompleted(status)
      ? 'completed'
      : 'pending'

  const config: Record<StatusKind, { label: string; className: string }> = {
    pending: { label: '进行中', className: 'bg-blue-500/10 text-blue-500 border-blue-500/20 hover:bg-blue-500/20' },
    failed: { label: '失败', className: 'bg-red-500/10 text-red-500 border-red-500/20 hover:bg-red-500/20' },
    completed: { label: '完成', className: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20' },
  }

  const { label, className: statusClassName } = config[statusKind]

  return (
    <Badge variant="outline" className={cn('text-xs font-medium', statusClassName, className)}>
      {statusKind === 'pending' && (
        <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
      )}
      {label}
    </Badge>
  )
}

interface OrganizeStatusBadgeProps { status: string; className?: string }

export function OrganizeStatusBadge({ status, className }: OrganizeStatusBadgeProps) {
  const config: Record<string, { label: string; className: string }> = {
    [ORGANIZE_STATUS.SUCCESS]: { label: '成功', className: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20' },
    [ORGANIZE_STATUS.FAILED]: { label: '失败', className: 'bg-red-500/10 text-red-500 border-red-500/20 hover:bg-red-500/20' },
    [ORGANIZE_STATUS.SKIPPED]: { label: '已跳过', className: 'bg-gray-500/10 text-gray-500 border-gray-500/20 hover:bg-gray-500/20' },
  }
  
  const { label, className: statusClassName } = config[status] || { label: '未知', className: 'bg-gray-500/10 text-gray-500 border-gray-500/20' }

  return (
    <Badge variant="outline" className={cn('text-xs font-medium', statusClassName, className)}>
      {label}
    </Badge>
  )
}
