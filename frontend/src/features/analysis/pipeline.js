// 流水线状态；当前先真实执行数据接入阶段。

import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { STAGES } from './content'
import { fetchDataIngestion, fetchFullAnalysis } from '../../api/analysis'

const STANCE_TEXT = { bullish: '偏多', neutral: '中性', bearish: '偏空' }
const ACTION_TEXT = { buy: '买入', hold: '持有', reduce: '减仓', avoid: '回避' }
const DECISION_TEXT = { approve: '通过', revise: '需修改', reject: '否决' }

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
    pushEvent('analyst', '多智能体链路', '正在执行分析师、辩论、交易、风控与 PM 决策…')
    const run = await fetchFullAnalysis(request, { signal: controller.signal })
    if (guard()) return

    state.completed.ingest = run.ingestion || result
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

    const stance = (report) => STANCE_TEXT[report?.stance] || '未给出'
    pushEvent(
      'analyst',
      '分析师团队',
      `三份研报：行情 ${stance(run.market_report)} · 基本面 ${stance(run.fundamental_report)} · 新闻 ${stance(run.news_report)}。`,
      'success',
    )
    if (run.debate_turns?.length) {
      pushEvent('debate', '多空研究员', `完成 ${run.debate_turns.length} 条辩论发言。`, 'success')
    }
    if (run.trade_proposal) {
      pushEvent('trader', '交易员', `提案：${ACTION_TEXT[run.trade_proposal.action] || run.trade_proposal.action}。`, 'success')
    }
    if (run.risk_reviews?.length) {
      const decisions = run.risk_reviews.map((review) => DECISION_TEXT[review.decision] || review.decision)
      pushEvent('risk', '风控评审', `三类风控意见：${decisions.join(' / ')}。`, 'success')
    }
    if (run.pm_decision) {
      const action = ACTION_TEXT[run.pm_decision.action] || run.pm_decision.action
      pushEvent('pm', 'PM 决策', `最终结论：${action}（置信度 ${Math.round(run.pm_decision.confidence * 100)}%）。`, 'success')
    }
    state.finished = true
  } catch (e) {
    if (e.name !== 'AbortError' && runId === myRun) {
      const message = e.message || String(e)
      pushEvent('system', '系统', `执行异常：${message}`, 'error')
      // 事件流在右侧，容易漏看；同时用弹窗提示，避免误以为卡住
      ElMessage.error(`分析失败：${message}`)
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
