<template>
  <div class="stage-render">
    <!-- 1. 数据接入 -->
    <div v-if="stageKey === 'ingest' && data" class="ingest-wrap">
      <div class="ingest-head">
        <div class="ingest-title">
          <b>{{ data.stock_name || data.stock_code }}</b>
          <span class="faint">{{ data.stock_code }}</span>
        </div>
        <div class="ingest-sub">
          <el-tag size="small" effect="plain">{{ periodName(data.period) }}</el-tag>
          <span class="faint">{{ data.actual_start_date || '—' }} → {{ data.actual_end_date || '—' }}</span>
        </div>
      </div>

      <div class="ingest-cards">
        <div v-for="(item, i) in data.items" :key="i" class="ingest-card" :class="item.status">
          <div class="card-head">
            <el-icon class="card-icon"><component :is="ingestIcon(item.name)" /></el-icon>
            <span class="card-name">{{ item.name }}</span>
            <el-tag :type="ingestionStatusType(item)" effect="plain" size="small">
              {{ ingestionStatusLabel(item) }}
            </el-tag>
          </div>
          <div class="card-note">{{ item.note }}</div>
        </div>
      </div>

      <div v-if="metaChips.length" class="meta-chips">
        <span v-for="chip in metaChips" :key="chip.label" class="meta-chip">
          <span class="faint">{{ chip.label }}</span>{{ chip.value }}
        </span>
      </div>

      <el-collapse v-if="hasDetails" class="ingest-details">
        <el-collapse-item v-if="financialRows.length" name="financial">
          <template #title>
            <span class="detail-title">财务数据时间点 <em>{{ financialRows.length }}</em></span>
          </template>
          <div v-for="(row, i) in financialRows" :key="i" class="financial-row">
            <div class="financial-label">{{ row.label }}</div>
            <div class="financial-metrics">
              <span>ROE <b>{{ pct(row.roe) }}</b></span>
              <span>营收增速 <b>{{ pct(row.revGrowth) }}</b></span>
              <span>净利增速 <b>{{ pct(row.profitGrowth) }}</b></span>
              <span>毛利率 <b>{{ pct(row.margin) }}</b></span>
            </div>
          </div>
        </el-collapse-item>

        <el-collapse-item v-if="newsItems.length" name="news">
          <template #title>
            <span class="detail-title">
              区间事件 <em>{{ data.news_data.total_count ?? newsItems.length }}</em>
            </span>
          </template>
          <div class="news-list">
            <div
              v-for="(item, i) in newsItems"
              :key="`${item.published_at || item.time}-${i}`"
              class="news-row"
            >
              <span class="news-date faint">{{ shortDate(item.published_at || item.time) }}</span>
              <el-tag
                size="small"
                effect="plain"
                :type="item.kind === 'company_announcement' ? 'info' : 'success'"
              >
                {{ item.kind === 'company_announcement' ? '公告' : '新闻' }}
              </el-tag>
              <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">
                {{ item.title }}
              </a>
              <span v-else class="news-title">{{ item.title }}</span>
              <span v-if="item.source" class="faint news-source">{{ item.source }}</span>
            </div>
          </div>
        </el-collapse-item>

      </el-collapse>
    </div>

    <!-- 2. 分析师研报 -->
    <div v-else-if="stageKey === 'analyst' && data?.report" class="analyst-report">
      <div class="analyst-chips">
        <div v-for="card in analystCards" :key="card.key" class="analyst-chip" :class="card.stance">
          <span class="chip-label">{{ card.label }}</span>
          <el-tag size="small" effect="dark" :type="stanceTagType(card.stance)">
            {{ stanceLabel(card.stance) }}
          </el-tag>
          <span class="chip-conf">{{ conf(card.confidence) }}</span>
        </div>
        <span class="analyst-meta faint">
          {{ data.stock_name || data.stock_code }} · {{ periodName(data.period) }} ·
          {{ data.actual_start_date }} → {{ data.actual_end_date }} · {{ data.model_name }}
        </span>
      </div>

      <el-collapse v-model="expandedAnalysts" class="analyst-details">
        <el-collapse-item name="market">
          <template #title>
            <span class="detail-title">
              行情分析师
              <em>{{ stanceLabel(data.report.stance) }} · 置信度 {{ conf(data.report.confidence) }}</em>
            </span>
          </template>
          <div class="report-conclusion">{{ data.report.conclusion }}</div>
          <ol class="report-points">
            <li v-for="(point, i) in data.report.key_points" :key="i">
              <div class="point-text">{{ point.text }}</div>
              <div v-if="point.evidence_ids?.length" class="point-cites">
                <el-tag v-for="id in point.evidence_ids" :key="id" size="small" effect="plain" type="info">
                  {{ evidenceLabel(id) }}
                </el-tag>
              </div>
            </li>
          </ol>
        </el-collapse-item>

        <el-collapse-item v-for="finding in extraFindings" :key="finding.key" :name="finding.key">
          <template #title>
            <span class="detail-title">
              {{ finding.title }}
              <em>{{ stanceLabel(finding.report.stance) }} · 置信度 {{ conf(finding.report.confidence) }}</em>
            </span>
          </template>
          <div class="report-conclusion">{{ finding.report.conclusion }}</div>
          <ul class="extra-points">
            <li v-for="(point, i) in finding.report.key_points" :key="i">{{ point }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 3. 多空辩论 -->
    <div v-else-if="stageKey === 'debate' && data?.length" class="debate-wrap">
      <div class="debate-summary faint">
        共 {{ debateRounds.length }} 轮 · {{ data.length }} 条发言
        <span class="debate-legend">
          <i class="legend-dot bull" />多头
          <i class="legend-dot bear" />空头
        </span>
      </div>

      <el-collapse v-model="expandedRounds" class="debate-details">
        <el-collapse-item v-for="round in debateRounds" :key="round.number" :name="round.number">
          <template #title>
            <span class="detail-title">
              第 {{ round.number }} 轮 <em>{{ round.turns.length }} 条发言</em>
            </span>
          </template>
          <div class="round-body">
            <div
              v-for="turn in round.turns"
              :key="`${round.number}-${turn.speaker}`"
              class="debate-bubble"
              :class="turn.speaker"
            >
              <div class="bubble-avatar">{{ turn.speaker === 'bull' ? '多' : '空' }}</div>
              <div class="bubble-content">
                <div class="bubble-head">
                  <b>{{ turn.speaker === 'bull' ? '多头研究员' : '空头研究员' }}</b>
                </div>
                <div class="bubble-text">{{ turn.argument }}</div>
                <div v-if="turn.evidence_ids?.length" class="bubble-cites">
                  <el-tag v-for="id in turn.evidence_ids" :key="id" size="small" effect="plain" type="info">
                    {{ evidenceLabel(id) }}
                  </el-tag>
                </div>
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 4. 交易提案 -->
    <div v-else-if="stageKey === 'trader' && data" class="proposal-wrap">
      <div class="proposal-head">
        <span class="proposal-action" :class="data.action">{{ actionLabel(data.action) }}</span>
        <span class="faint">研究性提案，不构成下单指令</span>
      </div>

      <p class="proposal-rationale">{{ data.rationale }}</p>

      <div v-if="priceRows.length" class="proposal-prices">
        <div v-for="row in priceRows" :key="row.label" class="price-item">
          <span class="faint">{{ row.label }}</span>
          <b>{{ row.value }}</b>
        </div>
      </div>
      <div v-if="data.prices_estimated" class="price-note faint">
        模型未给出有效价位，以上为系统按近期 K 线估算
      </div>

      <div v-if="data.evidence_ids?.length" class="pm-block">
        <div class="risk-block-title">依据</div>
        <div class="pm-evidence">
          <el-tag v-for="id in data.evidence_ids" :key="id" size="small" effect="plain" type="info">
            {{ evidenceLabel(id) }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 5. 风控评审 -->
    <div v-else-if="stageKey === 'risk' && data?.length" class="risk-wrap">
      <div class="risk-overview">
        <span class="faint">三类风控意见</span>
        <span v-for="review in data" :key="review.reviewer" class="risk-chip" :class="review.decision">
          <i class="status-dot" />
          {{ reviewerLabel(review.reviewer) }} · {{ decisionLabel(review.decision) }}
        </span>
      </div>

      <div class="risk-grid">
        <div v-for="review in data" :key="review.reviewer" class="risk-card" :class="review.decision">
          <div class="risk-head">
            <span class="risk-badge">{{ reviewerBadge(review.reviewer) }}</span>
            <div class="risk-name">
              <b>{{ reviewerLabel(review.reviewer) }}</b>
              <span class="faint">{{ reviewerHint(review.reviewer) }}</span>
            </div>
            <el-tag size="small" effect="dark" :type="decisionTagType(review.decision)">
              {{ decisionLabel(review.decision) }}
            </el-tag>
          </div>

          <p class="risk-text">{{ review.summary }}</p>

          <div v-if="review.concerns?.length" class="risk-block">
            <div class="risk-block-title">关注点</div>
            <ul class="risk-list">
              <li v-for="(concern, i) in review.concerns" :key="i">{{ concern }}</li>
            </ul>
          </div>

          <div v-if="review.required_controls?.length" class="risk-block">
            <div class="risk-block-title">控制要求</div>
            <ul class="control-list">
              <li v-for="control in review.required_controls" :key="control">
                <el-icon class="control-icon"><CircleCheck /></el-icon>
                <span>{{ control }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- 6. PM 决策 -->
    <div v-else-if="stageKey === 'pm' && data" class="pm-wrap">
      <div class="pm-head">
        <div class="pm-action" :class="data.action">
          <span class="pm-action-label">最终结论</span>
          <b>{{ actionLabel(data.action) }}</b>
        </div>
        <div class="pm-confidence">
          <span class="faint">置信度</span>
          <span class="pm-bar">
            <i :style="{ width: `${Math.round((data.confidence || 0) * 100)}%` }" />
          </span>
          <b>{{ Math.round((data.confidence || 0) * 100) }}%</b>
        </div>
      </div>

      <div v-if="data.target_price || data.stop_price" class="pm-prices">
        <div class="pm-price">
          <span class="faint">{{ priceLabels(data.action).target }}</span>
          <b>{{ priceValue(data.target_price) }}</b>
        </div>
        <div class="pm-price">
          <span class="faint">{{ priceLabels(data.action).stop }}</span>
          <b>{{ priceValue(data.stop_price) }}</b>
        </div>
      </div>
      <div v-if="data.prices_estimated" class="price-note faint">
        模型未给出有效价位，以上为系统按近期 K 线估算
      </div>

      <p class="pm-rationale">{{ data.rationale }}</p>

      <div v-if="data.key_risks?.length" class="pm-block">
        <div class="risk-block-title">主要风险</div>
        <ul class="pm-risk-list">
          <li v-for="(risk, i) in data.key_risks" :key="i">
            <el-icon class="pm-risk-icon"><Warning /></el-icon>
            <span>{{ risk }}</span>
          </li>
        </ul>
      </div>

      <div v-if="data.evidence_ids?.length" class="pm-block">
        <div class="risk-block-title">依据</div>
        <div class="pm-evidence">
          <el-tag v-for="id in data.evidence_ids" :key="id" size="small" effect="plain" type="info">
            {{ evidenceLabel(id) }}
          </el-tag>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ stageKey: { type: String, required: true }, data: { type: Object, required: true } })

const periodName = (period) => ({ daily: '日K', weekly: '周K', monthly: '月K' })[period] || period
const pct = (value) => value == null ? '暂无' : `${Number(value).toFixed(2)}%`
const stanceLabel = (stance) => ({ bullish: '偏多', neutral: '中性', bearish: '偏空' })[stance] || '未知'
const stanceTagType = (stance) => ({ bullish: 'danger', neutral: 'info', bearish: 'success' })[stance] || 'info'
const actionLabel = (action) => ({ buy: '买入', hold: '持有', reduce: '减仓', avoid: '回避' })[action] || action
const priceValue = (value) => (value == null ? '—' : `${Number(value).toFixed(2)} 元`)
const priceLabels = (action) =>
  ['buy', 'hold'].includes(action)
    ? { target: '目标价', stop: '止损价' }
    : { target: '回补参考价', stop: '失效价' }
const reviewerLabel = (reviewer) =>
  ({ aggressive: '进攻型风控', neutral: '中性风控', conservative: '保守型风控' })[reviewer] || reviewer
const REVIEWER_BADGE = { aggressive: '攻', neutral: '中', conservative: '守' }
const REVIEWER_HINT = {
  aggressive: '关注收益空间',
  neutral: '平衡收益与风险',
  conservative: '本金安全优先',
}
const reviewerBadge = (reviewer) => REVIEWER_BADGE[reviewer] || '风'
const reviewerHint = (reviewer) => REVIEWER_HINT[reviewer] || ''

const decisionLabel = (decision) =>
  ({ approve: '通过', revise: '有条件通过', reject: '否决' })[decision] || decision
const decisionTagType = (decision) =>
  ({ approve: 'success', revise: 'warning', reject: 'danger' })[decision] || 'info'

const extraFindings = computed(() => {
  const items = []
  if (props.data?.fundamental_report) {
    items.push({ key: 'fundamental', title: '基本面分析师', report: props.data.fundamental_report })
  }
  if (props.data?.news_report) {
    items.push({ key: 'news', title: '新闻情绪分析师', report: props.data.news_report })
  }
  return items
})

const expandedAnalysts = ref(['market'])
const conf = (value) => (value == null ? '—' : `${Math.round(Number(value) * 100)}%`)
const analystCards = computed(() => {
  const cards = []
  if (props.data?.report) {
    cards.push({
      key: 'market',
      label: '行情',
      stance: props.data.report.stance,
      confidence: props.data.report.confidence,
    })
  }
  for (const finding of extraFindings.value) {
    cards.push({
      key: finding.key,
      label: finding.key === 'news' ? '新闻情绪' : '基本面',
      stance: finding.report.stance,
      confidence: finding.report.confidence,
    })
  }
  return cards
})

const debateRounds = computed(() => {
  const rounds = new Map()
  for (const turn of Array.isArray(props.data) ? props.data : []) {
    const number = turn.round_number ?? 1
    if (!rounds.has(number)) rounds.set(number, { number, turns: [] })
    rounds.get(number).turns.push(turn)
  }
  return [...rounds.values()].sort((a, b) => a.number - b.number)
})

// 默认展开所有轮次，用户可逐轮折叠
const PRICE_LABELS = {
  buy: ['买入价', '卖出价', '止损价'],
  reduce: ['卖出价', '回补价', '止损价'],
  avoid: ['卖出价', '回补价', '止损价'],
}

const priceRows = computed(() => {
  const proposal = props.data || {}
  const [entryLabel, targetLabel, stopLabel] =
    PRICE_LABELS[proposal.action] || ['参考价', '目标价', '止损价']
  return [
    { label: entryLabel, value: proposal.entry_price },
    { label: targetLabel, value: proposal.target_price },
    { label: stopLabel, value: proposal.stop_price },
  ]
    .filter((row) => row.value != null)
    .map((row) => ({ label: row.label, value: `${Number(row.value).toFixed(2)} 元` }))
})

const expandedRounds = ref([])
watch(
  debateRounds,
  (rounds) => {
    expandedRounds.value = rounds.map((round) => round.number)
  },
  { immediate: true }
)
const evidenceById = computed(() => new Map((props.data?.evidence || []).map((item) => [item.evidence_id, item])))
const evidenceLabel = (id) => {
  const evidence = evidenceById.value.get(id)
  if (!evidence) return `证据 ${id.slice(0, 8)}`
  const date = evidence.observed_at ? ` · ${String(evidence.observed_at).slice(0, 10)}` : ''
  return `${evidence.source}${date}`
}
const ingestionStatusLabel = (item) => {
  if (item.status === 'success') return '已获取'
  if (item.status === 'failed') return '获取失败'
  return item.name === '新闻与公司公告' ? '覆盖有限' : '数据不完整'
}
const ingestionStatusType = (item) => (
  item.status === 'success' ? 'success' : item.status === 'failed' ? 'danger' : 'warning'
)
const financialRows = computed(() => {
  const data = props.data?.fundamentals_data || {}
  const rows = []
  if (data.baseline) {
    rows.push({
      label: `区间前基线：${data.baseline.report_date}（公告 ${data.baseline.publication_date}）`,
      ...data.baseline,
    })
  } else if (data.roe != null || data.revGrowth != null || data.profitGrowth != null || data.margin != null) {
    rows.push({ label: '当前基本面快照', ...data })
  }
  for (const report of data.reports_in_range || []) {
    rows.push({
      label: `区间内披露：${report.report_date}（公告 ${report.publication_date}）`,
      ...report,
    })
  }
  return rows
})

const INGEST_ICONS = {
  K线行情: 'DataLine',
  日线行情: 'DataLine',
  基本面数据: 'DataAnalysis',
  新闻与公司公告: 'ChatDotRound',
}
const ingestIcon = (name) => INGEST_ICONS[name] || 'Document'

const newsItems = computed(() => props.data?.news_data?.items || [])

// 标题行已展示周期、区间和来源，这里只保留其余元信息
const metaChips = computed(() => {
  const meta = props.data?.meta || {}
  const hidden = ['分析周期', '请求区间', 'K线来源']
  return Object.entries(meta)
    .filter(([label]) => !hidden.includes(label))
    .map(([label, value]) => ({ label, value }))
})

const hasDetails = computed(
  () => financialRows.value.length > 0 || newsItems.value.length > 0
)

const shortDate = (value) => (value ? String(value).slice(0, 10) : '日期未知')
</script>

<style scoped>
.stage-render {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 数据接入 */
.ingest-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ingest-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.ingest-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 15px;
}
.ingest-title .faint {
  font-size: 12px;
}
.ingest-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.ingest-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 900px) {
  .ingest-cards {
    grid-template-columns: 1fr;
  }
}
.ingest-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid transparent;
}
.ingest-card.partial,
.ingest-card.failed {
  border-color: rgba(212, 167, 44, 0.35);
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
}
.card-head .el-tag {
  margin-left: auto;
}
.card-icon {
  font-size: 15px;
  color: var(--accent);
}
.ingest-card.success .card-icon {
  color: var(--down);
}
.ingest-card.partial .card-icon {
  color: var(--gold);
}
.card-note {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-2);
}
.meta-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--panel-2);
  font-size: 12px;
}
.meta-chip .faint {
  font-size: 11px;
}
.ingest-details {
  border: none;
}
.ingest-details :deep(.el-collapse-item__header) {
  height: 40px;
  background: transparent;
  border-bottom: 1px solid var(--border);
}
.ingest-details :deep(.el-collapse-item__wrap) {
  background: transparent;
}
.detail-title {
  font-size: 13px;
  font-weight: 700;
}
.detail-title em {
  margin-left: 6px;
  font-style: normal;
  font-weight: 400;
  font-size: 12px;
  color: var(--text-2);
}
.financial-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--panel-2);
}
.financial-label {
  font-size: 12px;
  font-weight: 600;
}
.financial-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  font-size: 12px;
  color: var(--text-2);
}
.financial-metrics b {
  color: var(--text);
}
.news-list {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow-y: auto;
}
.news-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 4px;
  font-size: 12px;
  line-height: 1.6;
  border-bottom: 1px solid rgba(35, 44, 66, 0.6);
}
.news-row:last-child {
  border-bottom: none;
}
.news-date {
  flex: 0 0 84px;
  font-variant-numeric: tabular-nums;
}
.news-row a {
  color: var(--accent);
  text-decoration: none;
}
.news-row a:hover {
  text-decoration: underline;
}
.news-title {
  color: var(--text);
}
.news-source {
  margin-left: auto;
  flex: 0 0 auto;
}
.analyst-report {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.analyst-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.analyst-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--panel-2);
}
.analyst-chip .chip-label {
  font-size: 12px;
  font-weight: 700;
}
.analyst-chip .chip-conf {
  font-size: 12px;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
.analyst-chip.bullish {
  box-shadow: inset 0 0 0 1px rgba(239, 68, 68, 0.35);
}
.analyst-chip.bearish {
  box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.35);
}
.analyst-meta {
  margin-left: auto;
  font-size: 12px;
}
.analyst-details {
  border: none;
}
.analyst-details :deep(.el-collapse-item__header) {
  height: 42px;
  background: transparent;
  border-bottom: 1px solid var(--border);
}
.analyst-details :deep(.el-collapse-item__wrap) {
  background: transparent;
}
.report-conclusion {
  margin-bottom: 10px;
  line-height: 1.8;
}
.report-points {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.report-points li {
  line-height: 1.7;
}
.point-text {
  color: var(--text);
}
.point-cites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.extra-points {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-2);
}

