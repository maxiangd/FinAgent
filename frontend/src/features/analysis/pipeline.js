// 分析流水线：创建后台任务并订阅 SSE，阶段进度实时更新。

import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { STAGES } from './content'
import {
  analysisTaskEventsUrl,
  cancelAnalysisTask,
  createAnalysisTask,
  getAnalysisTask,
} from '../../api/analysis'

const now = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export const state = reactive({
  selected: null, // 当前股票
  running: false,
  finished: false,
  currentIndex: -1, // 正在执行的阶段下标
  completed: {}, // { [stageKey]: 该阶段生成的结构化数据 }
  events: [], // 事件日志（来自后端 SSE）
  elapsed: 0, // 运行耗时(秒)
  taskId: null,
})

// 行情图表偏好（全局响应式，供 Home / KLineChart 直接读写，绕过 prop 链路）
export const chartPrefs = reactive({
  showMA: true,
  indicator: 'macd',
  rangeBox: false, // 区间最高/最低的箱体虚线（默认只显示两个小箭头）
})

const STAGE_INDEX = Object.fromEntries(STAGES.map((stage, index) => [stage.key, index]))
const STAGE_LABEL = Object.fromEntries(STAGES.map((stage) => [stage.key, stage.label]))
const LAST_TASK_KEY = 'finagent:lastTask'

export function saveLastTask(taskId) {
  try {
    localStorage.setItem(LAST_TASK_KEY, JSON.stringify({ taskId, savedAt: Date.now() }))
  } catch {
    /* 隐私模式下可能不可用，忽略即可 */
  }
}

export function readLastTask() {
  try {
    return JSON.parse(localStorage.getItem(LAST_TASK_KEY) || 'null')
  } catch {
    return null
  }
}

export function clearLastTask() {
  try {
    localStorage.removeItem(LAST_TASK_KEY)
  } catch {
    /* ignore */
  }
}

let runId = 0
let timer = null
let activeSource = null
let activeTaskId = null

function pushEvent(stageKey, agent, text, type = 'info') {
  state.events.unshift({ id: Symbol('e'), time: now(), stage: stageKey, agent, text, type })
  // 防止事件无限增长
  if (state.events.length > 200) state.events.pop()
}

export function selectStock(stock) {
  stopAnalysis()
  state.selected = stock
  state.completed = {}
  state.events = []
  state.finished = false
  state.currentIndex = -1
  state.elapsed = 0
  state.taskId = null
}

