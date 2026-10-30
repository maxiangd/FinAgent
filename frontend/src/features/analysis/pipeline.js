// 流水线状态与模拟执行引擎（模拟 SSE 事件流）
// 后续接入 FastAPI + LangGraph 后端后：startSimulation 改为发起真实任务，
// 并通过 EventSource 消费 /api/tasks/{id}/events 推送的事件填充同一份状态。

import { reactive } from 'vue'
import {
  STAGES,
  genIngest,
  genAnalysts,
  genDebate,
  genProposal,
  genRisk,
  genDecision,
} from './content'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

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

function pushEvent(stageKey, agent, text, type = 'info') {
  state.events.unshift({ id: Symbol('e'), time: now(), stage: stageKey, agent, text, type })
  // 防止事件无限增长
  if (state.events.length > 200) state.events.pop()
}

function stageLabel(key) {
  return STAGES.find((s) => s.key === key)?.label ?? key
}

export function selectStock(stock) {
  stopSimulation()
  state.selected = stock
  state.completed = {}
  state.events = []
  state.finished = false
  state.currentIndex = -1
  state.elapsed = 0
  state.progress = 0
}

export function stopSimulation() {
  runId++
  state.running = false
  state.currentIndex = -1
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

export async function startSimulation() {
  const s = state.selected
  if (!s || state.running) return

  const myRun = ++runId
  stopSimulation()
  runId = myRun

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

  // ---------- 阶段 1：数据接入 ----------
  try {
    state.currentIndex = 0
    pushEvent('ingest', '数据接入', `正在获取 ${s.name}(${s.code}) 行情、财务、新闻数据…`)
    await sleep(500)
    if (guard()) throw new Error('cancelled')
    state.completed.ingest = genIngest(s)
    pushEvent('ingest', '数据接入', `行情/财务数据就绪（${(s.news ?? []).length} 条原始新闻；新闻分析模型待接入）`, 'success')

    // ---------- 阶段 2：分析师研报 ----------
    state.currentIndex = 1
    const analysts = genAnalysts(s)
    pushEvent('analyst', '分析师', `${s.name} 技术面 / 基本面 / 新闻面分析启动`)
    await sleep(600)
    if (guard()) throw new Error('cancelled')
    for (const a of analysts) {
      if (guard()) throw new Error('cancelled')
      const result = a.rating == null ? '原始新闻已展示，模型分析待接入' : `评分 ${a.rating}`
      pushEvent('analyst', a.agent, `完成${a.group}分析，${result}`, 'success')
      await sleep(420)
    }
    state.completed.analyst = analysts

    // ---------- 阶段 3：多空辩论 ----------
    state.currentIndex = 2
    const rounds = genDebate(s)
    pushEvent('debate', '多空辩论', '开启 3 轮可控辩论（发言计数 + 角色轮转）')
    await sleep(500)
    if (guard()) throw new Error('cancelled')
    for (const r of rounds) {
      for (const [side, msg] of [
        ['多头研究员'.padEnd(5, '  '), r.bull],
        ['空头研究员'.padEnd(5, '  '), r.bear],
      ]) {
        if (guard()) throw new Error('cancelled')
        pushEvent('debate', side, `第 ${r.round} 轮 · ${msg.title}完成`, 'info')
        await sleep(520)
      }
    }
    state.completed.debate = rounds
    pushEvent('debate', '多空辩论', '辩论结束，多头/空头评分已汇总', 'success')

    // ---------- 阶段 4：交易提案 ----------
    state.currentIndex = 3
    pushEvent('trader', '交易员', '根据辩论结论生成交易提案…')
    await sleep(700)
    if (guard()) throw new Error('cancelled')
    state.completed.trader = genProposal(s)
    const p = state.completed.trader
    pushEvent('trader', '交易员', `提案生成：${p.direction}，目标 ${p.target}，止损 ${p.stop}`, 'success')

    // ---------- 阶段 5：风控评审 ----------
    state.currentIndex = 4
    const risks = genRisk(s)
    pushEvent('risk', '风控评审', '进攻 / 中性 / 保守 三类风控并行评审中')
    await sleep(600)
    if (guard()) throw new Error('cancelled')
    for (const r of risks) {
      if (guard()) throw new Error('cancelled')
      pushEvent('risk', r.name, `评审得分 ${r.score}，结论：${r.verdict}`, r.tone === 'warn' ? 'warn' : 'success')
      await sleep(500)
    }
    state.completed.risk = risks

    // ---------- 阶段 6：PM 决策 ----------
    state.currentIndex = 5
    pushEvent('pm', 'PM 决策', '汇总分析、辩论、提案与风控结论，生成最终决策…')
    await sleep(800)
    if (guard()) throw new Error('cancelled')
    state.completed.pm = genDecision(s)
    const confidence = state.completed.pm.confidence == null ? '置信度待模型评估' : `置信度 ${state.completed.pm.confidence}%`
    pushEvent('pm', 'PM 决策', `最终决策：${state.completed.pm.action}（${confidence}）`, 'success')

    state.finished = true
  } catch (e) {
    if (e.message !== 'cancelled' && runId === myRun) {
      pushEvent('system', '系统', `执行异常：${e.message}`, 'error')
    }
  } finally {
    if (runId === myRun) {
      state.running = false
      state.currentIndex = -1
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
