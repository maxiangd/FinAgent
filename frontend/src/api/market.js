// 后端数据 API 封装（vite dev 代理 /api -> http://127.0.0.1:8000）
import { ElMessage } from 'element-plus'

async function request(path) {
  const res = await fetch(path)
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

// 行情快照（名称/最新价/涨跌幅/财务/原始新闻），字段兼容前端 selected
export async function fetchSnapshot(code) {
  return request(`/api/stock/${code}/snapshot`)
}

// 日K 线（前复权，默认近 ~520 个交易日），填充 selected.kline / dates
export async function fetchKline(code, limit = 520) {
  return request(`/api/stock/${code}/kline?limit=${limit}`)
}

// 按代码或名称搜索股票，返回 [{code, name}] 候选
export async function searchStock(q) {
  return request(`/api/search?q=${encodeURIComponent(q)}`)
}

// 加载完整标的数据：快照 + K线，组装为前端 selected 结构
export async function loadStock(code) {
  const [snap, kl] = await Promise.all([fetchSnapshot(code.trim()), fetchKline(code.trim())])
  return { ...snap, kline: kl.items, dates: kl.dates }
}

export function showApiError(e) {
  ElMessage.error(`数据获取失败：${e.message || e}`)
}
