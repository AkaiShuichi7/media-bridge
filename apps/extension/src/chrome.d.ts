/**
 * @description chrome.* API 的最小类型声明（无 @types/chrome 依赖）
 * @responsibility 为 popup.ts 使用的 chrome API 子集提供类型，
 *               包括 runtime.getManifest（版本号唯一来源）
 */
declare const chrome: {
  permissions: {
    request: (permissions: { origins: string[] }) => Promise<boolean>
  }
  storage: {
    local: {
      get: (keys: string | string[]) => Promise<Record<string, any>>
      set: (items: Record<string, any>) => Promise<void>
      remove: (keys: string | string[]) => Promise<void>
    }
  }
  action: {
    setBadgeText: (details: { text: string }) => Promise<void>
  }
  runtime: {
    sendMessage: (message: unknown) => void
    onMessage: { addListener: (listener: (message: any) => void) => void }
    onStartup: { addListener: (listener: () => void) => void }
    /** 读取 manifest.json（version 等元信息的唯一来源） */
    getManifest: () => { version: string }
  }
}