export function stopAnalysis() {
  runId++
  state.running = false
  state.currentIndex = -1
  if (activeSource) {
    activeSource.close()
    activeSource = null
  }
  if (activeTaskId) {
    cancelAnalysisTask(activeTaskId).catch(() => {})
    activeTaskId = null
  }
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function beginRun() {
  state.running = true
  state.finished = false
  state.completed = {}
  state.events = []
  state.elapsed = 0
  state.currentIndex = 0
  timer = setInterval(() => {
    if (state.running) state.elapsed++
  }, 1000)
}

function endRun(myRun) {
  if (runId !== myRun) return
  state.running = false
  state.currentIndex = -1
  activeTaskId = null
  if (activeSource) {
    activeSource.close()
    activeSource = null
  }
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

export async function startAnalysis(request) {
  const stock = state.selected
  if (!stock || state.running) return

  stopAnalysis()
  const myRun = ++runId
  beginRun()

  try {
    const task = await createAnalysisTask(request)
    if (runId !== myRun) {
      cancelAnalysisTask(task.task_id).catch(() => {})
      return
    }
    activeTaskId = task.task_id
    state.taskId = task.task_id
    saveLastTask(task.task_id)
    pushEvent('system', '任务', `任务 ${task.task_id.slice(0, 8)} 已创建，开始执行。`)
    await followTask(task.task_id, myRun)
  } catch (e) {
    if (runId === myRun) reportError(e)
  } finally {
    endRun(myRun)
  }
}

export async function resumeTask(taskId) {
  if (state.running) return
  stopAnalysis()
  const myRun = ++runId
  beginRun()
  activeTaskId = taskId
  state.taskId = taskId
  saveLastTask(taskId)
  pushEvent('system', '任务', `已恢复任务 ${taskId.slice(0, 8)} 的订阅。`)
  try {
    await followTask(taskId, myRun)
  } catch (e) {
    if (runId === myRun) reportError(e)
  } finally {
    endRun(myRun)
  }
}

export function applyTaskResult(result) {
  applyResult(result)
}

function followTask(taskId, myRun) {
  return new Promise((resolve, reject) => {
    const seen = new Set()
    const source = new EventSource(analysisTaskEventsUrl(taskId))
    activeSource = source

    source.onmessage = (message) => {
      if (runId !== myRun) {
        source.close()
        resolve()
        return
      }
      let event
      try {
        event = JSON.parse(message.data)
      } catch {
        return
      }
      if (seen.has(event.event_id)) return // 断线重连时不重复处理
      seen.add(event.event_id)
      handleEvent(event)

      if (event.event_type === 'task_completed') {
        source.close()
        getAnalysisTask(taskId)
          .then((task) => {
            applyResult(task.result)
            resolve()
          })
          .catch(reject)
      } else if (event.event_type === 'task_failed') {
        source.close()
        reject(new Error(event.message || '分析失败'))
      } else if (event.event_type === 'task_cancelled') {
        source.close()
        resolve()
      }
    }

    source.onerror = () => {
      // 服务端在任务结束后会关闭连接；运行中则由 EventSource 自动重连
      if (runId !== myRun) {
        source.close()
        resolve()
      }
    }
  })
}

function handleEvent(event) {
  const stage = event.stage
  if (event.event_type === 'stage_started' && stage) {
    state.currentIndex = STAGE_INDEX[stage] ?? state.currentIndex
    pushEvent(stage, STAGE_LABEL[stage] || stage, event.message || '开始执行。')
    return
  }
  if (event.event_type === 'stage_completed' && stage) {
    // 事件里带上了该阶段的结果，收到即可渲染，不必等整条任务结束
    applyStagePayload(stage, event.payload || {})
    pushEvent(stage, STAGE_LABEL[stage] || stage, event.message || '完成。', 'success')
    return
  }
  if (event.event_type === 'task_queued' || event.event_type === 'task_started') {
    pushEvent('system', '任务', event.message || '')
    return
  }
  if (event.event_type === 'task_completed') {
    pushEvent('system', '任务', event.message || '分析完成。', 'success')
  }
}

function applyStagePayload(stage, payload) {
  if (stage === 'ingest' && payload.ingestion) {
    state.completed.ingest = payload.ingestion
  } else if (stage === 'analyst' && payload.analyst) {
    state.completed.analyst = payload.analyst
  } else if (stage === 'debate' && payload.debate_turns) {
    state.completed.debate = payload.debate_turns.length ? payload.debate_turns : null
  } else if (stage === 'trader' && payload.trade_proposal) {
    state.completed.trader = payload.trade_proposal
  } else if (stage === 'risk' && payload.risk_reviews) {
    state.completed.risk = payload.risk_reviews.length ? payload.risk_reviews : null
  } else if (stage === 'pm' && payload.pm_decision) {
    state.completed.pm = payload.pm_decision
  }
}

function applyResult(run) {
  if (!run) return
  state.completed.ingest = run.ingestion || null
  state.completed.analyst = {
    report: run.market_report,
    stock_name: run.stock_name,
    stock_code: run.stock_code,
    period: run.period,
    actual_start_date: run.actual_start_date,
    actual_end_date: run.actual_end_date,
    model_name: run.model_names?.market,
    limitations: run.limitations,
    evidence: run.evidence,
    fundamental_report: run.fundamental_report,
    news_report: run.news_report,
  }
  state.completed.debate = run.debate_turns?.length ? run.debate_turns : null
  state.completed.trader = run.trade_proposal || null
  state.completed.risk = run.risk_reviews?.length ? run.risk_reviews : null
  state.completed.pm = run.pm_decision || null
  state.finished = true
}

function reportError(e) {
  if (e?.name === 'AbortError') return
  const message = e?.message || String(e)
  pushEvent('system', '系统', `执行异常：${message}`, 'error')
  ElMessage.error(`分析失败：${message}`)
}

export function progressPercent() {
  const done = STAGES.filter((s) => state.completed[s.key]).length
  return Math.round((done / STAGES.length) * 100)
}
