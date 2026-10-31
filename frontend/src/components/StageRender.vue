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

</style>
