// 六阶段流水线的阶段定义；数据接入与分析师已由后端真实执行，其余阶段待接入。
export const STAGES = [
  { key: 'ingest', label: '数据接入', desc: '行情 / 财务 / 新闻数据拉取' },
  { key: 'analyst', label: '分析师研报', desc: '技术面 · 基本面 · 新闻面' },
  { key: 'debate', label: '多空辩论', desc: '多头 vs 空头 · 3 轮' },
  { key: 'trader', label: '交易提案', desc: '交易员生成交易提案' },
  { key: 'risk', label: '风控评审', desc: '进攻 / 中性 / 保守评审' },
  { key: 'pm', label: 'PM 决策', desc: '输出最终投资决策' },
]
