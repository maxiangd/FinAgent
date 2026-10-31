// 统一的 fetch 封装（vite dev 代理 /api -> http://127.0.0.1:8000）
import { ElMessage } from 'element-plus'

export async function request(path, options = {}) {
  const res = await fetch(path, options)
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
