// 流水线状态；当前先真实执行数据接入阶段。

import { reactive } from 'vue'
import { STAGES } from './content'
import { fetchDataIngestion, fetchMarketAnalysis } from '../../api/analysis'

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
  events: [], // SSE 风格事件日志
  elapsed: 0, // 运行耗时(秒)
})

// 行情图表偏好（全局响应式，供 Home / KLineChart 直接读写，绕过 prop 链路）
export const chartPrefs = reactive({
  showMA: true,
  indicator: 'macd',
  rangeBox: false, // 区间最高/最低的箱体虚线（默认只显示两个小箭头）
})

let runId = 0
let timer = null
let activeController = null

function pushEvent(stageKey, agent, text, type = 'info') {
  state.events.unshift({ id: Symbol('e'), time: now(), stage: stageKey, agent, text, type })
  // 防止事件无限增长
  if (state.events.length > 200) state.events.pop()
}

export function selectStock(stock) {
  stopDataIngestion()
  state.selected = stock
  state.completed = {}
  state.events = []
  state.finished = false
  state.currentIndex = -1
  state.elapsed = 0
  state.progress = 0
}

export function stopDataIngestion() {
  runId++
  state.running = false
  state.currentIndex = -1
  if (activeController) {
    activeController.abort()
    activeController = null
  }
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

export async function startDataIngestion(request) {
  const s = state.selected
  if (!s || state.running) return

  stopDataIngestion()
  const myRun = ++runId
  const controller = new AbortController()
  activeController = controller

  state.running = true
  state.finished = false
  state.completed = {}
  state.events = []
  state.elapsed = 0
  state.currentIndex = 0

  timer = setInterval(() => {
    if (state.running) state.elapsed++
  }, 1000)

  const guard = () => runId !== myRun // 被新任务/停止打断

  try {
    state.currentIndex = 0
    const rangeText = request.start_date && request.end_date
      ? `${request.start_date} 至 ${request.end_date}`
      : '最新可用区间'
    pushEvent('ingest', '数据接入', `正在接入 ${s.name}（${s.code}）${request.period} 数据，${rangeText}…`)
    const result = await fetchDataIngestion(request, { signal: controller.signal })
    if (guard()) return
    state.completed.ingest = result
    const klineItem = result.items?.find((item) => item.name === 'K线行情')
    pushEvent(
      'ingest',
      '数据接入',
      klineItem?.note || '行情、基本面与新闻数据已返回。',
      'success',
    )

    state.currentIndex = 1
    pushEvent('analyst', '行情分析师', '正在调用模型分析所选区间…')
    const analysis = await fetchMarketAnalysis(request, { signal: controller.signal })
    if (guard()) return
    state.completed.analyst = analysis
    const stanceText = ({ bullish: '偏多', neutral: '中性', bearish: '偏空' })[
      analysis.report?.stance
    ] || '已生成报告'
    pushEvent(
      'analyst',
      '行情分析师',
      `${analysis.provider ? `${analysis.provider} · ` : ''}${analysis.model_name} 已完成分析：${stanceText}。`,
      'success',
    )
    state.finished = true
  } catch (e) {
    if (e.name !== 'AbortError' && runId === myRun) {
      pushEvent('system', '系统', `执行异常：${e.message}`, 'error')
    }
  } finally {
    if (runId === myRun) {
      state.running = false
      state.currentIndex = -1
      activeController = null
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }
}

export function progressPercent() {
  const done = STAGES.filter((s) => state.completed[s.key]).length
  return Math.round((done / STAGES.length) * 100)
}
