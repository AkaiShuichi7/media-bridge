/**
 * @description 磁力链接判定规则（唯一实现）
 * @responsibility 提供 isMagnetLink 判定函数，供 page-hook / capture / popup
 *               三个上下文复用；判定规则变更只改这一处
 */

/**
 * 判定字符串是否为有效的磁力链接（BT info_hash 形式）。
 *
 * 匹配示例：magnet:?xt=urn:btih:…（大小写不敏感，允许首尾空白）
 *
 * @param {unknown} value 待判定值（非字符串直接返回 false）
 * @returns {boolean} 是否为磁力链接
 */
export function isMagnetLink(value) {
  return typeof value === 'string' && /^magnet:\?xt=urn:btih:/i.test(value.trim())
}

/**
 * 规范化磁力链接（去首尾空白）；非磁力链接返回 null。
 *
 * @param {unknown} value 待规范化值
 * @returns {string | null} 规范化后的磁力链接，或 null
 */
export function normalizeMagnet(value) {
  if (!isMagnetLink(value)) return null
  return value.trim()
}
