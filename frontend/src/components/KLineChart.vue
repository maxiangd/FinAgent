<template>
  <v-chart
    ref="chartEl"
    class="k-chart"
    :option="option"
    autoresize
    :style="{ height: props.height }"
    @datazoom="onDataZoom"
  />
</template>

<script setup>
import { computed, watch, ref } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { CandlestickChart, BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { calcMA, calcMACD, calcKDJ, calcRSI } from '../features/market/indicators'
import { chartPrefs } from '../features/analysis/pipeline'

use([
  CanvasRenderer,
  CandlestickChart,
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
])

const props = defineProps({
  stock: { type: Object, required: true },
  period: { type: String, default: '日K' }, // 日K / 周K / 月K
  height: { type: String, default: '300px' },
  indicator: { type: String, default: 'macd' }, // none / vol / macd / kdj / rsi（实际读 chartPrefs）
})
const emit = defineEmits(['count'])

const UP = '#ef4444'
const DOWN = '#16a34a'
const MA_COLORS = ['#d4a72c', '#4f7cff', '#a855f7', '#06b6d4'] // MA5/10/20/60
const MA_PERIODS = [5, 10, 20, 60]
// 均线图例文字样式：颜色与线一致
const maRichStyle = Object.fromEntries(
  MA_PERIODS.map((n, i) => [`MA${n}`, { color: MA_COLORS[i], fontSize: 10 }])
)

const series = computed(() => {
  const s = props.stock
  // 异步加载期间 stock 可能为 null
  if (!s || !Array.isArray(s.kline) || !Array.isArray(s.dates)) {
    return { kline: [], dates: [], values: [] }
  }
  const { kline, dates } = s.klinePeriod === props.period
    ? { kline: s.kline, dates: s.dates }
    : props.period === '日K'
      ? { kline: s.kline, dates: s.dates }
      : { kline: [], dates: [] }
  return {
    dates,
    kline,
    values: kline.map((d) => [d.open, d.close, d.low, d.high]),
  }
})

watch(
  () => series.value.dates.length,
  (n) => emit('count', n),
  { immediate: true }
)

// 缩放窗口按周期区分：日K看近段；月K默认看全部
const zoomStart = computed(() =>
  props.period === '日K' ? 75 : props.period === '周K' ? 55 : 10
)

// 当前可见窗口（百分比）。zoomWin 故意用普通对象而非 ref：
// 拖拽/滚轮期间若触发 Vue 重算，vue-echarts 会用 notMerge 重绘整个 option，
// 而重绘会销毁重建 dataZoom 的 RoamController，正在进行的拖拽手势会被打断
// （表现为拖一大段只挪一点点）。所以窗口状态不进响应式，标注走增量 setOption。
const chartEl = ref(null)
const zoomWin = { s: 75, e: 100 }
function liveZoom() {
  const inst = chartEl.value?.chart
  if (inst) {
    try {
      const dz = inst.getOption().dataZoom
      const d0 = Array.isArray(dz) ? (Array.isArray(dz[0]) ? dz[0][0] : dz[0]) : null
      if (d0 && typeof d0.start === 'number') return { s: d0.start, e: d0.end ?? 100 }
    } catch { /* ignore */ }
  }
  return { s: zoomStart.value, e: 100 }
}
// 每帧最多同步一次，避免拖拽 slider 时高频重算
let zoomRaf = 0
function onDataZoom() {
  if (zoomRaf) return
  zoomRaf = requestAnimationFrame(() => {
    zoomRaf = 0
    const v = liveZoom()
    if (Math.abs(v.s - zoomWin.s) > 0.01 || Math.abs(v.e - zoomWin.e) > 0.01) {
      zoomWin.s = v.s
      zoomWin.e = v.e
      applyRangeMarks()
    }
  })
}
// 增量更新区间标注：只 merge kline 系列的 markLine/markPoint，不动 dataZoom/坐标轴，
// 因此不会打断拖拽手势
function applyRangeMarks() {
  const inst = chartEl.value?.chart
  const kline = series.value.kline
  if (!inst || !kline.length || inst.isDisposed()) return
  inst.setOption({ series: [{ id: 'kline', ...rangeMarks(kline) }] }, { lazyUpdate: true })
}
// 周期切换：把窗口重置为该周期默认窗口（同时同步 zoomWin 与实例）
watch(
  () => zoomStart.value,
  (v) => {
    zoomWin.s = v
    zoomWin.e = 100
    const inst = chartEl.value?.chart
    if (inst) inst.dispatchAction({ type: 'dataZoom', start: v, end: 100 })
  },
  { immediate: true }
)

// 可见窗口对应的数据下标区间（floor/ceil 会把边缘半根也算进来）
function windowRange(n) {
  if (n <= 1) return { i0: 0, i1: Math.max(0, n - 1) }
  const i0 = Math.max(0, Math.floor((zoomWin.s / 100) * (n - 1)))
  const i1 = Math.min(n - 1, Math.ceil((zoomWin.e / 100) * (n - 1)))
  return { i0: Math.min(i0, i1), i1: Math.max(i0, i1) }
}

// 当前可见区间的最高/最低。
// 默认：两根短箭头指向取到极值的那根 K 线；
// 打开「箱体边界」：两条横虚线 + 右端箭头 + 价格标签（同花顺/雪球那种箱体标法）。
function rangeMarks(kline) {
  const n = kline.length
  const empty = { markLine: { data: [] }, markPoint: { data: [] } }
  if (!n) return empty
  const { i0, i1 } = windowRange(n)
  let hi = -Infinity
  let lo = Infinity
  let hiIdx = -1
  let loIdx = -1
  for (let i = i0; i <= i1; i++) {
    const d = kline[i]
    if (!d) continue
    if (d.high > hi) {
      hi = d.high
      hiIdx = i
    }
    if (d.low < lo) {
      lo = d.low
      loIdx = i
    }
  }
  if (!Number.isFinite(hi) || !Number.isFinite(lo)) return empty
  return chartPrefs.rangeBox
    ? { markLine: boxMarkLine(hi, lo), markPoint: { data: [] } }
    : { markLine: { data: [] }, markPoint: arrowMarkPoint(hi, lo, hiIdx, loIdx, i0, i1) }
}

function boxMarkLine(hi, lo) {
  const mark = (v, color, text, pos) => ({
    yAxis: v,
    symbol: ['none', 'arrow'],
    symbolSize: 9,
    lineStyle: { color, type: 'dashed', width: 1, opacity: 0.9 },
    label: {
      show: true,
      position: pos,
      formatter: `${text} ${v.toFixed(2)}`,
      color,
      fontSize: 10,
      fontWeight: 700,
      backgroundColor: 'rgba(13,17,28,0.92)',
      borderColor: color,
      borderWidth: 1,
      padding: [2, 4],
      borderRadius: 3,
    },
  })
  return {
    silent: true,
    animation: false,
    data: [
      mark(hi, UP, '最高', 'insideEndTop'),
      mark(lo, DOWN, '最低', 'insideEndBottom'),
    ],
  }
}

function arrowMarkPoint(hi, lo, hiIdx, loIdx, i0, i1) {
  // 标签默认放箭头右侧；箭头已经靠近窗口右边界时翻到左侧，避免被裁掉
  const span = Math.max(1, i1 - i0)
  const labelPos = (idx) => ((idx - i0) / span > 0.8 ? 'left' : 'right')
  const label = (v, color, pos) => ({
    show: true,
    position: pos,
    distance: 3,
    formatter: v.toFixed(2),
    color,
    fontSize: 10,
    fontWeight: 700,
    backgroundColor: 'rgba(13,17,28,0.86)',
    padding: [1, 3],
    borderRadius: 3,
  })
  return {
    silent: true,
    animation: false,
    data: [
      {
        coord: [hiIdx, hi],
        symbol: 'arrow',
        symbolSize: 9,
        symbolRotate: 180, // 箭头朝下，指向最高价
        symbolOffset: [0, -8],
        itemStyle: { color: UP },
        label: label(hi, UP, labelPos(hiIdx)),
      },
      {
        coord: [loIdx, lo],
        symbol: 'arrow',
        symbolSize: 9,
        symbolOffset: [0, 8], // 箭头朝上，指向最低价
        itemStyle: { color: DOWN },
        label: label(lo, DOWN, labelPos(loIdx)),
      },
    ],
  }
}

// Tooltip 中文展示：K线开收高低 + 涨跌幅，按当前均线/副图指标联动
function tooltipFormatter(params) {
  const i = params[0].dataIndex
  const k = series.value.kline[i]
  if (!k) return ''
  const pre = series.value.kline[i - 1] || k
  const pct = pre.close ? ((k.close - pre.close) / pre.close) * 100 : 0
  const up = k.close >= pre.close
  const c = up ? '#ef4444' : '#16a34a'
  const fmt = (v, n = 2) => (v == null ? '-' : Number(v).toFixed(n))
  const byId = {}
  params.forEach((p) => { byId[p.seriesId] = p })
  // 注意：axis 触发时 params[].data 已是 dataIndex 处的单条数据
  const val = (id) => {
    const p = byId[id]
    if (!p) return null
    const d = p.data
    return d && typeof d === 'object' ? d.value : d
  }
  const num = (id, n) => { const v = val(id); return v == null ? '-' : Number(v).toFixed(n) }

  let html = `<div style="font-weight:700;margin-bottom:5px">${series.value.dates[i]}</div>`
  html += `开 <b style="color:${c}">${fmt(k.open)}</b>　收 <b style="color:${c}">${fmt(k.close)}</b> ${pct >= 0 ? '▲' : '▼'} <b style="color:${c}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</b><br/>`
  html += `高 <b style="color:${c}">${fmt(k.high)}</b>　低 <b style="color:${c}">${fmt(k.low)}</b>`

  if (byId.vol) {
    const v = val('vol')
    html += `<br/>成交量 <b>${v == null ? '-' : Number(v).toFixed(0)}</b> 万手`
  }

  const mas = [5, 10, 20, 60].filter((n) => val(`ma-${n}`) != null)
  if (mas.length) html += '<br/>' + mas.map((n) => `MA${n} <b>${fmt(val(`ma-${n}`))}</b>`).join('　')

  if (val('dif') != null) {
    html += `<br/>DIF快线 <b style="color:#f8e16c">${num('dif', 3)}</b>　DEA慢线 <b style="color:#4f7cff">${num('dea', 3)}</b><br/>MACD柱 <b>${num('macd', 3)}</b>`
  }
  if (val('kdj-k') != null) {
    html += `<br/>K值 <b style="color:#f8e16c">${num('kdj-k', 2)}</b>　D值 <b style="color:#4f7cff">${num('kdj-d', 2)}</b>　J值 <b style="color:#a855f7">${num('kdj-j', 2)}</b>`
  }
  if (val('rsi6') != null) {
    html += `<br/>RSI6 <b style="color:#f8e16c">${num('rsi6', 2)}</b>　RSI12 <b style="color:#4f7cff">${num('rsi12', 2)}</b>　RSI24 <b style="color:#a855f7">${num('rsi24', 2)}</b>`
  }
  return html
}

const hasSub = computed(() => props.indicator !== 'none')

// 主图指标（均线）
const maSeries = computed(() => {
  if (!chartPrefs.showMA) return []
  const closes = series.value.kline.map((d) => d.close)
  return [5, 10, 20, 60].map((n, idx) => ({
    id: `ma-${n}`, // 稳定 id：切换开关时 ECharts 会正确增删对应系列
    name: `MA${n}`,
    type: 'line',
    data: calcMA(closes, n),
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 1.1, color: MA_COLORS[idx] },
    itemStyle: { color: MA_COLORS[idx] },
  }))
})

