<template>
  <div class="home">
    <!-- 顶部：标的搜索 + 运行控制 -->
    <div class="panel toolbar">
      <div class="search-box">
        <el-select
          v-model="selCode"
          filterable
          remote
          clearable
          :remote-method="onQuery"
          :loading="searching"
          class="stock-select"
          placeholder="输入股票代码或名称，如 600519 / 贵州茅台"
          :disabled="state.running"
          @change="onPickCode"
          @keyup.enter="onPickFirst"
        >
          <el-option v-for="c in candidates" :key="c.code" :label="`${c.name}（${c.code}）`" :value="c.code" />
        </el-select>
        <el-button type="primary" :icon="Search" :loading="loading" @click="onPickFirst">查询</el-button>
        <el-button type="primary" plain :icon="VideoPlay" :disabled="!selected || state.running" @click="start">
          开始分析
        </el-button>
        <el-button :icon="VideoPause" :disabled="!state.running" @click="stop">停止</el-button>
        <el-button :icon="Refresh" :disabled="!selected || state.running" @click="reset">重置</el-button>
      </div>
      <div class="mode-badge">
        <el-tag effect="dark" type="success" size="small">AKShare 真实数据</el-tag>
        <el-tag effect="plain" size="small" type="info">LangGraph 后端规划中</el-tag>
      </div>
    </div>

    <!-- 标的行情头 -->
    <div v-if="selected" class="panel stock-header">
      <div class="stock-main">
        <div class="stock-name">{{ selected.name }}</div>
        <div class="stock-code faint">{{ selected.code }} · {{ selected.industry }}</div>
      </div>
      <div class="stock-quote">
        <span class="stock-price" :class="(selected.changePct ?? 0) >= 0 ? 'up' : 'down'">{{ fmt(selected.price, 2) }}</span>
        <span class="stock-change" :class="(selected.changePct ?? 0) >= 0 ? 'up' : 'down'">
          {{ (selected.changePct ?? 0) >= 0 ? '+' : '' }}{{ fmt(selected.changePct, 2) }}%
        </span>
      </div>
      <div class="stock-meta">
        <div class="sm-item"><span class="faint">市值</span><b>{{ selected.marketCap ?? '暂无' }}</b></div>
        <div class="sm-item"><span class="faint">PE(TTM)</span><b>{{ fmt(selected.pe, 1) }}</b></div>
        <div class="sm-item"><span class="faint">ROE</span><b>{{ fmt(selected.roe, 1) }}%</b></div>
        <div class="sm-item"><span class="faint">股息率</span><b>{{ fmt(selected.dividendYield, 2) }}%</b></div>
        <div class="sm-item"><span class="faint">营收增速</span><b :class="fmtpctCls(selected.revGrowth)">{{ fmtPct(selected.revGrowth) }}</b></div>
        <div class="sm-item"><span class="faint">净利增速</span><b :class="fmtpctCls(selected.profitGrowth)">{{ fmtPct(selected.profitGrowth) }}</b></div>
        <div class="sm-item"><span class="faint">量比</span><b :class="volRatioInfo(selected.volRatio).cls">{{ volRatioInfo(selected.volRatio).text }}<span class="tiny">{{ fmt(selected.volRatio, 2) }}</span></b></div>
      </div>
    </div>

    <!-- 行情图表（可折叠） -->
    <div class="panel market-panel">
      <div class="market-head">
        <span class="market-title">
          行情图表
          <span class="faint">近 {{ kCount }} 根 · AKShare 前复权</span>
        </span>
        <div class="market-tools">
          <el-segmented v-model="kPeriod" :options="periodOptions" size="small" />
          <el-button text size="small" :icon="chartOpen ? Fold : Expand" @click="chartOpen = !chartOpen">
            {{ chartOpen ? '收起' : '展开' }}
          </el-button>
        </div>
      </div>
      <el-collapse-transition>
        <div v-show="chartOpen && selected" class="market-body">
          <div class="market-stats">
            <div v-for="st in marketStats" :key="st.label" class="ms-item">
              <span class="faint">{{ st.label }}</span>
              <b :class="st.cls || undefined">{{ st.value }}</b>
            </div>
          </div>
          <div class="market-chart">
            <div class="chart-toolbar">
              <el-radio-group v-model="indicator" size="small">
                <el-radio-button value="none">隐藏</el-radio-button>
                <el-radio-button value="vol">成交量</el-radio-button>
                <el-radio-button value="macd">MACD</el-radio-button>
                <el-radio-button value="kdj">KDJ</el-radio-button>
                <el-radio-button value="rsi">RSI</el-radio-button>
              </el-radio-group>
              <span class="ma-switch">
              <el-checkbox v-model="chartPrefs.showMA">均线</el-checkbox>
              <span class="faint">MA5/10/20/60</span>
              <el-checkbox v-model="chartPrefs.rangeBox">箱体边界</el-checkbox>
            </span>
            </div>
            <!-- key 仅含周期：切周期重建；切指标不重建，保留拖拽窗口 -->
            <KLineChart :key="`${kPeriod}`" :stock="chartStock" :period="kPeriod" height="320px" :indicator="indicator" @count="kCount = $event" />
            <div v-if="chartLoading" class="market-foot faint">正在加载 {{ kPeriod }} 数据…</div>
            <div v-else class="market-foot faint">
              当前周期：{{ kPeriod }} · 共 {{ kCount }} 根 · 数据源：AKShare · 最近：{{ lastKDate }} · 收：{{ lastKClose }} 元
            </div>
          </div>
        </div>
      </el-collapse-transition>
    </div>

    <!-- 阶段进度 -->
    <StageProgress class="stages" />

    <!-- 主内容 -->
    <div class="columns">
      <div class="col-left">
        <!-- 每个已完成/执行中阶段的报告区 -->
        <template v-for="(s, i) in STAGES" :key="s.key">
          <div v-if="completedData(s)" class="panel stage-section">
            <div class="stage-head">
              <span class="stage-idx">{{ i + 1 }}</span>
              <span class="stage-label">{{ s.label }}</span>
              <span class="stage-desc faint">{{ s.desc }}</span>
              <el-tag type="success" effect="dark" size="small" class="stage-state">完成</el-tag>
            </div>
            <StageRender :stage-key="s.key" :data="completedData(s)" />
          </div>
          <div v-else-if="isCurrent(i)" class="panel stage-section running-section">
            <div class="stage-head">
              <span class="stage-idx">{{ i + 1 }}</span>
              <span class="stage-label">{{ s.label }}</span>
              <span class="stage-desc faint">{{ s.desc }}</span>
              <el-tag type="primary" effect="dark" size="small" class="is-loading stage-state">
                <el-icon class="spin"><Loading /></el-icon> 执行中
              </el-tag>
            </div>
            <div class="running-placeholder faint">
              <el-icon class="is-loading" :size="20" style="margin-right: 8px"><Loading /></el-icon>
              {{ s.label }} 阶段 Agent 正在执行，事件实时推送至右侧事件流…
            </div>
          </div>
        </template>
      </div>

      <div class="col-right">
        <DecisionPanel />
        <div class="panel event-wrap">
          <EventLog />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, Refresh, Fold, Expand, Search } from '@element-plus/icons-vue'
