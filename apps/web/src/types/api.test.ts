// 任务状态契约回归测试
// 云端契约（与后端 monitor.py 一致）：2=完成，负数（如 -1）=失败，其余（0/1 等）=进行中。
// 后端对 115 原始状态值透传，负数语义只在 UI 判定层归一化。
import { describe, it, expect } from 'vitest'
import { isTaskFailed, isTaskCompleted, isTaskPending, TASK_STATUS } from './api'

describe('isTaskFailed：所有负数状态都判定为失败', () => {
  it('-1 判定为失败', () => {
    expect(isTaskFailed(-1)).toBe(true)
  })

  it('其他负数（-2、-3）同样判定为失败', () => {
    expect(isTaskFailed(-2)).toBe(true)
    expect(isTaskFailed(-3)).toBe(true)
  })

  it('0、1、2 不判定为失败', () => {
    expect(isTaskFailed(0)).toBe(false)
    expect(isTaskFailed(1)).toBe(false)
    expect(isTaskFailed(2)).toBe(false)
  })
})

describe('isTaskCompleted：仅 2 判定为完成', () => {
  it('2 判定为完成', () => {
    expect(isTaskCompleted(TASK_STATUS.COMPLETED)).toBe(true)
  })

  it('0、1 与负数均不判定为完成', () => {
    expect(isTaskCompleted(0)).toBe(false)
    expect(isTaskCompleted(1)).toBe(false)
    expect(isTaskCompleted(-1)).toBe(false)
  })
})

describe('isTaskPending：非完成且非失败均为进行中', () => {
  it('0 与 1 均判定为进行中（1 不是失败）', () => {
    expect(isTaskPending(0)).toBe(true)
    expect(isTaskPending(1)).toBe(true)
  })

  it('2 与负数不判定为进行中', () => {
    expect(isTaskPending(2)).toBe(false)
    expect(isTaskPending(-1)).toBe(false)
  })
})

describe('三个判定函数对任意状态互斥且完备', () => {
  it('任意整数状态恰好命中一个分类', () => {
    const statuses = [-5, -2, -1, 0, 1, 2, 3, 100]
    for (const status of statuses) {
      const hits = [isTaskFailed(status), isTaskCompleted(status), isTaskPending(status)]
        .filter(Boolean).length
      expect(hits, `status=${status} 应恰好命中一个分类`).toBe(1)
    }
  })
})
