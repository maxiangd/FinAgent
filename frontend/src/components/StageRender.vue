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
    <div v-else-if="stageKey === 'analyst' && data" class="analyst-grid">
      <div v-for="a in data" :key="a.agent" class="panel analyst-card">
        <div class="analyst-head">
          <div class="analyst-icon"><el-icon><component :is="a.icon" /></el-icon></div>
          <div class="analyst-meta">
            <div class="analyst-name">{{ a.agent }}</div>
            <div class="analyst-group faint">{{ a.group }}</div>
          </div>
          <div v-if="a.rating != null" class="analyst-score">
            <span class="score-num">{{ a.rating }}</span>
            <span class="faint">分</span>
          </div>
          <el-tag v-else type="info" effect="plain" size="small">待接入 LLM</el-tag>
        </div>
        <ul class="analyst-lines">
          <li v-for="(line, i) in a.lines" :key="i">{{ line }}</li>
        </ul>
      </div>
    </div>

    <!-- 3. 多空辩论 -->
    <div v-else-if="stageKey === 'debate' && data" class="debate-wrap">
      <div v-for="r in data" :key="r.round" class="debate-round">
        <div class="debate-round-label faint">第 {{ r.round }} 轮</div>
        <div class="debate-msg bull">
          <div class="avatar bull">🐂</div>
          <div class="bubble">
            <div class="bubble-head"><b>多头研究员</b><span class="faint">{{ r.bull.title }}</span></div>
            <div class="bubble-body">{{ r.bull.content }}</div>
          </div>
        </div>
        <div class="debate-msg bear">
          <div class="bubble">
            <div class="bubble-head"><b>空头研究员</b><span class="faint">{{ r.bear.title }}</span></div>
            <div class="bubble-body">{{ r.bear.content }}</div>
          </div>
          <div class="avatar bear">🐻</div>
        </div>
      </div>
    </div>

    <!-- 4. 交易提案 -->
    <div v-else-if="stageKey === 'trader' && data" class="proposal-wrap">
      <div class="duel">
        <div class="duel-side bull-side">
          <div class="duel-score">{{ data.bullScore }}</div>
          <div class="muted">多头评分</div>
        </div>
        <div class="duel-bar">
          <div class="duel-fill bull" :style="{ width: data.bullScore + '%' }" />
        </div>
        <div class="duel-bar">
          <div class="duel-fill bear" :style="{ width: data.bearScore + '%' }" />
        </div>
        <div class="duel-side bear-side">
          <div class="duel-score">{{ data.bearScore }}</div>
          <div class="muted">空头评分</div>
        </div>
      </div>
      <div class="proposal-fields">
        <div class="pf-item">
          <span class="faint">操作方向</span>
          <b :class="data.directionType">{{ data.direction }}</b>
        </div>
        <div class="pf-item">
          <span class="faint">目标价</span>
          <b>{{ data.target }} 元</b>
        </div>
        <div class="pf-item">
          <span class="faint">止损价</span>
          <b>{{ data.stop }} 元</b>
        </div>
        <div class="pf-item">
          <span class="faint">建议仓位</span>
          <b>{{ data.position }}</b>
        </div>
        <div class="pf-item">
          <span class="faint">持有周期</span>
          <b>{{ data.horizon }}</b>
        </div>
      </div>
      <div class="proposal-rationale muted">{{ data.rationale }}</div>
    </div>

    <!-- 5. 风控评审 -->
    <div v-else-if="stageKey === 'risk' && data" class="risk-grid">
      <div v-for="r in data" :key="r.name" class="panel risk-card">
        <div class="risk-head">
          <div class="risk-name">
            <span class="risk-dot" :class="r.tone" />
            {{ r.name }}
          </div>
          <el-tag :type="r.tone === 'up' ? 'danger' : r.tone === 'warn' ? 'warning' : 'success'" effect="dark" size="small">
            {{ r.verdict }}
          </el-tag>
        </div>
        <div class="risk-score">
          <span class="score-num">{{ r.score }}</span>
          <span class="faint">/ 100</span>
        </div>
        <el-progress :percentage="+r.score" :stroke-width="5" :show-text="false"
          :color="r.tone === 'up' ? '#ef4444' : r.tone === 'warn' ? '#d4a72c' : '#22c55e'" />
        <div class="risk-comment muted">{{ r.comment }}</div>
        <div class="risk-limit faint">仓位上限：{{ r.limit }}</div>
      </div>
    </div>

    <!-- 6. PM 决策 -->
    <div v-else-if="stageKey === 'pm' && data" class="pm-wrap">
      <div class="pm-summary muted">{{ data.summary }}</div>
      <div class="pm-block">
        <div class="pm-block-title">决策依据</div>
        <ul>
          <li v-for="(r, i) in data.reasons" :key="i">{{ r }}</li>
        </ul>
      </div>
      <div class="pm-block">
        <div class="pm-block-title">风险提示</div>
        <ul class="risk-list">
          <li v-for="(r, i) in data.risks" :key="i">{{ r }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ stageKey: { type: String, required: true }, data: { type: Object, required: true } })

