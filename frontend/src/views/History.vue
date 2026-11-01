<template>
  <div class="page">
    <div class="panel page-head">
      <div>
        <div class="page-title">任务与报告</div>
        <div class="faint">全部分析任务及其六阶段报告（最近 50 条），含服务重启前的记录</div>
      </div>
      <div class="head-actions">
        <el-segmented v-model="statusFilter" :options="filterOptions" size="small" />
        <el-button
          size="small"
          type="danger"
          :icon="Delete"
          :disabled="!selectedIds.length"
          :loading="deleting"
          @click="removeSelected"
        >
          批量删除<span v-if="selectedIds.length">（{{ selectedIds.length }}）</span>
        </el-button>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="panel table-panel">
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="filteredTasks"
        row-key="task_id"
        size="small"
        empty-text="暂无任务"
        style="width: 100%"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="股票" width="160">
          <template #default="{ row }">
            <span v-if="row.stock_name">{{ row.stock_name }} </span>
            <span class="faint">{{ row.stock_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="周期" width="80">
          <template #default="{ row }">{{ PERIOD_TEXT[row.period] || '-' }}</template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.pm_action" size="small" :type="ACTION_TAG_TYPE[row.pm_action] || 'info'">
              {{ ACTION_TEXT[row.pm_action] || row.pm_action }}
            </el-tag>
            <span v-else class="faint">-</span>
          </template>
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
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button text size="small" :disabled="row.status !== 'completed'" @click="openReport(row)">
              查看报告
            </el-button>
            <el-button text size="small" @click="resume(row)">载入工作台</el-button>
            <el-button text size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Refresh } from '@element-plus/icons-vue'
import { deleteAnalysisTask, deleteAnalysisTasks, fetchRecentTasks } from '../api/analysis'
import { saveLastTask } from '../features/analysis/pipeline'
import { ACTION_TEXT, PERIOD_TEXT, STATUS_TEXT, formatTime, statusTagType } from '../features/analysis/taskResult'

const ACTION_TAG_TYPE = { buy: 'danger', hold: 'info', reduce: 'warning', avoid: 'success' }

const router = useRouter()
const tasks = ref([])
const loading = ref(false)
const statusFilter = ref('全部')
const filterOptions = ['全部', '已完成', '失败', '执行中']
const STATUS_BY_LABEL = { 已完成: 'completed', 失败: 'failed', 执行中: 'running' }
const tableRef = ref(null)
const selectedIds = ref([])
const deleting = ref(false)

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

function onSelectionChange(rows) {
  selectedIds.value = rows.map((row) => row.task_id)
}

function dropTasks(ids) {
  const removed = new Set(ids)
  tasks.value = tasks.value.filter((task) => !removed.has(task.task_id))
  tableRef.value?.clearSelection()
  selectedIds.value = []
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除后该任务的记录与报告都会移除，且不可恢复。确定删除 ${row.stock_code} 的任务吗？`,
      '删除任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await deleteAnalysisTask(row.task_id)
    dropTasks([row.task_id])
    ElMessage.success('任务已删除')
  } catch (e) {
    ElMessage.error(`删除失败：${e.message}`)
  }
}

async function removeSelected() {
  const ids = [...selectedIds.value]
  try {
    await ElMessageBox.confirm(
      `将删除选中的 ${ids.length} 个任务及其报告，且不可恢复。确定继续吗？`,
      '批量删除任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deleting.value = true
  try {
    const result = await deleteAnalysisTasks(ids)
    dropTasks(result.deleted || [])
    if (result.skipped?.length) {
      ElMessage.warning(
        `已删除 ${result.deleted?.length || 0} 个，${result.skipped.length} 个无法删除（任务可能仍在执行）`
      )
    } else {
      ElMessage.success(`已删除 ${result.deleted?.length || 0} 个任务`)
    }
  } catch (e) {
    ElMessage.error(`批量删除失败：${e.message}`)
  } finally {
    deleting.value = false
  }
}

onMounted(load)
</script>
