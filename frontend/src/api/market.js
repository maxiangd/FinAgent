// 行情接口：快照、K 线、搜索
import { request } from './http'

// 行情快照（名称/最新价/涨跌幅/财务/原始新闻），字段兼容前端 selected
export async function fetchSnapshot(code) {
  return request(`/api/stock/${code}/snapshot`)
}

// 获取指定周期的前复权 K 线；可附日期区间与指标预热 K 线
export async function fetchKline(code, period = 'daily', range = null, warmupBars = 0) {
  const params = new URLSearchParams({ period })
  if (Array.isArray(range) && range.length === 2) {
    params.set('start_date', range[0])
    params.set('end_date', range[1])
  }
  if (warmupBars > 0) params.set('warmup_bars', String(warmupBars))
  return request(`/api/stock/${code}/kline?${params.toString()}`)
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
