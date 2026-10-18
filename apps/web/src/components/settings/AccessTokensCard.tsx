// 访问令牌卡片 - 创建/列出/撤销扩展与 Agent 用的访问令牌
// 从 Settings 页抽出：令牌相关状态与 API 调用由本组件自持，页面不再感知
import { useState, useEffect } from 'react'
import { KeyRound, Copy } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'

interface AccessTokenItem {
  id: number
  name: string
  created_at: string
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
}

export function AccessTokensCard() {
  const [accessTokens, setAccessTokens] = useState<AccessTokenItem[]>([])
  const [tokenName, setTokenName] = useState('')
  const [newAccessToken, setNewAccessToken] = useState('')
  const [tokenBusy, setTokenBusy] = useState(false)

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

  return (
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
  )
}
