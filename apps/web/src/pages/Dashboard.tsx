/**
 * @description 仪表盘页面
 * @responsibility 系统概览、状态监控与快速操作入口
 */
import { useState } from 'react'
import { Activity, ListTodo, FileCheck, Clock, AlertCircle, CheckCircle2, Loader2, Plus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog'
import { PageContainer } from '@/components/shared/PageContainer'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { TaskStatusBadge } from '@/components/shared/StatusBadge'
import { useStatus, useTasks, useOrganizeRecords, useAddTask, useLibraries } from '@/hooks/queries'
import { formatDate } from '@/lib/utils'
import {
  type TaskItem,
  type LibraryItem,
  type OrganizeRecordItem,
  isTaskFailed,
  isTaskCompleted,
  isTaskPending,
} from '@/types/api'

export default function Dashboard() {
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [magnet, setMagnet] = useState('')
  const [libraryName, setLibraryName] = useState('')
  const [taskName, setTaskName] = useState('')

  const { data: status } = useStatus()
  const { data: tasksData, isLoading: tasksLoading } = useTasks()
  const { data: recordsData, isLoading: recordsLoading } = useOrganizeRecords(1, 5)
  const { data: libraries } = useLibraries()
  const addTask = useAddTask()

  const allTasks = tasksData?.tasks || []
  const recentTasks = allTasks.slice(0, 5)
  const recentRecords = recordsData?.records?.slice(0, 5) || []

  // 云端契约：负数=失败，2=完成，其余=进行中；与任务页筛选保持同一口径
  const activeTasks = allTasks.filter((t: TaskItem) => isTaskPending(t.status)).length
  const completedTasks = allTasks.filter((t: TaskItem) => isTaskCompleted(t.status)).length
  const failedTasks = allTasks.filter((t: TaskItem) => isTaskFailed(t.status)).length

  const handleAddTask = async () => {
    if (!magnet.trim() || !libraryName) return
    await addTask.mutateAsync({ magnet: magnet.trim(), library_name: libraryName, name: taskName || undefined })
    setMagnet('')
    setLibraryName('')
    setTaskName('')
    setAddDialogOpen(false)
  }

  const AddTaskForm = () => (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">磁力链接 *</label>
        <Textarea 
          placeholder="magnet:?xt=urn:btih:..." 
          value={magnet}
          onChange={e => setMagnet(e.target.value)}
          rows={3}
          className="break-all"
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">媒体库 *</label>
        <Select value={libraryName} onValueChange={setLibraryName}>
          <SelectTrigger><SelectValue placeholder="选择媒体库" /></SelectTrigger>
          <SelectContent>
            {libraries?.map((lib: LibraryItem) => (
              <SelectItem key={lib.name} value={lib.name}>{lib.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">任务名称（可选）</label>
        <Input placeholder="自定义名称" value={taskName} onChange={e => setTaskName(e.target.value)} />
      </div>
    </div>
  )

  return (
    <PageContainer>
      <div className="flex items-center justify-between space-y-2 mb-6">
        <h2 className="text-3xl font-bold tracking-tight">仪表盘</h2>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="监控状态"
          value={status?.monitor_running ? '运行中' : '已停止'}
          icon={Activity}
          iconClassName={status?.monitor_running ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}
        />
        <StatCard
          title="进行中任务"
          value={activeTasks}
          icon={Clock}
          iconClassName="bg-blue-500/10 text-blue-500"
        />
        <StatCard
          title="已完成任务"
          value={completedTasks}
          icon={CheckCircle2}
          iconClassName="bg-emerald-500/10 text-emerald-500"
        />
        <StatCard
          title="失败任务"
          value={failedTasks}
          icon={AlertCircle}
          iconClassName="bg-red-500/10 text-red-500"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        <Card className="overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-medium">最近任务</CardTitle>
          </CardHeader>
          <CardContent>
            {tasksLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <div key={i} className="h-12 rounded bg-muted animate-pulse" />)}
              </div>
            ) : recentTasks.length === 0 ? (
              <EmptyState
                icon={ListTodo}
                title="暂无任务"
                description="点击右下角按钮添加任务"
                className="py-8"
              />
            ) : (
              <div className="space-y-3">
                {recentTasks.map((task: TaskItem) => (
                  <div key={task.task_id} className="min-w-0 overflow-hidden rounded-lg border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="max-w-full truncate text-sm font-medium" title={task.name}>{task.name}</p>
                      <TaskStatusBadge status={task.status} />
                    </div>
                    <p className="mt-1 max-w-full truncate text-xs text-muted-foreground">
                      {isTaskPending(task.status) ? `进度 ${task.progress}% · ` : ''}{formatDate(task.add_time)}
                    </p>
                    {task.error_message && (
                      <p
                        className="mt-1 max-w-full truncate text-xs text-red-500"
                        title={task.error_message}
                      >
                        {task.error_message}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-medium">最近整理记录</CardTitle>
          </CardHeader>
          <CardContent>
            {recordsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <div key={i} className="h-12 rounded bg-muted animate-pulse" />)}
              </div>
            ) : recentRecords.length === 0 ? (
              <EmptyState
                icon={FileCheck}
                title="暂无整理记录"
                description="任务完成后自动整理文件"
                className="py-8"
              />
            ) : (
              <div className="space-y-3">
                {recentRecords.map((record: OrganizeRecordItem) => (
                  <div key={record.id} className="min-w-0 overflow-hidden rounded-lg border p-3">
                    <p className="max-w-full truncate text-sm font-medium" title={record.organized_name}>{record.organized_name}</p>
                    <p className="mt-1 max-w-full truncate text-xs text-muted-foreground" title={record.target_path}>{record.target_path}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDate(record.created_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="fixed bottom-24 right-6 z-50">
        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button className="h-14 w-14 rounded-full shadow-lg" size="icon">
              <Plus className="h-6 w-6" />
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>添加离线下载任务</DialogTitle></DialogHeader>
            <AddTaskForm />
            <DialogFooter>
              <Button variant="outline" onClick={() => setAddDialogOpen(false)}>取消</Button>
              <Button onClick={handleAddTask} disabled={addTask.isPending || !magnet.trim() || !libraryName}>
                {addTask.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}添加
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </PageContainer>
  )
}