/* 多空辩论 */
.debate-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.debate-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
}
.debate-legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-left: 6px;
}
.legend-dot.bull {
  background: var(--up);
}
.legend-dot.bear {
  background: var(--down);
}
.debate-details {
  border: none;
}
.debate-details :deep(.el-collapse-item__header) {
  height: 40px;
  background: transparent;
  border-bottom: 1px solid var(--border);
}
.debate-details :deep(.el-collapse-item__wrap) {
  background: transparent;
}
.round-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 4px;
}
.debate-bubble {
  display: flex;
  gap: 10px;
  max-width: 92%;
}
.debate-bubble.bear {
  flex-direction: row-reverse;
  margin-left: auto;
}
.bubble-avatar {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
}
.debate-bubble.bull .bubble-avatar {
  background: rgba(239, 68, 68, 0.15);
  color: var(--up);
}
.debate-bubble.bear .bubble-avatar {
  background: rgba(34, 197, 94, 0.15);
  color: var(--down);
}
.bubble-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid transparent;
}
.debate-bubble.bull .bubble-content {
  border-color: rgba(239, 68, 68, 0.25);
}
.debate-bubble.bear .bubble-content {
  border-color: rgba(34, 197, 94, 0.25);
}
.bubble-head {
  font-size: 12px;
}
.bubble-text {
  font-size: 13px;
  line-height: 1.75;
}
.bubble-cites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 交易提案 */
.proposal-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.proposal-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.proposal-action {
  padding: 4px 14px;
  border-radius: 999px;
  background: var(--panel-2);
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 1px;
}
.proposal-action.buy {
  color: var(--up);
}
.proposal-action.reduce,
.proposal-action.avoid {
  color: var(--down);
}
.proposal-rationale {
  margin: 0;
  line-height: 1.8;
  color: var(--text-2);
}
.proposal-prices {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.price-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 112px;
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--panel-2);
}
.price-item b {
  font-size: 14px;
}
/* 风控评审 */
.risk-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.risk-overview {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.risk-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--panel-2);
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.risk-chip.approve .status-dot {
  background: var(--down);
}
.risk-chip.revise .status-dot {
  background: var(--gold);
}
.risk-chip.reject .status-dot {
  background: var(--up);
}
.risk-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 1100px) {
  .risk-grid {
    grid-template-columns: 1fr;
  }
}
.risk-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  background: var(--panel-2);
  border-top: 3px solid var(--border);
}
.risk-card.approve {
  border-top-color: var(--down);
}
.risk-card.revise {
  border-top-color: var(--gold);
}
.risk-card.reject {
  border-top-color: var(--up);
}
.risk-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.risk-head .el-tag {
  margin-left: auto;
}
.risk-badge {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 800;
  background: rgba(79, 124, 255, 0.15);
  color: var(--accent);
}
.risk-card.approve .risk-badge {
  background: rgba(34, 197, 94, 0.14);
  color: var(--down);
}
.risk-card.revise .risk-badge {
  background: rgba(212, 167, 44, 0.16);
  color: var(--gold);
}
.risk-card.reject .risk-badge {
  background: rgba(239, 68, 68, 0.14);
  color: var(--up);
}
.risk-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}
.risk-name .faint {
  font-size: 11px;
}
.risk-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);
}
.risk-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.risk-block-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text-2);
}
.risk-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.75;
  color: var(--text-2);
}
.control-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control-list li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
}
.control-icon {
  flex: 0 0 auto;
  margin-top: 3px;
  font-size: 12px;
  color: var(--gold);
}

