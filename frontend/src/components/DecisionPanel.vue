<template>
  <div class="decision-panel">
    <!-- 运行统计 -->
    <div class="panel stat-block">
      <div class="stat-row">
        <div class="stat">
          <div class="stat-num">{{ progress }}%</div>
          <div class="faint">任务进度</div>
        </div>
        <div class="stat">
          <div class="stat-num tabular">{{ state.elapsed }}s</div>
          <div class="faint">运行耗时</div>
        </div>
        <div class="stat">
          <div class="stat-num">{{ doneCount }}/6</div>
          <div class="faint">完成阶段</div>
        </div>
      </div>
      <el-progress :percentage="progress" :stroke-width="6" :show-text="false" :color="progressColor" />
      <div v-if="state.running && currentStage" class="current-stage faint">
        当前阶段：{{ currentStage.label }} · {{ currentStage.desc }}
      </div>
    </div>

    <!-- 最终决策 -->
    <div v-if="decision" class="panel decision-block">
      <div class="decision-title">
        最终决策 <span class="faint">(PM)</span>
      </div>
      <div class="decision-hero" :class="decisionTone">
        <div class="hero-action">{{ actionLabel }}</div>
        <div class="hero-conf">
          <span class="faint">置信度</span>
          <b>{{ Math.round((decision.confidence || 0) * 100) }}%</b>
        </div>
      </div>
      <div v-if="decision.target_price != null || decision.stop_price != null" class="decision-prices">
        <div class="decision-price">
          <span class="faint">{{ priceLabels.target }}</span>
          <b>{{ fmtPrice(decision.target_price) }}</b>
        </div>
        <div class="decision-price">
          <span class="faint">{{ priceLabels.stop }}</span>
          <b>{{ fmtPrice(decision.stop_price) }}</b>
        </div>
      </div>
      <div v-if="decision.prices_estimated" class="price-note faint">
        模型未给出有效价位，以上为系统按近期 K 线估算
      </div>
      <div class="decision-rationale">{{ decision.rationale }}</div>
      <div v-if="decision.key_risks?.length" class="decision-risks">
        <div class="decision-risks-title faint">主要风险</div>
        <ul>
          <li v-for="(risk, i) in decision.key_risks" :key="i">{{ risk }}</li>
        </ul>
      </div>
      <div class="disclaimer faint">以上为研究结论，不构成投资建议。</div>
    </div>

    <!-- 空态 -->
    <div v-else class="panel decision-idle">
      <el-icon :size="40"><Flag /></el-icon>
      <div class="muted">等待分析结果…</div>
      <div class="faint" style="font-size: 12px">点击「开始分析」后，六个阶段会依次返回分析师、辩论、提案、风控与 PM 结论</div>
      <div class="faint" style="font-size: 11px; margin-top: 10px">数据接入 → 研报 → 辩论 → 提案 → 风控 → 决策</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { state, progressPercent } from '../features/analysis/pipeline'
import { STAGES } from '../features/analysis/content'

const progress = computed(() => progressPercent())
const doneCount = computed(() => STAGES.filter((s) => state.completed[s.key]).length)
const currentStage = computed(() =>
  state.running && state.currentIndex >= 0 ? STAGES[state.currentIndex] : null
)
const ACTION_TEXT = { buy: '买入', hold: '持有', reduce: '减仓', avoid: '回避' }
const decision = computed(() => state.completed.pm || null)
const actionLabel = computed(() =>
  decision.value ? ACTION_TEXT[decision.value.action] || decision.value.action : ''
)
const decisionTone = computed(
  () => ({ buy: 'up', reduce: 'down', avoid: 'down', hold: 'neutral' })[decision.value?.action] || 'neutral'
)
const priceLabels = computed(() =>
  ['buy', 'hold'].includes(decision.value?.action)
    ? { target: '目标价', stop: '止损价' }
    : { target: '回补参考价', stop: '失效价' }
)
const fmtPrice = (value) => (value == null ? '-' : `${Number(value).toFixed(2)} 元`)
const progressColor = computed(() => {
  const p = progress.value
  return p === 100 ? '#22c55e' : p > 40 ? '#d4a72c' : '#4f7cff'
})
</script>

<style scoped>
.decision-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.stat-block {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.stat-row {
  display: flex;
  justify-content: space-between;
}
.stat {
  text-align: center;
  flex: 1;
}
.stat-num {
  font-size: 20px;
  font-weight: 800;
}
.tabular {
  font-variant-numeric: tabular-nums;
}
.current-stage {
  font-size: 12px;
  text-align: center;
}
.decision-block {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.decision-title {
  font-weight: 700;
}
.decision-hero {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 14px;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid rgba(120, 130, 160, 0.25);
}
.decision-hero.up {
  background: var(--up-bg);
  border-color: rgba(239, 68, 68, 0.4);
}
.decision-hero.down {
  background: var(--down-bg);
  border-color: rgba(34, 197, 94, 0.4);
}
.decision-hero.up .hero-action {
  color: var(--up);
}
.decision-hero.down .hero-action {
  color: var(--down);
}
.hero-action {
  font-size: 28px;
  font-weight: 900;
  letter-spacing: 2px;
}
.hero-conf {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 13px;
}
.hero-conf b {
  font-size: 20px;
}
.decision-rationale {
  line-height: 1.8;
  color: var(--text-2);
}
.decision-prices {
  display: flex;
  gap: 10px;
}
.decision-price {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--panel-2);
  border: 1px solid var(--border);
}
.decision-price b {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}
.price-note {
  font-size: 11px;
  margin-top: -4px;
}
.decision-risks ul {
  margin: 6px 0 0;
  padding-left: 16px;
  color: #f0b9b9;
  font-size: 12px;
  line-height: 1.8;
}
.decision-risks-title {
  font-weight: 600;
}
.disclaimer {
  font-size: 11px;
  line-height: 1.6;
}
.decision-idle {
  padding: 34px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
</style>
