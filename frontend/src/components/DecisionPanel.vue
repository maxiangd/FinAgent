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
      <div class="decision-hero" :class="decision.tone">
        <div class="hero-action">{{ decision.action }}</div>
        <div class="hero-conf">
          <span class="faint">置信度</span>
          <b>{{ decision.confidence == null ? '待模型评估' : `${decision.confidence}%` }}</b>
        </div>
      </div>
      <el-progress v-if="decision.confidence != null" :percentage="+decision.confidence" :stroke-width="6" :show-text="false"
        :color="decision.tone === 'up' ? '#ef4444' : '#22c55e'" />
      <div class="decision-grid">
        <div class="dg-item">
          <span class="faint">目标价</span>
          <b>{{ decision.target }}</b>
        </div>
        <div class="dg-item">
          <span class="faint">止损位</span>
          <b>{{ decision.stop }}</b>
        </div>
        <div class="dg-item">
          <span class="faint">建议仓位</span>
          <b>{{ decision.position }}</b>
        </div>
        <div class="dg-item">
          <span class="faint">持有周期</span>
          <b>{{ decision.horizon }}</b>
        </div>
      </div>
      <div class="decision-risks">
        <div class="decision-risks-title faint">风险提示</div>
        <ul>
          <li v-for="(r, i) in decision.risks" :key="i">{{ r }}</li>
        </ul>
      </div>
      <div class="disclaimer faint">⚠️ 当前分析流程由前端模拟生成，新闻判断尚未接入大模型。</div>
    </div>

    <!-- 空态 -->
    <div v-else class="panel decision-idle">
      <el-icon :size="40"><Flag /></el-icon>
      <div class="muted">等待分析流程接入…</div>
      <div class="faint" style="font-size: 12px">当前先跑通真实数据接入；后续分析阶段接入 LLM 后再生成 PM 决策</div>
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
const decision = computed(() => state.completed.pm || null)
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
}
.decision-hero.up {
  background: var(--up-bg);
  border: 1px solid rgba(239, 68, 68, 0.4);
}
.decision-hero.down {
  background: var(--down-bg);
  border: 1px solid rgba(34, 197, 94, 0.4);
}
.hero-action {
  font-size: 30px;
  font-weight: 900;
  letter-spacing: 2px;
}
.hero-action.up {
  color: var(--up);
}
.hero-action.down {
  color: var(--down);
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
.decision-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.dg-item {
  background: var(--panel-2);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dg-item span {
  font-size: 11px;
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
