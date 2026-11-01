<template>
  <div class="page">
    <div class="panel page-head">
      <div>
        <div class="page-title">{{ title }}</div>
        <div class="faint">{{ subtitle }}</div>
      </div>
      <div class="head-actions">
        <el-tag v-if="pmDecision" effect="dark" :type="pmTagType">
          {{ ACTION_TEXT[pmDecision.action] || pmDecision.action }} · 置信度
          {{ Math.round((pmDecision.confidence || 0) * 100) }}%
        </el-tag>
        <el-button size="small" :icon="ArrowLeft" @click="goBack">返回</el-button>
      </div>
    </div>

    <div v-if="loading" class="panel faint detail-placeholder">加载中…</div>
    <div v-else-if="!stages" class="panel faint detail-placeholder">{{ emptyMessage }}</div>
    <template v-else>
      <div v-for="stage in visibleStages" :key="stage.key" class="panel report-section">
        <div class="section-head">
          <b>{{ stage.label }}</b>
          <span class="faint">{{ stage.desc }}</span>
        </div>
        <StageRender :stage-key="stage.key" :data="stages[stage.key]" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { STAGES } from '../features/analysis/content'
import { getAnalysisTask } from '../api/analysis'
import {
  ACTION_TEXT,
  PERIOD_TEXT,
  STATUS_TEXT,
  formatTime,
  taskResultToStages,
} from '../features/analysis/taskResult'
import StageRender from '../components/StageRender.vue'

const route = useRoute()
const router = useRouter()
const task = ref(null)
const loading = ref(false)

const stages = computed(() => (task.value?.result ? taskResultToStages(task.value.result) : null))
const pmDecision = computed(() => task.value?.result?.pm_decision || null)
const visibleStages = computed(() => STAGES.filter((stage) => stages.value?.[stage.key]))

const title = computed(() => {
  const result = task.value?.result
  if (result?.stock_name) return `${result.stock_name}（${result.stock_code}）分析报告`
  const code = task.value?.request?.stock_code
  return code ? `${code} 分析报告` : '分析报告'
})

const subtitle = computed(() => {
  const result = task.value?.result
  if (!result) {
    return task.value ? `任务状态：${STATUS_TEXT[task.value.status] || task.value.status}` : ''
  }
  const period = PERIOD_TEXT[result.period] || result.period || ''
  const range = result.actual_start_date && result.actual_end_date
    ? `${result.actual_start_date} 至 ${result.actual_end_date}`
    : ''
  return [period, range, `完成于 ${formatTime(task.value.updated_at)}`].filter(Boolean).join(' · ')
})

const pmTagType = computed(
  () => ({ buy: 'danger', reduce: 'warning', avoid: 'success' })[pmDecision.value?.action] || 'info'
)

const emptyMessage = computed(() => {
  if (!task.value) return '任务不存在或已被清理'
  const status = STATUS_TEXT[task.value.status] || task.value.status
  return `该任务当前状态为「${status}」，没有可展示的报告`
})

async function load() {
  loading.value = true
  try {
    task.value = await getAnalysisTask(route.params.taskId)
  } catch (e) {
    task.value = null
    ElMessage.error(`加载报告失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/reports')
}

onMounted(load)
watch(() => route.params.taskId, (value) => {
  if (value) load()
})
</script>