// 副图指标
const subSeries = computed(() => {
  const k = series.value.kline
  const closes = k.map((d) => d.close)
  switch (props.indicator) {
    case 'vol':
      return [
        {
          id: 'vol',
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          barWidth: '70%',
          data: k.map((d, i) => ({
            value: d.volume,
            itemStyle: { color: i > 0 && d.close >= k[i - 1].close ? UP : DOWN },
          })),
        },
      ]
    case 'macd': {
      const { dif, dea, hist } = calcMACD(closes)
      return [
        {
          id: 'macd',
          name: 'MACD',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          barWidth: '60%',
          data: hist.map((v) =>
            v == null ? null : { value: v, itemStyle: { color: v >= 0 ? UP : DOWN } }
          ),
        },
        { id: 'dif', name: 'DIF快线', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: dif, symbol: 'none', lineStyle: { width: 1.1, color: '#f8e16c' }, itemStyle: { color: '#f8e16c' } },
        { id: 'dea', name: 'DEA慢线', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: dea, symbol: 'none', lineStyle: { width: 1.1, color: '#4f7cff' }, itemStyle: { color: '#4f7cff' } },
      ]
    }
    case 'kdj': {
      const kdj = calcKDJ(k)
      return [
        { id: 'kdj-k', name: 'K值', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: kdj.k, symbol: 'none', lineStyle: { width: 1.1, color: '#f8e16c' }, itemStyle: { color: '#f8e16c' } },
        { id: 'kdj-d', name: 'D值', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: kdj.d, symbol: 'none', lineStyle: { width: 1.1, color: '#4f7cff' }, itemStyle: { color: '#4f7cff' } },
        { id: 'kdj-j', name: 'J值', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: kdj.j, symbol: 'none', lineStyle: { width: 1.1, color: '#a855f7' }, itemStyle: { color: '#a855f7' } },
      ]
    }
    case 'rsi': {
      const r = calcRSI(closes)
      return [
        { id: 'rsi6', name: 'RSI6', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: r.rsi6, symbol: 'none', lineStyle: { width: 1.1, color: '#f8e16c' }, itemStyle: { color: '#f8e16c' } },
        { id: 'rsi12', name: 'RSI12', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: r.rsi12, symbol: 'none', lineStyle: { width: 1.1, color: '#4f7cff' }, itemStyle: { color: '#4f7cff' } },
        { id: 'rsi24', name: 'RSI24', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: r.rsi24, symbol: 'none', lineStyle: { width: 1.1, color: '#a855f7' }, itemStyle: { color: '#a855f7' } },
      ]
    }
    default:
      return []
  }
})

