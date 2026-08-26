/**
 * @description 扩展后台 service worker
 * @responsibility 剪贴板 offscreen 读取的中转与 popup 唤起；
 *               badge 状态统一由 captured-state.js 维护，本文件不再直接写 badge
 */
import { syncBadgeFromStorage } from './captured-state.js'

// 进行中的剪贴板读取请求（requestId → Promise 句柄）
const clipboardRequests = new Map()
// popup 唤起节流
let lastPopupOpenedAt = 0

/**
 * 确保 offscreen 文档存在（懒创建）。
 */
async function ensureOffscreenDocument() {
  if (await chrome.offscreen.hasDocument()) return
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['CLIPBOARD'],
    justification: 'Read a magnet link only after the user clicks a copy control.',
  })
}

/**
 * 经 offscreen 文档读取剪贴板文本。
 *
 * @returns {Promise<string>} 剪贴板文本（失败时 resolve 空串由调用方判定）
 */
async function readClipboard() {
  await ensureOffscreenDocument()
  const requestId = crypto.randomUUID()
  return new Promise((resolve, reject) => {
    clipboardRequests.set(requestId, { resolve, reject })
    chrome.runtime.sendMessage({ type: 'offscreen-read-clipboard', requestId })
  })
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'magnet-captured') {
    // badge 已由 captured-state.storeCapturedMagnet 同步，这里只负责唤起 popup
    // Chrome 127+ lets an extension open its action popup from this user
    // initiated capture path. Older browsers keep the badge as a fallback.
    if (typeof chrome.action.openPopup === 'function' && Date.now() - lastPopupOpenedAt > 500) {
      lastPopupOpenedAt = Date.now()
      chrome.action.openPopup().catch(() => {})
    }
  }
  if (message?.type === 'clipboard-read-result') {
    const request = clipboardRequests.get(message.requestId)
    if (!request) return
    clipboardRequests.delete(message.requestId)
    if (message.error) request.reject(new Error(message.error))
    else request.resolve(message.text)
  }
  if (message?.type === 'read-clipboard') {
    readClipboard().then((text) => sendResponse({ text })).catch(() => sendResponse({ text: '' }))
    return true
  }
})

// 启动时校准 badge 与存储的一致性
chrome.runtime.onStartup.addListener(() => void syncBadgeFromStorage())
