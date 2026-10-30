// 六阶段流水线的内容生成器
// 阶段：数据接入 → 分析师研报 → 多空辩论 → 交易提案 → 风控评审 → PM 决策
// 输入为股票快照对象（可能来自模拟数据或 AKShare 真实数据，部分字段可能为 null）
// 后续接入真实后端(LangGraph)后，这些函数将由 SSE 推送的真实事件替代

export const STAGES = [
  { key: 'ingest', label: '数据接入', desc: '行情 / 财务 / 新闻数据拉取' },
  { key: 'analyst', label: '分析师研报', desc: '技术面 · 基本面 · 新闻面' },
  { key: 'debate', label: '多空辩论', desc: '多头 vs 空头 · 3 轮' },
  { key: 'trader', label: '交易提案', desc: '交易员生成交易提案' },
  { key: 'risk', label: '风控评审', desc: '进攻 / 中性 / 保守评审' },
  { key: 'pm', label: 'PM 决策', desc: '输出最终投资决策' },
]

const NA = '暂无'
const num = (v) => (v == null || v !== v ? null : Number(v))

function fmt(v, digits = 1, suffix = '') {
  const n = num(v)
  return n == null ? NA : n.toFixed(digits) + suffix
}

const pct = (v, digits = 2) => (num(v) == null ? NA : `${v >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`)

// ---------- 1. 数据接入 ----------
export function genIngest(s) {
  const news = s.news ?? []
  return {
    items: [
      { name: '日线行情', note: `最新收盘 ${fmt(s.price, 2)} 元，当日 ${pct(s.changePct)}`, ok: true },
      { name: '财务摘要', note: `ROE ${fmt(s.roe)}% · 毛利率 ${fmt(s.margin)}% · 营收同比 ${pct(s.revGrowth)} · 净利同比 ${pct(s.profitGrowth)}`, ok: true },
      { name: '个股新闻', note: `获取原始新闻 ${news.length} 条；新闻判断待接入大模型`, ok: true },
    ],
    meta: {
      行业: s.industry ?? NA,
      市值: s.marketCap ?? NA,
      股息率: fmt(s.dividendYield),
    },
  }
}

// ---------- 2. 分析师研报 ----------
export function genAnalysts(s) {
  const trend = (s.changePct ?? 0) >= 0 ? '偏多' : '偏空'
  const news = s.news ?? []
  return [
    {
      agent: '行情分析师',
      icon: 'TrendCharts',
      group: '技术面',
      rating: (52 + Math.abs(s.changePct ?? 0) * 6).toFixed(0),
      lines: [
        `价格处于 20 日均线上方，短期动能 ${trend}；MACD 在零轴上方运行，红柱温和放大。`,
        `RSI(14) 为 ${fmt(48 + (s.changePct ?? 0) * 9, 1)}，量价配合一般，无明显的超买超卖信号。`,
        `关键支撑位 ${fmt(s.price * 0.965, 2)}，压力位 ${fmt(s.price * 1.06, 2)}，突破后空间打开。`,
      ],
    },
    {
      agent: '基本面分析师',
      icon: 'DataAnalysis',
      group: '基本面',
      rating: num(s.roe) == null ? '50' : (48 + s.roe * 0.9).toFixed(0),
      lines: [
        s.pe != null
          ? `PE(动) ${fmt(s.pe)}，处于行业合理区间；ROE ${fmt(s.roe)}%，盈利质量优秀。`
          : `PE 数据暂缺（行情源受限）；ROE ${fmt(s.roe)}%，盈利质量可参考财务摘要。`,
        `营收同比增长 ${pct(s.revGrowth)}，净利润同比增长 ${pct(s.profitGrowth)}。`,
        num(s.margin) != null && num(s.margin) >= 50
          ? `毛利率 ${fmt(s.margin)}%，构成宽阔护城河，盈利确定性较强。`
          : `毛利率 ${fmt(s.margin)}%，主业盈利水平稳健。`,
      ],
    },
    {
      agent: '新闻分析师',
      icon: 'ChatDotRound',
      group: '新闻面',
      rating: null,
      lines: news.length
        ? [
            `已获取 ${news.length} 条原始新闻；当前不生成自动利好/利空结论。`,
            ...news.slice(0, 3).map((item) => `${item.time ? `${item.time} · ` : ''}${item.title}${item.source ? `（${item.source}）` : ''}`),
          ]
        : ['当前没有获取到相关新闻。'],
    },
  ]
}

