<template>
  <div class="stage-render">
    <!-- 1. 数据接入 -->
    <div v-if="stageKey === 'ingest' && data" class="ingest-wrap">
      <div class="ingest-range muted">
        {{ data.stock_name || '股票' }}（{{ data.stock_code }}）·
        {{ periodName(data.period) }} ·
        {{ data.actual_start_date || '—' }} 至 {{ data.actual_end_date || '—' }}
      </div>
      <div v-for="(item, i) in data.items" :key="i" class="ingest-item">
        <el-icon class="ingest-status" :class="item.status">
          <CircleCheckFilled v-if="item.status === 'success'" />
          <WarningFilled v-else />
        </el-icon>
        <div class="ingest-body">
          <div class="ingest-name">
            {{ item.name }}
            <el-tag :type="ingestionStatusType(item)" effect="plain" size="small">
              {{ ingestionStatusLabel(item) }}
            </el-tag>
          </div>
          <div class="ingest-note">{{ item.note }}</div>
        </div>
      </div>
      <div v-if="data.meta" class="meta-tags">
        <el-tag v-for="(v, k) in data.meta" :key="k" effect="plain" size="small" class="meta-tag">
          {{ k }}：{{ v }}
        </el-tag>
      </div>

      <div v-if="financialRows.length" class="ingest-detail-block">
        <div class="ingest-detail-title">财务数据时间点</div>
        <div v-for="(row, i) in financialRows" :key="i" class="ingest-financial-row">
          <b>{{ row.label }}</b>
          <span>ROE {{ pct(row.roe) }}</span>
          <span>营收增速 {{ pct(row.revGrowth) }}</span>
          <span>净利增速 {{ pct(row.profitGrowth) }}</span>
          <span>毛利率 {{ pct(row.margin) }}</span>
        </div>
      </div>

      <div v-if="data.news_data?.items?.length" class="ingest-detail-block">
        <div class="ingest-detail-title">
          区间事件
          <span class="faint">共 {{ data.news_data.total_count ?? data.news_data.items.length }} 条，按日期倒序</span>
        </div>
        <div v-for="(item, i) in data.news_data.items" :key="`${item.published_at || item.time}-${i}`" class="ingest-news-row">
          <span class="ingest-news-date faint">{{ item.published_at || item.time || '日期未知' }}</span>
          <el-tag v-if="item.kind" size="small" effect="plain" :type="item.kind === 'company_announcement' ? 'info' : 'success'">
            {{ item.kind === 'company_announcement' ? '公司公告' : '新闻' }}
          </el-tag>
          <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>
          <span v-else>{{ item.title }}</span>
          <span v-if="item.source" class="faint">{{ item.source }}</span>
        </div>
      </div>

      <div v-if="data.limitations?.length" class="ingest-limitations">
        <div class="ingest-detail-title">数据说明</div>
        <div v-for="(note, i) in data.limitations" :key="i">{{ note }}</div>
      </div>
    </div>

    <!-- 2. 分析师研报 -->
    <div v-else-if="stageKey === 'analyst' && data?.report" class="market-analysis-report">
      <div class="market-report-head">
        <el-tag :type="stanceTagType(data.report.stance)" effect="dark" size="small">
          {{ stanceLabel(data.report.stance) }}
        </el-tag>
        <span class="faint">
          {{ data.stock_name || data.stock_code }} · {{ periodName(data.period) }} ·
          {{ data.actual_start_date }} 至 {{ data.actual_end_date }} · {{ data.model_name }}
        </span>
        <b class="market-report-confidence">置信度 {{ Math.round(data.report.confidence * 100) }}%</b>
      </div>
      <div class="market-report-conclusion">{{ data.report.conclusion }}</div>
      <div v-for="(point, i) in data.report.key_points" :key="i" class="market-report-point">
        <span class="market-report-point-index">{{ i + 1 }}</span>
        <div class="market-report-point-body">
          <div>{{ point.text }}</div>
          <div class="market-report-citations">
            <el-tag v-for="id in point.evidence_ids" :key="id" size="small" effect="plain" type="info">
              {{ evidenceLabel(id) }}
            </el-tag>
          </div>
        </div>
      </div>
      <div v-if="data.report.data_gaps?.length" class="market-report-gaps">
        <b>数据缺口</b>
        <span v-for="(gap, i) in data.report.data_gaps" :key="i">{{ gap }}</span>
      </div>
      <div v-if="data.limitations?.length" class="market-report-gaps">
        <b>数据限制</b>
        <span v-for="(limitation, i) in data.limitations" :key="i">{{ limitation }}</span>
      </div>

      <div v-if="extraFindings.length" class="analyst-extra">
        <div v-for="finding in extraFindings" :key="finding.title" class="analyst-extra-card">
          <div class="analyst-extra-head">
            <b>{{ finding.title }}</b>
            <el-tag :type="stanceTagType(finding.report.stance)" effect="plain" size="small">
              {{ stanceLabel(finding.report.stance) }}
            </el-tag>
            <span class="faint">置信度 {{ Math.round((finding.report.confidence || 0) * 100) }}%</span>
          </div>
          <div class="analyst-extra-conclusion">{{ finding.report.conclusion }}</div>
          <ul class="analyst-extra-points">
            <li v-for="(point, i) in finding.report.key_points" :key="i">{{ point }}</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 3. 多空辩论 -->
    <div v-else-if="stageKey === 'debate' && data?.length" class="debate-wrap">
      <div v-for="(turn, i) in data" :key="i" class="debate-turn" :class="turn.speaker">
        <div class="debate-badge">{{ turn.speaker === 'bull' ? '多头' : '空头' }}</div>
        <div class="debate-body">
          <div class="faint">第 {{ turn.round_number }} 轮</div>
          <div>{{ turn.argument }}</div>
        </div>
      </div>
    </div>

    <!-- 4. 交易提案 -->
    <div v-else-if="stageKey === 'trader' && data" class="proposal-wrap">
      <div class="proposal-head">
        <el-tag effect="dark" size="small" :type="actionTagType(data.action)">{{ actionLabel(data.action) }}</el-tag>
        <span class="faint">研究性提案，不构成下单指令</span>
      </div>
      <div class="proposal-rationale">{{ data.rationale }}</div>
      <div class="proposal-prices">
        <span>参考价 {{ priceLabel(data.entry_price) }}</span>
        <span>目标价 {{ priceLabel(data.target_price) }}</span>
        <span>止损价 {{ priceLabel(data.stop_price) }}</span>
      </div>
    </div>

    <!-- 5. 风控评审 -->
    <div v-else-if="stageKey === 'risk' && data?.length" class="risk-wrap">
      <div v-for="review in data" :key="review.reviewer" class="risk-card">
        <div class="risk-head">
          <b>{{ reviewerLabel(review.reviewer) }}</b>
          <el-tag size="small" effect="plain" :type="decisionTagType(review.decision)">
            {{ decisionLabel(review.decision) }}
          </el-tag>
        </div>
        <div class="risk-summary">{{ review.summary }}</div>
        <ul v-if="review.concerns?.length" class="risk-list">
          <li v-for="(concern, i) in review.concerns" :key="i">{{ concern }}</li>
        </ul>
        <div v-if="review.required_controls?.length" class="risk-controls faint">
          控制要求：{{ review.required_controls.join('；') }}
        </div>
      </div>
    </div>

    <!-- 6. PM 决策 -->
    <div v-else-if="stageKey === 'pm' && data" class="pm-wrap">
      <div class="pm-head">
        <el-tag effect="dark" size="small" :type="actionTagType(data.action)">{{ actionLabel(data.action) }}</el-tag>
        <b>置信度 {{ Math.round((data.confidence || 0) * 100) }}%</b>
      </div>
      <div class="pm-rationale">{{ data.rationale }}</div>
      <div v-if="data.key_risks?.length" class="pm-risks">
        <b>主要风险</b>
        <span v-for="(risk, i) in data.key_risks" :key="i">{{ risk }}</span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ stageKey: { type: String, required: true }, data: { type: Object, required: true } })