import { STAGES } from '../features/analysis/content'
import { state, startSimulation, stopSimulation, selectStock, chartPrefs } from '../features/analysis/pipeline'
import { fetchKline, loadStock, searchStock, showApiError } from '../api/market'
import StageProgress from '../components/StageProgress.vue'
import StageRender from '../components/StageRender.vue'
import KLineChart from '../components/KLineChart.vue'
import EventLog from '../components/EventLog.vue'
import DecisionPanel from '../components/DecisionPanel.vue'

const selCode = ref('600519')
const candidates = ref([{ code: '600519', name: '贵州茅台' }])
const searching = ref(false)
const loading = ref(false)
let searchTimer = null
const chartOpen = ref(true)
const kPeriod = ref('日K')
const periodOptions = ['日K', '周K', '月K']
const apiPeriod = { 日K: 'daily', 周K: 'weekly', 月K: 'monthly' }
const indicator = ref('macd')
const kCount = ref(0)
const selected = computed(() => state.selected)
const chartBars = ref(null)
const chartLoading = ref(false)
let chartRequestId = 0
const chartStock = computed(() => {
  const stock = selected.value
  const bars = chartBars.value
  if (!stock || kPeriod.value === '日K') return stock
  if (!bars || bars.code !== stock.code || bars.period !== kPeriod.value) {
    return { ...stock, kline: [], dates: [], klinePeriod: kPeriod.value }
  }
  return { ...stock, kline: bars.items, dates: bars.dates, klinePeriod: kPeriod.value }
})
const completedData = (s) => state.completed[s.key] || null
const isCurrent = (i) => state.currentIndex === i

