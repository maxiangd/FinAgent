// 把任务结果映射成六个阶段的展示数据（工作台与报告页共用）

export function taskResultToStages(result) {
  if (!result) return {}
  return {
    ingest: result.ingestion || null,
    analyst: {
      report: result.market_report,
      stock_name: result.stock_name,
      stock_code: result.stock_code,
      period: result.period,
      actual_start_date: result.actual_start_date,
      actual_end_date: result.actual_end_date,
      model_name: result.model_names?.market,
      limitations: result.limitations,
      evidence: result.evidence,
      fundamental_report: result.fundamental_report,
      news_report: result.news_report,
    },
    debate: result.debate_turns?.length ? result.debate_turns : null,
    trader: result.trade_proposal || null,
    risk: result.risk_reviews?.length ? result.risk_reviews : null,
    pm: result.pm_decision || null,
  }
}

export const PERIOD_TEXT = { daily: '日K', weekly: '周K', monthly: '月K' }
export const STATUS_TEXT = {
  queued: '排队中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}
export const ACTION_TEXT = { buy: '买入', hold: '持有', reduce: '减仓', avoid: '回避' }

export const statusTagType = (status) =>
  ({ completed: 'success', running: 'primary', failed: 'danger', cancelled: 'info' })[status] || 'info'

export const formatTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
