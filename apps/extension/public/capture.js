/**
 * @description 捕获脚本（isolated world 注入）
 * @responsibility 消费 page-hook 转发的复制事件与页面点击启发式，
 *               判定与状态写入分别复用 magnet.js 与 captured-state.js，
 *               本文件只保留事件接线和去抖
 */
import { normalizeMagnet } from './magnet.js'
import { storeCapturedMagnet } from './captured-state.js'

// 去抖状态：同一磁力 2 秒内只记录一次
let lastCapturedValue = ''
let lastCapturedAt = 0
// 剪贴板探测节流：500ms 一次
let lastClipboardProbeAt = 0

/**
 * 捕获磁力：判定 → 去抖 → 写入共享状态 → 通知 service worker。
 *
 * @param {string} rawValue 原始捕获值
 */
const capture = async (rawValue) => {
  const value = normalizeMagnet(rawValue)
  if (!value) return
  const now = Date.now()
  if (value === lastCapturedValue && now - lastCapturedAt < 2000) return
  lastCapturedValue = value
  lastCapturedAt = now
  const stored = await storeCapturedMagnet(value, document.title)
  if (stored) chrome.runtime.sendMessage({ type: 'magnet-captured' })
}

/**
 * 从点击目标周边 DOM 启发式提取磁力链接。
 *
 * 优先级：data-clipboard-text 属性 → 磁力锚点 href → 同行兄弟磁力锚点。
 * 只检查直接所在的下载行，避免任意祖先扫描造成误报。
 *
 * @param {EventTarget | null} target 点击目标
 * @returns {string | null} 磁力链接或 null
 */
const findContextualMagnet = (target) => {
  if (!(target instanceof Element)) return null
  const clipboardValue = target.closest('[data-clipboard-text]')?.getAttribute('data-clipboard-text')
  if (clipboardValue) return clipboardValue
  const directLink = target.closest('a[href^="magnet:"]')
  if (directLink) return directLink.getAttribute('href')

  // The site's copy icon is an <i> sibling of the magnet <a> in the same
  // download-row <li>. Deliberately inspect only that immediate row.
  const copyControl = target.closest('i, button, [role="button"], [data-copy], [class*="copy"]')
  const row = copyControl?.parentElement
  const siblingLink = row?.querySelector(':scope > a[href^="magnet:"]')
  return siblingLink?.getAttribute('href') || null
}

/**
 * 通过 service worker 的 offscreen 文档读取剪贴板并捕获（带节流）。
 */
const probeClipboard = () => {
  const now = Date.now()
  if (now - lastClipboardProbeAt < 500) return
  lastClipboardProbeAt = now
  chrome.runtime.sendMessage({ type: 'read-clipboard' }, (response) => void capture(response?.text))
}

window.addEventListener('message', (event) => {
  if (event.source !== window || event.data?.source !== 'mediabridge-page-hook') return
  if (event.data?.type === 'magnet-copied') void capture(event.data.value)
  if (event.data?.type === 'copy-event') probeClipboard()
})

// Some sites render a styled copy control inside an ordinary magnet anchor.
// The magnet is not visible in the UI, but is still available as the href.
document.addEventListener('click', (event) => {
  void capture(findContextualMagnet(event.target))
}, true)