const fmt = (v, n = 2) => (v == null || Number.isNaN(Number(v)) ? '暂无' : Number(v).toFixed(n))
const fmtPct = (v) => (v == null || Number.isNaN(Number(v)) ? '暂无' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`)
const fmtpctCls = (v) => (v == null || Number.isNaN(Number(v)) ? '' : v >= 0 ? 'up' : 'down')

// 量比分档 → 直观文案（业界常用阈值）
function volRatioInfo(v) {
  const n = Number(v)
  if (v == null || Number.isNaN(n)) return { text: '暂无', cls: '' }
  if (n >= 2.5) return { text: '明显活跃', cls: 'up' }
  if (n >= 1.5) return { text: '活跃', cls: 'up' }
  if (n >= 1.0) return { text: '温和放量', cls: '' }
  if (n >= 0.8) return { text: '平量', cls: '' }
  if (n >= 0.5) return { text: '缩量', cls: 'down' }
  return { text: '明显缩量', cls: 'down' }
}

// 行情图表面板底部信息行（最近交易日 / 收盘价）
const lastKDate = computed(() => chartStock.value?.dates?.at(-1) ?? '-')
const lastKClose = computed(() => {
  const k = chartStock.value?.kline
  return k?.length ? Number(k[k.length - 1].close).toFixed(2) : '-'
})

watch([kPeriod, () => selected.value?.code], async ([period, code]) => {
  const requestId = ++chartRequestId
  chartBars.value = null
  chartLoading.value = Boolean(code && period !== '日K')
  if (!code || period === '日K') return

  try {
    const data = await fetchKline(code, apiPeriod[period])
    if (requestId !== chartRequestId) return
    chartBars.value = { code, period, items: data.items, dates: data.dates }
  } catch (e) {
    if (requestId === chartRequestId) showApiError(e)
  } finally {
    if (requestId === chartRequestId) chartLoading.value = false
  }
})

// 行情图表面板左侧的关键指标
const marketStats = computed(() => {
  const s = state.selected
  if (!s || !s.kline?.length) return []
  const k = s.kline
  const last = k[k.length - 1]
  const pre = k.length > 1 ? k[k.length - 2] : last
  const closes = k.map((d) => d.close)
  const maN = (n) => (closes.length >= n ? closes.slice(-n).reduce((a, b) => a + b, 0) / n : null)
  const pct = ((last.close - pre.close) / pre.close) * 100
  const upDown = pct >= 0 ? 'up' : 'down'
  const maColor = (v) => (v != null ? (last.close >= v ? 'up' : 'down') : '')
  const vol5 = +(k.slice(-5).reduce((a, d) => a + d.volume, 0) / 5).toFixed(0)
  return [
    { label: '最新价', value: `${last.close.toFixed(2)} 元`, cls: upDown },
    { label: '涨跌幅', value: `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`, cls: upDown },
    { label: '区间最高', value: Math.max(...k.map((d) => d.high)).toFixed(2) },
    { label: '区间最低', value: Math.min(...k.map((d) => d.low)).toFixed(2) },
    { label: 'MA5', value: maN(5)?.toFixed(2) ?? '-', cls: maColor(maN(5)) },
    { label: 'MA10', value: maN(10)?.toFixed(2) ?? '-', cls: maColor(maN(10)) },
    { label: 'MA20', value: maN(20)?.toFixed(2) ?? '-', cls: maColor(maN(20)) },
    { label: '5 日均量', value: `${vol5} 万手` },
  ]
})

// 远程搜索：代码精确或名称模糊（节流）
async function onQuery(keyword) {
  clearTimeout(searchTimer)
  const q = String(keyword || '').trim()
  if (!q) {
    candidates.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      candidates.value = await searchStock(q)
    } catch {
      candidates.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

async function loadByCode(code) {
  if (!code) return
  loading.value = true
  try {
    const stock = await loadStock(code)
    selectStock(stock)
  } catch (e) {
    showApiError(e)
  } finally {
    loading.value = false
  }
}

function onPickCode(code) {
  loadByCode(code)
}

// 查询按钮 / 回车：用已选项，否则用候选第一项
async function onPickFirst() {
  const code = selCode.value || candidates.value[0]?.code
  if (code) {
    await loadByCode(code)
  } else {
    ElMessage.warning('未找到该股票，请检查输入')
  }
}

function start() {
  startSimulation()
}
function stop() {
  stopSimulation()
}
function reset() {
  if (state.selected) selectStock(state.selected)
}

// 默认加载贵州茅台（真实数据）
loadByCode('600519')
</script>

<style scoped>
.home {
  width: 100%;
  max-width: 1760px;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 20px clamp(16px, 2vw, 32px) 60px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.toolbar {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.search-box {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.stock-select {
  width: 340px;
}
.mode-badge {
  display: flex;
  gap: 8px;
}

/* 行情头 */
.stock-header {
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 28px;
  flex-wrap: wrap;
}
.stock-name {
  font-size: 22px;
  font-weight: 800;
}
.stock-code {
  font-size: 12px;
  margin-top: 2px;
}
.stock-quote {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.stock-price {
  font-size: 28px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}
.stock-change {
  font-size: 15px;
  font-weight: 700;
}
.stock-meta {
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
  margin-left: auto;
}
.sm-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}
.sm-item b {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.sm-item .tiny {
  font-size: 10px;
  color: var(--text-3);
  margin-left: 1px;
}

/* 行情图表面板 */
.market-panel {
  padding: 0 18px 16px;
}
.market-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 6px;
}
.market-title {
  font-size: 15px;
  font-weight: 700;
}
.market-title .faint {
  font-size: 12px;
  font-weight: 400;
  margin-left: 6px;
}
.market-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}
.market-foot {
  margin-top: 6px;
  font-size: 12px;
}
.market-body {
  display: flex;
  gap: 18px;
  align-items: stretch;
}
.market-stats {
  width: 208px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}
.ms-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding: 9px 13px;
  background: var(--panel-2);
  border-radius: 8px;
}
.ms-item b {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.market-chart {
  flex: 1;
  min-width: 0;
}
.chart-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.ma-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-2);
}
/* Element Plus 默认给 .el-checkbox 加了 30px 右外边距，导致「均线」和说明文字离很远 */
.ma-switch :deep(.el-checkbox) {
  margin-right: 0;
  height: 26px;
}
.ma-switch :deep(.el-checkbox__label) {
  padding-left: 5px;
}
.ma-switch :deep(.el-checkbox + .el-checkbox) {
  margin-left: 4px;
}
.ma-switch b {
  color: var(--text);
}
.ma-switch .faint {
  margin-left: 2px;
}

.stages {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 14px 12px;
}

.columns {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  align-items: start;
}
.col-left {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.col-right {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
}
.stage-section {
  padding: 16px;
}
.stage-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.stage-idx {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: rgba(79, 124, 255, 0.14);
  border: 1px solid rgba(79, 124, 255, 0.35);
  color: var(--accent);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 800;
}
.stage-label {
  font-size: 16px;
  font-weight: 700;
}
.stage-desc {
  font-size: 12px;
}
.stage-state {
  margin-left: auto;
}
.running-section .stage-idx {
  background: rgba(212, 167, 44, 0.12);
  border-color: rgba(212, 167, 44, 0.4);
  color: var(--gold);
}
.running-placeholder {
  display: flex;
  align-items: center;
  font-size: 13px;
  padding: 6px 0;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.event-wrap {
  max-height: 480px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 1024px) {
  .columns {
    grid-template-columns: 1fr;
  }
  .col-right {
    position: static;
  }
}

@media (max-width: 900px) {
  .market-body {
    flex-direction: column;
  }
  .market-stats {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .ms-item {
    flex: 1 1 120px;
  }
}
</style>
