// 统一的 fetch 封装（vite dev 代理 /api -> http://127.0.0.1:8000）
import { ElMessage } from 'element-plus'

// 默认 180 秒：模型分析通常 10-30 秒，超时后明确报错而不是一直等
const DEFAULT_TIMEOUT_MS = 180_000

export async function request(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = options
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const forwardAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', forwardAbort, { once: true })
  }

  let res
  try {
    res = await fetch(path, { ...rest, signal: controller.signal })
  } catch (e) {
    if (timedOut) throw new Error(`请求超时（${Math.round(timeoutMs / 1000)} 秒未响应）`)
    throw e
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', forwardAbort)
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}

export function showApiError(e) {
  ElMessage.error(`数据获取失败：${e.message || e}`)
}