const periodName = (period) => ({ daily: '日K', weekly: '周K', monthly: '月K' })[period] || period
const pct = (value) => value == null ? '暂无' : `${Number(value).toFixed(2)}%`
const stanceLabel = (stance) => ({ bullish: '偏多', neutral: '中性', bearish: '偏空' })[stance] || '未知'
const stanceTagType = (stance) => ({ bullish: 'danger', neutral: 'info', bearish: 'success' })[stance] || 'info'
const actionLabel = (action) => ({ buy: '买入', hold: '持有', reduce: '减仓', avoid: '回避' })[action] || action
const actionTagType = (action) => ({ buy: 'danger', hold: 'info', reduce: 'warning', avoid: 'success' })[action] || 'info'
const priceLabel = (value) => (value == null ? '未给出' : `${Number(value).toFixed(2)} 元`)
const reviewerLabel = (reviewer) =>
  ({ aggressive: '进攻型风控', neutral: '中性风控', conservative: '保守型风控' })[reviewer] || reviewer
const decisionLabel = (decision) => ({ approve: '通过', revise: '需修改', reject: '否决' })[decision] || decision
const decisionTagType = (decision) =>
  ({ approve: 'success', revise: 'warning', reject: 'danger' })[decision] || 'info'

const extraFindings = computed(() => {
  const items = []
  if (props.data?.fundamental_report) {
    items.push({ title: '基本面分析师', report: props.data.fundamental_report })
  }
  if (props.data?.news_report) {
    items.push({ title: '新闻情绪分析师', report: props.data.news_report })
  }
  return items
})
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
</script>