/* PM 决策 */
.pm-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pm-head {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.pm-action {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 10px;
  background: var(--panel-2);
}
.pm-action-label {
  font-size: 11px;
  color: var(--text-2);
}
.pm-action b {
  font-size: 20px;
  letter-spacing: 1px;
}
.pm-action.buy b {
  color: var(--up);
}
.pm-action.reduce b,
.pm-action.avoid b {
  color: var(--down);
}
.pm-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.pm-bar {
  display: inline-block;
  width: 120px;
  height: 6px;
  border-radius: 999px;
  background: var(--panel-2);
  overflow: hidden;
}
.pm-bar i {
  display: block;
  height: 100%;
  background: var(--accent);
}
.pm-prices {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.pm-price {
  flex: 1 1 160px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 14px;
  border-radius: 9px;
  background: var(--panel-2);
  border: 1px solid var(--border);
}
.pm-price b {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}
.price-note {
  font-size: 11px;
  margin-top: -4px;
}
.pm-rationale {
  margin: 0;
  line-height: 1.8;
  color: var(--text-2);
}
.pm-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pm-risk-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pm-risk-list li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: #f0b9b9;
}
.pm-risk-icon {
  flex: 0 0 auto;
  margin-top: 3px;
  font-size: 12px;
  color: var(--up);
}
.pm-evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

</style>
