// 分析接口：数据接入、行情分析师、模型提供商
import { request } from './http'

// 执行一次真实的数据接入预览，日期范围由页面当前选择传入
export async function fetchDataIngestion(payload, { signal } = {}) {
  return request('/api/analysis/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

// 调用真实行情分析师；只分析请求对应的股票与日期范围
export async function fetchMarketAnalysis(payload, { signal } = {}) {
  return request('/api/analysis/market', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

// 已配置 API Key 的模型提供商；key 用于随分析请求提交
export async function fetchLLMProviders() {
  return request('/api/analysis/providers')
}
