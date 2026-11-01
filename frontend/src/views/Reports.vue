<template>
  <div class="page">
    <div class="panel page-head">
      <div>
        <div class="page-title">研究报告</div>
        <div class="faint">已完成任务的六阶段完整报告</div>
      </div>
      <div class="head-actions">
        <el-button size="small" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="panel table-panel">
      <el-table
        v-loading="loading"
        :data="reports"
        size="small"
        empty-text="暂无已完成的分析任务"
        style="width: 100%"
        @row-click="openDetail"
      >
        <el-table-column label="完成时间" width="190">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column prop="stock_code" label="股票" width="110" />
        <el-table-column label="周期" width="80">
          <template #default="{ row }">{{ PERIOD_TEXT[row.period] || '-' }}</template>
        </el-table-column>
        <el-table-column label="任务 ID" min-width="200">
          <template #default="{ row }"><span class="faint">{{ row.task_id.slice(0, 12) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button text size="small" @click.stop="openDetail(row)">查看报告</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchRecentTasks } from '../api/analysis'
import { PERIOD_TEXT, formatTime } from '../features/analysis/taskResult'

const router = useRouter()
const reports = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const tasks = await fetchRecentTasks(50)
    reports.value = tasks.filter((task) => task.status === 'completed')
  } catch (e) {
    ElMessage.error(`加载报告失败：${e.message}`)
    reports.value = []
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  router.push(`/reports/${row.task_id}`)
}

onMounted(load)
</script>