const periodName = (period) => ({ daily: '日K', weekly: '周K', monthly: '月K' })[period] || period
const pct = (value) => value == null ? '暂无' : `${Number(value).toFixed(2)}%`
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

/* 分析师 */
.analyst-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}
.analyst-card {
  padding: 14px;
}
.analyst-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.analyst-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: rgba(79, 124, 255, 0.12);
  font-size: 18px;
}
.analyst-name {
  font-weight: 700;
}
.analyst-group {
  font-size: 12px;
}
.analyst-score {
  margin-left: auto;
  text-align: right;
}
.score-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--accent);
}
.score-num {
  color: var(--accent);
}
.analyst-lines {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.8;
}

/* 辩论 */
.debate-round {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.debate-round-label {
  font-size: 12px;
  text-align: center;
  margin-bottom: 2px;
}
.debate-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.debate-msg.bull {
  justify-content: flex-start;
}
.debate-msg.bear {
  justify-content: flex-end;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 16px;
  flex-shrink: 0;
}
.avatar.bull {
  background: var(--up-bg);
  border: 1px solid rgba(239, 68, 68, 0.35);
}
.avatar.bear {
  background: var(--down-bg);
  border: 1px solid rgba(34, 197, 94, 0.35);
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--panel-2);
}
.debate-msg.bull .bubble {
  border-top-left-radius: 4px;
}
.debate-msg.bear .bubble {
  border-top-right-radius: 4px;
}
.bubble-head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  margin-bottom: 6px;
}
.bubble-body {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
}

/* 提案 */
.proposal-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.duel {
  display: flex;
  align-items: center;
  gap: 10px;
}
.duel-side {
  width: 70px;
  text-align: center;
}
.duel-score {
  font-size: 22px;
  font-weight: 800;
}
.bull-side .duel-score {
  color: var(--up);
}
.bear-side .duel-score {
  color: var(--down);
}
.duel-bar {
  flex: 1;
  height: 8px;
  background: var(--panel-2);
  border-radius: 4px;
  overflow: hidden;
}
.duel-bar:first-of-type {
  direction: rtl;
}
.duel-fill {
  height: 100%;
  border-radius: 4px;
}
.duel-fill.bull {
  background: linear-gradient(90deg, #ef4444, #f87171);
}
.duel-fill.bear {
  background: linear-gradient(90deg, #22c55e, #4ade80);
}
.proposal-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.pf-item {
  background: var(--panel-2);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pf-item span {
  font-size: 12px;
}
.proposal-rationale {
  font-size: 13px;
  line-height: 1.7;
  padding: 10px 12px;
  border-left: 3px solid var(--accent);
  background: var(--panel-2);
  border-radius: 0 8px 8px 0;
}

/* 风控 */
.risk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.risk-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.risk-name {
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
}
.risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.risk-dot.up {
  background: var(--up);
}
.risk-dot.warn {
  background: var(--gold);
}
.risk-dot.down {
  background: var(--down);
}
.risk-score .score-num {
  color: var(--text);
}
.risk-comment {
  font-size: 13px;
  line-height: 1.7;
  flex: 1;
}
.risk-limit {
  font-size: 12px;
}

/* PM */
.pm-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.pm-summary {
  font-size: 13px;
  line-height: 1.8;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--panel-2);
}
.pm-block-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.pm-block ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
  color: var(--text-2);
  font-size: 13px;
}
.pm-block .risk-list {
  color: #f59e9e;
}
</style>
