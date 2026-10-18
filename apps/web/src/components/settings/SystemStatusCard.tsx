// 系统状态卡片 - 后台监控运行状态的纯展示组件
// 数据由 Settings 页统一拉取（useStatus）后经 props 传入，避免重复请求
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'

interface SystemStatus {
  monitor_running?: boolean
  active_tasks?: number
  last_check_time?: string
}

export function SystemStatusCard({ statusData }: { statusData?: SystemStatus }) {
  return (
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
  )
}
