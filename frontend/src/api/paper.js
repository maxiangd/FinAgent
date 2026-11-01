// 模拟交易接口（研究演示，不接入真实下单）
import { request } from './http'

export async function fetchPaperPortfolio() {
  return request('/api/paper/portfolio')
}

export async function openPaperPosition(taskId, quantity) {
  return request('/api/paper/positions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, quantity }),
  })
}

export async function closePaperPosition(positionId) {
  return request(`/api/paper/positions/${positionId}/close`, { method: 'POST' })
}

export async function resetPaperAccount() {
  return request('/api/paper/reset', { method: 'POST' })
}
