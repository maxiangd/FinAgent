// 智能体接口：分析任务与模型提供商（/api/agent）
import { request } from './http'

// 创建异步分析任务，返回 { task_id, status, ... }
export async function createAnalysisTask(payload, { signal } = {}) {
  return request('/api/agent/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
    timeoutMs: 30_000,
  })
}

// 查询任务状态与最终结果
export async function getAnalysisTask(taskId) {
  return request(`/api/agent/tasks/${taskId}`)
}

// 最近的分析任务列表
export async function fetchRecentTasks(limit = 10) {
  return request(`/api/agent/tasks?limit=${limit}`)
}

// 请求取消运行中的任务
export async function cancelAnalysisTask(taskId) {
  return request(`/api/agent/tasks/${taskId}/cancel`, { method: 'POST' })
}

// 删除已结束的任务及其报告
export async function deleteAnalysisTask(taskId) {
  return request(`/api/agent/tasks/${taskId}`, { method: 'DELETE' })
}

// 批量删除已结束的任务；返回 { deleted: [...], skipped: [...] }
export async function deleteAnalysisTasks(taskIds) {
  return request('/api/agent/tasks/batch-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_ids: taskIds }),
  })
}

// SSE 事件流地址（EventSource 直接用）
export const analysisTaskEventsUrl = (taskId) => `/api/agent/tasks/${taskId}/events`

// 已配置 API Key 的模型提供商；key 用于随分析请求提交
export async function fetchLLMProviders() {
  return request('/api/providers')
}

// 分析链路中的 Agent 角色，用于按角色分配模型
export async function fetchAgentOptions() {
  return request('/api/providers/agents')
}
