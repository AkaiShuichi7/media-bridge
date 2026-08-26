/**
 * @description 公共模块（magnet.js / captured-state.js）的类型声明
 * @responsibility 让 src/popup.ts 以类型安全的方式复用 public 下的共享模块
 */

declare module '*/magnet.js' {
  /** 判定字符串是否为有效磁力链接 */
  export function isMagnetLink(value: unknown): boolean
  /** 规范化磁力链接；非磁力返回 null */
  export function normalizeMagnet(value: unknown): string | null
}

declare module '*/captured-state.js' {
  /** 写入捕获的磁力并同步 badge；返回是否真正写入 */
  export function storeCapturedMagnet(rawValue: string, title?: string): Promise<boolean>
  /** 清除待发送磁力并同步 badge */
  export function clearCapturedMagnet(): Promise<void>
  /** 读取待发送磁力；无捕获时 undefined */
  export function loadCapturedMagnet(): Promise<{ value: string; title?: string } | undefined>
  /** 应用启动时校准 badge 与存储的一致性 */
  export function syncBadgeFromStorage(): Promise<void>
}
