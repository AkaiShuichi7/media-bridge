/**
 * @description 捕获状态模块（唯一实现）
 * @responsibility 收敛「待发送磁力」状态的写入与清除，独占维护
 *               badge 与 chrome.storage 的同步不变量；
 *               capture.js / popup.ts / service-worker 均通过本模块操作状态
 */

import { normalizeMagnet } from './magnet.js'

/**
 * 写入捕获的磁力链接（含来源页标题），并同步 badge。
 *
 * @param {string} rawValue 页面捕获到的原始值（可能带空白/非磁力）
 * @param {string} title 来源页面标题
 * @returns {boolean} 是否真正写入（非磁力或重复触发返回 false）
 */
export async function storeCapturedMagnet(rawValue, title = '') {
  const value = normalizeMagnet(rawValue)
  if (!value) return false
  await chrome.storage.local.set({ capturedMagnet: { value, title } })
  await chrome.action.setBadgeText({ text: '1' })
  return true
}

/**
 * 清除待发送磁力（提交成功 / 用户取消后调用），并同步 badge。
 */
export async function clearCapturedMagnet() {
  await chrome.storage.local.remove('capturedMagnet')
  await chrome.action.setBadgeText({ text: '' })
}

/**
 * 读取待发送磁力；无捕获时返回 undefined。
 *
 * @returns {Promise<{value: string, title?: string} | undefined>}
 */
export async function loadCapturedMagnet() {
  const { capturedMagnet } = await chrome.storage.local.get('capturedMagnet')
  return capturedMagnet
}

/**
 * 应用启动时校准 badge（恢复与存储一致的状态）。
 */
export async function syncBadgeFromStorage() {
  const captured = await loadCapturedMagnet()
  await chrome.action.setBadgeText({ text: captured ? '1' : '' })
}
