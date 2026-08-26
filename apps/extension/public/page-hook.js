/**
 * @description 页面钩子（MAIN world 注入）
 * @responsibility 劫持页面剪贴板写入/copy 行为，把可能的磁力链接
 *               通过 postMessage 转发给 isolated world 的 capture.js；
 *               判定规则复用 magnet.js（模块方式加载，见 vite 打包）
 */
import { normalizeMagnet } from './magnet.js'

const emit = (value) => {
  const magnet = normalizeMagnet(value)
  if (magnet) window.postMessage({ source: 'mediabridge-page-hook', type: 'magnet-copied', value: magnet }, '*')
}

// 读取当前选中文本（输入框内选中优先，其次页面选区）
const selectedText = () => {
  const active = document.activeElement
  if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) {
    const start = active.selectionStart ?? 0
    const end = active.selectionEnd ?? active.value.length
    return active.value.slice(start, end)
  }
  return window.getSelection()?.toString() || ''
}

try {
  const originalWriteText = navigator.clipboard?.writeText?.bind(navigator.clipboard)
  if (originalWriteText) {
    navigator.clipboard.writeText = (value) => {
      emit(value)
      return originalWriteText(value)
    }
  }
  const originalWrite = navigator.clipboard?.write?.bind(navigator.clipboard)
  if (originalWrite) {
    navigator.clipboard.write = (items) => {
      for (const item of items) {
        if (item.types?.includes('text/plain')) {
          item.getType('text/plain').then((blob) => blob.text()).then(emit).catch(() => {})
        }
      }
      return originalWrite(items)
    }
  }
} catch { /* A page may expose a read-only Clipboard implementation. */ }

try {
  const originalExecCommand = document.execCommand.bind(document)
  document.execCommand = (command, ...args) => {
    const isCopy = String(command).toLowerCase() === 'copy'
    const beforeCopy = isCopy ? selectedText() : ''
    const result = originalExecCommand(command, ...args)
    if (isCopy) {
      emit(beforeCopy)
      window.setTimeout(() => emit(selectedText()), 0)
    }
    return result
  }
} catch { /* A page may expose a read-only execCommand implementation. */ }

document.addEventListener('copy', (event) => {
  emit(event.clipboardData?.getData('text/plain'))
  // execCommand('copy') and some libraries populate clipboardData after the
  // capture phase. Tell the isolated script to verify the final clipboard.
  window.setTimeout(() => window.postMessage({ source: 'mediabridge-page-hook', type: 'copy-event' }, '*'), 0)
}, true)