<style scoped>
.stage-render {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 数据接入 */
.ingest-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--panel-2);
}
.ingest-range {
  font-size: 13px;
  font-weight: 600;
}
.ingest-status {
  font-size: 16px;
  margin-top: 2px;
  flex-shrink: 0;
}
.ingest-status.success {
  color: var(--down);
}
.ingest-status.partial,
.ingest-status.failed {
  color: var(--gold);
}
.ingest-name {
  font-weight: 600;
  margin-bottom: 2px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ingest-note {
  font-size: 13px;
  color: var(--text-2);
}
.meta-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.ingest-detail-block,
.ingest-limitations {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--panel-2);
}
.ingest-detail-title {
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.ingest-financial-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: var(--text-2);
  font-size: 12px;
}
.ingest-financial-row b {
  color: var(--text);
}
.ingest-news-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.ingest-news-date {
  flex: 0 0 86px;
  font-variant-numeric: tabular-nums;
}
.ingest-news-row a {
  color: var(--accent);
  text-decoration: none;
}
.ingest-news-row a:hover {
  text-decoration: underline;
}
.ingest-limitations {
  color: var(--gold);
  font-size: 12px;
  line-height: 1.6;
}
.ingest-limitations .ingest-detail-title {
  color: var(--text);
}
.market-analysis-report {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.market-report-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
}
.market-report-confidence {
  margin-left: auto;
}
.market-report-conclusion {
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--panel-2);
  font-weight: 600;
  line-height: 1.7;
}
.market-report-point {
  display: flex;
  gap: 10px;
  line-height: 1.7;
}
.market-report-point-index {
  flex: 0 0 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--accent);
  background: rgba(79, 124, 255, 0.12);
}
.market-report-point-body {
  min-width: 0;
}
.market-report-citations {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 5px;
}
.market-report-gaps {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--gold);
  background: var(--panel-2);
  font-size: 12px;
  line-height: 1.6;
}
.market-report-gaps b {
  color: var(--text);
}

/* 三个分析师的补充结论 */
.analyst-extra {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}
.analyst-extra-card {
  background: var(--panel-2);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.analyst-extra-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.analyst-extra-conclusion {
  color: var(--text-2);
  line-height: 1.7;
}
.analyst-extra-points {
  margin: 0;
  padding-left: 16px;
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.8;
}

/* 多空辩论 */
.debate-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.debate-turn {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: var(--panel-2);
  border-radius: 8px;
  padding: 10px 12px;
  border-left: 3px solid transparent;
}
.debate-turn.bull {
  border-left-color: var(--up);
}
.debate-turn.bear {
  border-left-color: var(--down);
}
.debate-badge {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
}
.debate-turn.bull .debate-badge {
  color: var(--up);
}
.debate-turn.bear .debate-badge {
  color: var(--down);
}
.debate-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.7;
}

/* 交易提案 */
.proposal-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.proposal-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.proposal-rationale {
  line-height: 1.8;
  color: var(--text-2);
}
.proposal-prices {
  display: flex;
  gap: 18px;
  font-size: 13px;
  color: var(--text-2);
}

/* 风控评审 */
.risk-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.risk-card {
  background: var(--panel-2);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.risk-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.risk-summary {
  color: var(--text-2);
  line-height: 1.7;
}
.risk-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-2);
}
.risk-controls {
  font-size: 12px;
}

/* PM 决策 */
.pm-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pm-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pm-rationale {
  line-height: 1.8;
  color: var(--text-2);
}
.pm-risks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #f0b9b9;
}

</style>
