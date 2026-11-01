<template>
  <div class="page">
    <div class="panel page-head">
      <div>
        <div class="page-title">历史任务</div>
        <div class="faint">最近 50 个分析任务，包含服务重启前的记录</div>
      </div>
      <div class="head-actions">
        <el-segmented v-model="statusFilter" :options="filterOptions" size="small" />
        <el-button size="small" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="panel table-panel">
      <el-table
        v-loading="loading"
        :data="filteredTasks"
        size="small"
        empty-text="暂无任务"
        style="width: 100%"
      >
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="stock_code" label="股票" width="110" />
        <el-table-column label="周期" width="80">
          <template #default="{ row }">{{ PERIOD_TEXT[row.period] || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">
              {{ STATUS_TEXT[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务 ID" min-width="180">
          <template #default="{ row }"><span class="faint">{{ row.task_id.slice(0, 12) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <el-button text size="small" :disabled="row.status !== 'completed'" @click="openReport(row)">
              查看报告
            </el-button>
            <el-button text size="small" @click="resume(row)">载入工作台</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchRecentTasks } from '../api/analysis'
import { saveLastTask } from '../features/analysis/pipeline'
import { PERIOD_TEXT, STATUS_TEXT, formatTime, statusTagType } from '../features/analysis/taskResult'

const router = useRouter()
const tasks = ref([])
const loading = ref(false)
const statusFilter = ref('全部')
const filterOptions = ['全部', '已完成', '失败', '执行中']
const STATUS_BY_LABEL = { 已完成: 'completed', 失败: 'failed', 执行中: 'running' }

const filteredTasks = computed(() => {
  const status = STATUS_BY_LABEL[statusFilter.value]
  return status ? tasks.value.filter((task) => task.status === status) : tasks.value
})

async function load() {
  loading.value = true
  try {
    tasks.value = await fetchRecentTasks(50)
  } catch (e) {
    ElMessage.error(`加载任务失败：${e.message}`)
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function openReport(row) {
  router.push(`/reports/${row.task_id}`)
}

function resume(row) {
  saveLastTask(row.task_id)
  ElMessage.success('已记录该任务，正在载入工作台')
  router.push('/')
}

onMounted(load)
</script>
