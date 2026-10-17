import { useState } from 'react'
import { Trash2, Magnet, Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { PageContainer } from '@/components/shared/PageContainer'
import { EmptyState } from '@/components/shared/EmptyState'
import { TaskStatusBadge } from '@/components/shared/StatusBadge'
import { useTasks, useDeleteTask } from '@/hooks/queries'
import { formatDate, truncate } from '@/lib/utils'
import {
  type TaskItem,
  isTaskFailed,
  isTaskCompleted,
  isTaskPending,
} from '@/types/api'

export default function Tasks() {
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [deleteTaskId, setDeleteTaskId] = useState<string | null>(null)

  const { data: tasksData, isLoading } = useTasks()
  const deleteTask = useDeleteTask()

  const allTasks: TaskItem[] = tasksData?.tasks || []
  // 云端契约：负数=失败，2=完成，其余=进行中；筛选按语义分类而非裸数值
  const filteredTasks = allTasks.filter((t: TaskItem) => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'failed') return isTaskFailed(t.status)
    if (statusFilter === 'completed') return isTaskCompleted(t.status)
    return isTaskPending(t.status)
  })

  const countAll = allTasks.length
  const countPending = allTasks.filter((t: TaskItem) => isTaskPending(t.status)).length
  const countCompleted = allTasks.filter((t: TaskItem) => isTaskCompleted(t.status)).length
  const countFailed = allTasks.filter((t: TaskItem) => isTaskFailed(t.status)).length

  const handleDeleteTask = async () => {
    if (deleteTaskId === null) return
    await deleteTask.mutateAsync(deleteTaskId)
    setDeleteTaskId(null)
  }

  return (
    <PageContainer>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={statusFilter} onValueChange={setStatusFilter} className="w-full sm:w-auto">
          <TabsList>
            <TabsTrigger value="all">全部 {countAll}</TabsTrigger>
            <TabsTrigger value="pending">进行中 {countPending}</TabsTrigger>
            <TabsTrigger value="completed">完成 {countCompleted}</TabsTrigger>
            <TabsTrigger value="failed">失败 {countFailed}</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />)}</div>
      ) : filteredTasks.length === 0 ? (
        <EmptyState icon={Magnet} title="暂无任务" description="在仪表盘点击添加任务" />
      ) : (
        <div className="space-y-3">
          {filteredTasks.map((task: TaskItem) => (
            <Card key={task.task_id} className="transition-colors hover:bg-accent/50">
              <CardContent className="flex items-center justify-between p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-medium">{task.name || '未命名任务'}</p>
                    <TaskStatusBadge status={task.status} />
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <span>ID: {truncate(task.task_id, 16)}</span>
                    <span>{formatDate(task.add_time)}</span>
                    {isTaskPending(task.status) && <span>进度 {task.progress}%</span>}
                  </div>
                  {task.error_message && (
                    <p
                      className="mt-1 max-w-full truncate text-xs text-red-500"
                      title={task.error_message}
                    >
                      {task.error_message}
                    </p>
                  )}
                </div>
                <Button variant="ghost" size="icon" className="ml-2 flex-shrink-0 text-muted-foreground hover:text-red-500" onClick={() => setDeleteTaskId(task.task_id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={deleteTaskId !== null} onOpenChange={open => !open && setDeleteTaskId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>确认删除</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">确定要删除这个任务吗？此操作无法撤销。</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTaskId(null)}>取消</Button>
            <Button variant="destructive" onClick={handleDeleteTask} disabled={deleteTask.isPending}>
              {deleteTask.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  )
}
