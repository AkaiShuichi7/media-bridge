// 整理记录页面 - 查看文件整理历史
import { useState } from 'react'
import { FileCheck2, ChevronLeft, ChevronRight, FolderInput, FolderOutput } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageContainer } from '@/components/shared/PageContainer'
import { EmptyState } from '@/components/shared/EmptyState'
import { useOrganizeRecords } from '@/hooks/queries'
import { formatDate } from '@/lib/utils'
import type { OrganizeRecordItem } from '@/types/api'

export default function Records() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const pageSize = 20
  const statusValue = statusFilter === 'all' ? undefined : statusFilter

  const { data, isLoading } = useOrganizeRecords(page, pageSize, statusValue)

  const records = data?.records || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / pageSize)

  return (
    <PageContainer>
      {/* 状态筛选 */}
      <div className="mb-6">
        <Tabs value={statusFilter} onValueChange={v => { setStatusFilter(v); setPage(1) }}>
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="success">成功</TabsTrigger>
            <TabsTrigger value="skipped">跳过</TabsTrigger>
            <TabsTrigger value="failed">失败</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* 记录列表 */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />)}
        </div>
      ) : records.length === 0 ? (
        <EmptyState
          icon={FileCheck2}
          title="暂无整理记录"
          description="任务完成后自动整理文件"
        />
      ) : (
        <>
          {/* PC 端 Table */}
          <div className="hidden md:block rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>原始文件</TableHead>
                  <TableHead>整理后</TableHead>
                  <TableHead>整理时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record: OrganizeRecordItem) => (
                  <TableRow key={record.id}>
                    <TableCell className="max-w-xs">
                      <p className="truncate" title={record.original_name}>{record.original_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{record.source_path}</p>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <p className="truncate font-medium" title={record.organized_name}>{record.organized_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{record.target_path}</p>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(record.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* 移动端卡片 */}
          <div className="space-y-3 md:hidden">
            {records.map((record: OrganizeRecordItem) => (
              <Card key={record.id}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{record.organized_name}</p>
                      <p className="mt-1 truncate text-sm text-muted-foreground" title={record.original_name}>
                        原文件: {record.original_name}
                      </p>
                      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                        <FolderInput className="h-3 w-3" />
                        <span className="truncate">{record.source_path}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <FolderOutput className="h-3 w-3" />
                        <span className="truncate">{record.target_path}</span>
                      </div>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{formatDate(record.created_at)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {page} / {totalPages} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </PageContainer>
  )
}
