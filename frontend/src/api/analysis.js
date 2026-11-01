// 分析接口：数据接入、任务、模型提供商
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

// 创建异步分析任务，返回 { task_id, status, ... }
export async function createAnalysisTask(payload, { signal } = {}) {
  return request('/api/analysis/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
    timeoutMs: 30_000,
  })
}

// 查询任务状态与最终结果
export async function getAnalysisTask(taskId) {
  return request(`/api/analysis/tasks/${taskId}`)
}

// 最近的分析任务列表
export async function fetchRecentTasks(limit = 10) {
  return request(`/api/analysis/tasks?limit=${limit}`)
}

// 请求取消运行中的任务
export async function cancelAnalysisTask(taskId) {
  return request(`/api/analysis/tasks/${taskId}/cancel`, { method: 'POST' })
}

// SSE 事件流地址（EventSource 直接用）
export const analysisTaskEventsUrl = (taskId) => `/api/analysis/tasks/${taskId}/events`

// 已配置 API Key 的模型提供商；key 用于随分析请求提交
export async function fetchLLMProviders() {
  return request('/api/analysis/providers')
}