// 新闻分析模型接入前，多空评分保持中性。
export function scoreDuel(s) {
  return { bull: 50, bear: 50 }
}

// 由真实指标动态生成多空论据（替代手写 bullNotes/bearNotes）
function bullCases(s) {
  const c = []
  if (num(s.revGrowth) != null && s.revGrowth > 0) c.push(`营收同比增长 ${pct(s.revGrowth)}，成长性仍在`)
  else c.push('经营保持韧性，回调整理后基本面仍有支撑')
  if (num(s.roe) != null && s.roe > 12) c.push(`ROE ${fmt(s.roe)}% 保持高位，盈利质量扎实，具备穿越周期能力`)
  else if (num(s.roe) != null) c.push(`ROE ${fmt(s.roe)}% 处于行业中等水平，稳中有升`)
  if (num(s.margin) != null && s.margin >= 50) c.push(`毛利率 ${fmt(s.margin)}% 显示定价权，护城河较宽`)
  else if (num(s.margin) != null) c.push(`毛利率 ${fmt(s.margin)}% 保持稳定，主业盈利可见`)
  c.push('新闻分析模型尚未接入，暂不将新闻作为多头依据')
  return c
}

function bearCases(s) {
  const c = []
  if (num(s.profitGrowth) != null && s.profitGrowth < 0) c.push(`净利润同比 ${pct(s.profitGrowth)}，盈利端短期承压`)
  else if (num(s.profitGrowth) != null) c.push(`净利增速放缓至 ${pct(s.profitGrowth)}，边际改善有限`)
  else c.push('盈利数据暂缺，当前无法判断盈利趋势')
  c.push('短期涨幅已计入较多预期，追高胜率不高，需警惕获利回吐')
  c.push('宏观与行业景气存在不确定性，资金面波动加大')
  return c
}

// ---------- 3. 多空辩论 ----------
export function genDebate(s) {
  const { bull: bullScore, bear: bearScore } = scoreDuel(s)
  const bullC = bullCases(s)
  const bearC = bearCases(s)
  return [
    {
      round: 1,
      bull: { title: '多头首轮陈述', content: `第一，${bullC[0]}；第二，${bullC[1]}。核心逻辑：业绩确定性强，回调即机会。` },
      bear: { title: '空头首轮陈述', content: `第一，${bearC[0]}；第二，${bearC[1]}。核心逻辑：预期已较充分，风险收益比不佳。` },
    },
    {
      round: 2,
      bull: { title: '多头反驳', content: `空头担忧属于阶段性数据扰动。以 ${s.name} 的现金流与定价权，${s.pe != null ? `当前 ${fmt(s.pe)} 倍 PE ` : ''}对应的是确定性的中期增长，戴维斯双击概率大于双杀概率。` },
      bear: { title: '空头反驳', content: `多头忽略了边际变化：增速放缓 + 估值不便宜的组合，历史上常见"业绩兑现但股价不涨"的钝化行情，资金的机会成本不可忽视。` },
    },
    {
      round: 3,
      bull: { title: '多头总结', content: bullScore === bearScore ? `当前多空模拟评分持平（${bullScore}:${bearScore}），暂不形成方向性建议。` : `综合多空逻辑，多头评分 ${bullScore}：建议买入，目标价 ${fmt(s.price * 1.08, 2)}，仓位 12%-15%。` },
      bear: { title: '空头总结', content: bullScore === bearScore ? '新闻分析模型尚未接入，需等待更多分析后再判断方向。' : `综合多空逻辑，空头评分 ${bearScore}：建议观望或持仓减半，等待基本面与估值共振。` },
    },
  ]
}