const subYAxis = computed(() => {
  switch (props.indicator) {
    case 'vol':
      return { gridIndex: 1, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false } }
    case 'macd':
      return { gridIndex: 1, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#636d87', fontSize: 10 }, splitLine: { lineStyle: { color: '#1a2133' } } }
    case 'kdj':
    case 'rsi':
      return { gridIndex: 1, min: 0, max: 100, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#636d87', fontSize: 10 }, splitLine: { lineStyle: { color: '#1a2133' } } }
    default:
      return null
  }
})

// 与参考项目一致的 K 线画法 + 可切换副图指标
const option = computed(() => {
  const sub = hasSub.value
  // 取当前窗口（非响应式：拖拽期间不触发整图重绘，避免打断手势）
  const zw = zoomWin
  const marks = rangeMarks(series.value.kline)
  const dZoom = [
    { type: 'inside', start: zw.s, end: zw.e },
    { start: zw.s, end: zw.e, borderColor: '#232c42', backgroundColor: '#10141f' },
  ]
  if (sub) dZoom[0].xAxisIndex = [0, 1]
  if (sub) dZoom[1].xAxisIndex = [0, 1]

  return {
    backgroundColor: 'transparent',
    animation: false,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(20, 25, 39, 0.96)',
      borderColor: '#232c42',
      textStyle: { color: '#e6ebf4', fontSize: 12 },
      formatter: tooltipFormatter,
    },
    legend: [
      {
        // 副图指标图例（左侧）
        show: sub,
        top: 2,
        left: 8,
        icon: 'roundRect',
        itemWidth: 10,
        itemHeight: 2,
        textStyle: { color: '#9aa5bd', fontSize: 10 },
        data: subSeries.value.map((s) => s.name),
        selectedMode: false,
      },
      {
        // 均线图例：文字颜色与均线一致，便于对应
        show: chartPrefs.showMA,
        top: 2,
        right: 8,
        icon: 'roundRect',
        itemWidth: 10,
        itemHeight: 2,
        itemGap: 10,
        textStyle: { fontSize: 10, rich: maRichStyle },
        formatter: (name) => `{${name}|${name}}`,
        data: maSeries.value.map((s) => s.name),
        selectedMode: false,
      },
    ],
    grid: sub
      ? [
          { left: 44, right: 20, top: 26, height: '56%' },
          { left: 44, right: 20, top: '66%', height: '22%' },
        ]
      : [{ left: 44, right: 20, top: 26, height: '72%' }],
    xAxis: [
      {
        type: 'category',
        data: series.value.dates,
        boundaryGap: true,
        axisLine: { onZero: false, lineStyle: { color: '#232c42' } },
        axisLabel: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      ...(sub
        ? [{
            type: 'category',
            data: series.value.dates,
            gridIndex: 1,
            boundaryGap: true,
            axisLine: { lineStyle: { color: '#232c42' } },
            axisLabel: { color: '#636d87', fontSize: 10 },
            axisTick: { show: false },
            splitLine: { show: false },
          }]
        : []),
    ],
    yAxis: [
      {
        scale: true,
        type: 'value',
        // 上下留白：否则窗口最高/最低正好压在坐标轴边缘，标注线和标签会被裁掉
        boundaryGap: ['10%', '10%'],
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#636d87', fontSize: 11 },
        splitLine: { lineStyle: { color: '#1a2133' } },
      },
      ...(subYAxis.value ? [subYAxis.value] : []),
    ],
    dataZoom: dZoom,
    series: [
      {
        id: 'kline',
        type: 'candlestick',
        name: 'K线',
        data: series.value.values,
        itemStyle: {
          color: UP,
          color0: DOWN,
          borderColor: UP,
          borderColor0: DOWN,
        },
        markLine: marks.markLine,
        markPoint: marks.markPoint,
      },
      ...maSeries.value,
      ...subSeries.value,
    ],
  }
})
</script>

<style scoped>
.k-chart {
  width: 100%;
  display: block;
}
</style>

<!-- vue-echarts 容器链：根元素定高后，内部 .vue-echarts-inner 需要显式撑满 -->
<style>
.k-chart > .vue-echarts-inner {
  height: 100% !important;
  width: 100%;
}
</style>
