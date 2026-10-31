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

    <!-- 空态：PM 决策阶段尚未接入 -->
    <div class="panel decision-idle">
      <el-icon :size="40"><Flag /></el-icon>
      <div class="muted">PM 决策待接入</div>
      <div class="faint" style="font-size: 12px">数据接入与行情分析师已由后端真实执行；多空辩论、交易提案、风控、PM 决策尚未接入</div>
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
.decision-idle {
  padding: 34px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
</style>