// ---------- 4. 交易提案 ----------
export function genProposal(s) {
  const { bull: bullScore, bear: bearScore } = scoreDuel(s)
  const bullWins = bullScore > bearScore
  const bearWins = bearScore > bullScore
  return {
    bullScore,
    bearScore,
    direction: bullWins ? '买入' : bearWins ? '卖出/减仓' : '观望',
    directionType: bullWins ? 'up' : bearWins ? 'down' : 'neutral',
    target: bullWins ? fmt(s.price * 1.08, 2) : bearWins ? fmt(s.price * 0.94, 2) : '待评估',
    stop: bullWins ? fmt(s.price * 0.965, 2) : bearWins ? fmt(s.price * 1.06, 2) : '待评估',
    position: bullWins ? '10% - 15%' : bearWins ? '0% - 5%' : '0%',
    horizon: bullWins || bearWins ? '1 - 3 个月' : '待模型评估',
    rationale: bullWins
      ? `辩论环节多头以 ${bullScore} : ${bearScore} 占优。建议结合基本面进一步评估。`
      : bearWins
        ? `辩论环节空头以 ${bearScore} : ${bullScore} 占优。建议降低仓位或观望。`
        : '当前模拟评分持平，新闻分析模型尚未接入，暂不提供方向性建议。',
  }
}

// ---------- 5. 风控评审 ----------
export function genRisk(s) {
  const base = 60
  return [
    { name: '进攻型风控', limit: '≤ 20%', score: Math.min(95, base + 16).toFixed(0), verdict: '通过', tone: 'up', comment: `当前模拟评分达到通过阈值；要求止损纪律严格，跌破 ${fmt(s.price * 0.955, 2)} 无条件离场。` },
    { name: '中性风控', limit: '≤ 12%', score: base.toFixed(0), verdict: '有条件通过', tone: 'warn', comment: `基本面与估值匹配度尚可，但短期涨幅已计入部分预期，建议回踩均线分批建仓，单票仓位不超过 12%。` },
    { name: '保守风控', limit: '≤ 8%', score: Math.max(30, base - 14).toFixed(0), verdict: '减仓提示', tone: 'down', comment: `板块 Beta 修复接近尾声、市场波动率上升，保守型账户建议仓位降至 8% 以下或等待更优买点。` },
  ]
}

// ---------- 6. PM 决策 ----------
export function genDecision(s) {
  const proposal = genProposal(s)
  const risks = genRisk(s)
  const passes = risks.filter((r) => r.verdict === '通过').length
  const condPasses = risks.filter((r) => r.verdict === '有条件通过').length
  const confidence = proposal.directionType === 'neutral' ? null : Math.min(88, 52 + passes * 4)
  const action = proposal.directionType === 'up' ? '买入' : proposal.directionType === 'down' ? '减仓' : '观望'
  return {
    action,
    tone: proposal.directionType,
    confidence: confidence.toFixed(0),
    target: proposal.target,
    stop: proposal.stop,
    position: proposal.position,
    horizon: proposal.horizon,
    summary: proposal.directionType === 'neutral'
      ? `对 ${s.name}（${s.code}）的当前模拟多空评分持平；新闻分析模型尚未接入，暂不提供方向性建议。`
      : `综合多空辩论（多头 ${proposal.bullScore} : ${proposal.bearScore} 空头）、交易提案与三类风控评审（通过 ${passes} / 有条件通过 ${condPasses} / 减仓提示 1），对 ${s.name}（${s.code}）给出「${action}」评级：目标价 ${proposal.target} 元，建议仓位 ${proposal.position}，止损位 ${proposal.stop} 元，持有周期 ${proposal.horizon}。`,
    reasons: [
      proposal.directionType === 'neutral'
        ? '多空模拟评分持平，新闻判断待接入大模型'
        : proposal.direction === '买入' ? '多空辩论中多头逻辑占优，成长确定性为决策主依据' : '多空辩论中空头逻辑占优，控制回撤为第一优先',
      '基本面（稳健盈利质量 / 现金流）支撑中期持有下限',
      '风控评审通过，仓位建议已纳入波动率与风险预算约束',
    ],
    risks: ['行业景气不及预期', '市场系统性风险下的流动性收缩', '短期涨幅过大后的技术性回调'],
  }
}
