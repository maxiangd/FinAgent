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

// 分析窗口结束日买入后：到观察日的涨幅 + 固定持有期收益（默认 T+1/T+5/T+10/T+20）
export async function fetchPaperBacktest(taskId, { asOf, horizons = '1,5,10,20' } = {}) {
  const params = new URLSearchParams({ horizons })
  if (asOf) params.set('as_of', asOf)
  return request(`/api/paper/backtest/${taskId}?${params.toString()}`)
}
