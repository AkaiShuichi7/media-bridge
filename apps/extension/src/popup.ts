/**
 * @description 磁力任务助手弹窗
 * @responsibility 展示捕获的磁力链接、配置服务器连接并提交离线任务；
 *               捕获状态的读写复用 captured-state.js，判定复用 magnet.js，
 *               渲染统一经 escapeHtml 转义防止注入，版本号从 manifest 读取
 */
import './popup.css'
import { isMagnetLink } from '../public/magnet.js'
import { clearCapturedMagnet, loadCapturedMagnet, storeCapturedMagnet } from '../public/captured-state.js'

type Library = { name: string }
type Settings = { serverUrl: string; token: string }
type CapturedMagnet = { value: string; title?: string }

const app = document.querySelector<HTMLElement>('#app')!
// 版本号唯一来源是 manifest.json，不再硬编码第二份
const VERSION = chrome.runtime.getManifest().version
const state: { settings: Settings; magnet?: CapturedMagnet; libraries: Library[]; isSubmitting: boolean } = {
  settings: { serverUrl: '', token: '' },
  libraries: [],
  isSubmitting: false,
}

/**
 * HTML 转义：磁力标题来自任意网页 document.title，属不可信输入。
 *
 * @param value 原始字符串
 * @returns 转义后的安全 HTML 片段
 */
function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
}

/**
 * 属性值转义（用于 input value / option value 等属性位置）。
 */
function escapeAttr(value: string) {
  return escapeHtml(value)
}

function normalizedServerUrl(value: string) {
  return value.trim().replace(/\/+$/, '')
}

function show(message: string, error = false) {
  const notice = document.querySelector<HTMLElement>('#notice')!
  notice.textContent = message
  notice.className = error ? 'notice error' : 'notice success'
}

async function requestHostPermission(url: string) {
  const origin = new URL(url).origin
  return chrome.permissions.request({ origins: [`${origin}/*`] })
}

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`${state.settings.serverUrl}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${state.settings.token}`, 'Content-Type': 'application/json', ...(options.headers || {}) },
    credentials: 'omit',
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || payload?.code !== 0) throw new Error(payload?.message || `请求失败 (${response.status})`)
  return payload.data
}

async function saveSettings() {
  const serverUrl = normalizedServerUrl((document.querySelector<HTMLInputElement>('#server-url')!).value)
  const token = (document.querySelector<HTMLInputElement>('#token')!).value.trim()
  if (!serverUrl || !token.startsWith('mb_')) return show('请填写 MediaBridge 地址和以 mb_ 开头的访问令牌。', true)
  try {
    if (!await requestHostPermission(serverUrl)) return show('需要允许该站点访问权限，才能连接 MediaBridge。', true)
    state.settings = { serverUrl, token }
    await chrome.storage.local.set({ settings: state.settings })
    show('连接设置已保存。')
    await loadLibraries()
  } catch {
    show('服务器地址无效。', true)
  }
}

async function loadLibraries() {
  if (!state.settings.serverUrl || !state.settings.token) return
  try {
    state.libraries = (await api('/api/libraries')).libraries
    render()
  } catch (error) {
    show(error instanceof Error ? error.message : '无法读取媒体库。', true)
  }
}

async function submitTask() {
  if (state.isSubmitting) return
  const libraryName = (document.querySelector<HTMLSelectElement>('#library')!).value
  if (!state.magnet || !libraryName) return show('请先选择媒体库。', true)
  state.isSubmitting = true
  render()
  show('正在发送离线任务…')
  let errorMessage: string | undefined
  try {
    await api('/api/tasks', { method: 'POST', body: JSON.stringify({ magnet: state.magnet.value, library_name: libraryName, name: state.magnet.title || undefined }) })
    // 提交成功后清除捕获状态（badge 同步收敛在 captured-state 内）
    await clearCapturedMagnet()
    state.magnet = undefined
    render()
    show('离线任务已提交到 MediaBridge。')
    window.setTimeout(() => window.close(), 2000)
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : '任务提交失败。'
  } finally {
    state.isSubmitting = false
    if (state.magnet) render()
  }
  if (errorMessage) show(errorMessage, true)
}

async function readClipboardManually() {
  try {
    const value = await navigator.clipboard.readText()
    if (!isMagnetLink(value)) {
      show('剪贴板中未找到有效的磁力链接。', true)
      return
    }
    // 状态写入与 badge 同步收敛在 captured-state 内
    const stored = await storeCapturedMagnet(value)
    if (stored) state.magnet = await loadCapturedMagnet()
    render()
    show('已从剪贴板读取磁力链接。')
  } catch {
    show('无法读取剪贴板；请确认已授予剪贴板权限。', true)
  }
}

async function discardCapturedMagnet() {
  state.magnet = undefined
  await clearCapturedMagnet()
  render()
  show('已取消本次待发送任务。')
  window.setTimeout(() => window.close(), 100)
}

function render() {
  const configured = Boolean(state.settings.serverUrl && state.settings.token)
  const hasMagnet = Boolean(state.magnet)
  // 所有动态值经转义后内插（title/value 来自不可信页面与剪贴板）
  app.innerHTML = `
    <section class="header"><strong>MediaBridge</strong><span>磁力任务助手 v${VERSION}</span></section>
    <section class="card"><label>MediaBridge 地址<input id="server-url" type="url" placeholder="https://media.example.com" value="${escapeAttr(state.settings.serverUrl)}" /></label>
    <label>访问令牌<input id="token" type="password" placeholder="mb_…" value="${escapeAttr(state.settings.token)}" /></label>
    <button id="save" class="secondary">保存并连接</button></section>
    <section class="card ${hasMagnet ? '' : 'empty'}"><h2>已捕获的磁力链接</h2>
      ${hasMagnet ? `<p class="title">${escapeHtml(state.magnet?.title || '当前页面资源')}</p><code>${escapeHtml(state.magnet?.value || '')}</code>
      <label>目标媒体库<select id="library"><option value="">请选择</option>${state.libraries.map((library) => `<option value="${escapeAttr(library.name)}">${escapeHtml(library.name)}</option>`).join('')}</select></label>
      <div class="actions"><button id="submit" ${configured && state.libraries.length && !state.isSubmitting ? '' : 'disabled'}>${state.isSubmitting ? '<span class="spinner" aria-hidden="true"></span>正在发送…' : '发送到 MediaBridge'}</button><button id="discard" class="secondary" ${state.isSubmitting ? 'disabled' : ''}>取消</button></div>` : '<p>点击页面中的“复制磁力链接”按钮后，链接会显示在这里；插件不会自动提交。</p><button id="read-clipboard" class="secondary">读取剪贴板中的磁力链接</button>'}
    </section><p id="notice" class="notice"></p>`
  document.querySelector('#save')?.addEventListener('click', () => void saveSettings())
  document.querySelector('#submit')?.addEventListener('click', () => void submitTask())
  document.querySelector('#read-clipboard')?.addEventListener('click', () => void readClipboardManually())
  document.querySelector('#discard')?.addEventListener('click', () => void discardCapturedMagnet())
}

async function start() {
  const stored = await chrome.storage.local.get('settings')
  state.settings = stored.settings || state.settings
  state.magnet = await loadCapturedMagnet()
  render()
  await loadLibraries()
}

void start()
