<template>
  <div class="page">
    <div class="panel page-head">
      <div>
        <div class="page-title">模拟交易</div>
        <div class="faint">采纳已完成分析任务的 PM 结论建仓，按最新行情估值；研究演示，不接入真实下单</div>
      </div>
      <div class="head-actions">
        <el-button size="small" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button size="small" plain @click="resetAccount">重置账户</el-button>
      </div>
    </div>

    <div class="stat-grid" v-if="portfolio">
      <div class="panel stat-card">
        <div class="faint">总资产</div>
        <b class="stat-value" :class="pnlClass(portfolio.total_pnl)">{{ money(portfolio.total_assets) }}</b>
      </div>
      <div class="panel stat-card">
        <div class="faint">现金</div>
        <b class="stat-value">{{ money(portfolio.cash) }}</b>
      </div>
      <div class="panel stat-card">
        <div class="faint">持仓市值</div>
        <b class="stat-value">{{ money(portfolio.market_value) }}</b>
      </div>
      <div class="panel stat-card">
        <div class="faint">浮动盈亏</div>
        <b class="stat-value" :class="pnlClass(portfolio.unrealized_pnl)">{{ signed(portfolio.unrealized_pnl) }}</b>
      </div>
      <div class="panel stat-card">
        <div class="faint">已实现盈亏</div>
        <b class="stat-value" :class="pnlClass(portfolio.realized_pnl)">{{ signed(portfolio.realized_pnl) }}</b>
      </div>
    </div>

    <div class="panel form-panel">
      <div class="form-title">
        <b>采纳分析结论建仓</b>
        <span class="faint">选择一个已完成的任务，按最新价买入</span>
      </div>
      <div class="form-row">
        <el-select
          v-model="selectedTask"
          class="task-select"
          size="default"
          filterable
          placeholder="选择已完成的分析任务"
          @change="onSelectTask"
        >
          <el-option
            v-for="task in completedTasks"
            :key="task.task_id"
            :label="`${task.stock_code} · ${periodText(task.period)} · ${formatTime(task.created_at)} · ${task.task_id.slice(0, 8)}`"
            :value="task.task_id"
          />
        </el-select>
        <el-tag v-if="selectedPmAction" effect="plain" :type="pmTagType(selectedPmAction)">
          PM：{{ ACTION_TEXT[selectedPmAction] || selectedPmAction }}
        </el-tag>
        <el-input-number v-model="quantity" :min="100" :step="100" :precision="0" size="default" />
        <el-button type="primary" :loading="submitting" @click="openPosition">建仓</el-button>
        <span class="faint">股数需为 100 的整数倍</span>
      </div>
    </div>

    <div class="panel table-panel">
      <div class="table-title">
        <b>当前持仓</b>
        <span class="faint">按最新行情估值</span>
      </div>
      <el-table :data="portfolio?.positions || []" size="small" empty-text="暂无持仓" style="width: 100%">
        <el-table-column label="股票" min-width="150">
          <template #default="{ row }">
            <b>{{ row.stock_name || row.stock_code }}</b>
            <span class="faint"> {{ row.stock_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="90" />
        <el-table-column label="成本价" width="110">
          <template #default="{ row }">{{ money(row.entry_price) }}</template>
        </el-table-column>
        <el-table-column label="现价" width="110">
          <template #default="{ row }">{{ row.current_price == null ? '-' : money(row.current_price) }}</template>
        </el-table-column>
        <el-table-column label="市值" width="130">
          <template #default="{ row }">{{ row.market_value == null ? '-' : money(row.market_value) }}</template>
        </el-table-column>
        <el-table-column label="浮动盈亏" width="160">
          <template #default="{ row }">
            <span :class="pnlClass(row.unrealized_pnl)">
              {{ signed(row.unrealized_pnl) }}
              <template v-if="row.unrealized_pnl_pct != null">（{{ signed(row.unrealized_pnl_pct) }}%）</template>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="PM 决策" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="pmTagType(row.pm_action)">
              {{ ACTION_TEXT[row.pm_action] || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button text size="small" @click="closePosition(row)">平仓</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="panel table-panel">
      <div class="table-title">
        <b>已平仓记录</b>
        <span class="faint">最近 20 条</span>
      </div>
      <el-table :data="portfolio?.closed_positions || []" size="small" empty-text="暂无平仓记录" style="width: 100%">
        <el-table-column label="股票" min-width="150">
          <template #default="{ row }">
            <b>{{ row.stock_name || row.stock_code }}</b>
            <span class="faint"> {{ row.stock_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="90" />
        <el-table-column label="成本价" width="110">
          <template #default="{ row }">{{ money(row.entry_price) }}</template>
        </el-table-column>
        <el-table-column label="平仓价" width="110">
          <template #default="{ row }">{{ money(row.close_price) }}</template>
        </el-table-column>
        <el-table-column label="已实现盈亏" width="140">
          <template #default="{ row }">
            <span :class="pnlClass(row.realized_pnl)">{{ signed(row.realized_pnl) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平仓时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.closed_at) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchRecentTasks, getAnalysisTask } from '../api/analysis'
import {
  closePaperPosition,
  fetchPaperPortfolio,
  openPaperPosition,
  resetPaperAccount,
} from '../api/paper'
import { ACTION_TEXT, PERIOD_TEXT, formatTime } from '../features/analysis/taskResult'

const portfolio = ref(null)
const tasks = ref([])
const loading = ref(false)
const submitting = ref(false)
const selectedTask = ref('')
const selectedPmAction = ref('')
const quantity = ref(100)

const completedTasks = computed(() => tasks.value.filter((task) => task.status === 'completed'))
const periodText = (period) => PERIOD_TEXT[period] || '-'
const pmTagType = (action) =>
  ({ buy: 'danger', reduce: 'warning', avoid: 'success', hold: 'info' })[action] || 'info'
const pnlClass = (value) => (value == null ? '' : value > 0 ? 'up' : value < 0 ? 'down' : '')
const money = (value) =>
  value == null ? '-' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const signed = (value) => {
  if (value == null) return '-'
  const number = Number(value)
  return `${number >= 0 ? '+' : ''}${number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

async function load() {
  loading.value = true
  try {
    const [data, recent] = await Promise.all([fetchPaperPortfolio(), fetchRecentTasks(50)])
    portfolio.value = data
    tasks.value = recent
  } catch (e) {
    ElMessage.error(`加载模拟交易失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function onSelectTask(taskId) {
  selectedPmAction.value = ''
  if (!taskId) return
  try {
    const task = await getAnalysisTask(taskId)
    selectedPmAction.value = task.result?.pm_decision?.action || ''
  } catch {
    /* 详情取不到时不影响建仓，后端会再校验 */
  }
}

async function openPosition() {
  if (!selectedTask.value) {
    ElMessage.warning('请先选择一个已完成的分析任务')
    return
  }
  submitting.value = true
  try {
    const position = await openPaperPosition(selectedTask.value, quantity.value)
    ElMessage.success(
      `已建仓：${position.stock_name || position.stock_code} ${position.quantity} 股 @ ${position.entry_price}`
    )
    await load()
  } catch (e) {
    ElMessage.error(`建仓失败：${e.message}`)
  } finally {
    submitting.value = false
  }
}

async function closePosition(row) {
  try {
    await ElMessageBox.confirm(
      `确认按最新价平仓 ${row.stock_name || row.stock_code}（${row.quantity} 股）？`,
      '平仓确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const position = await closePaperPosition(row.position_id)
    ElMessage.success(`已平仓，已实现盈亏 ${signed(position.realized_pnl)}`)
    await load()
  } catch (e) {
    ElMessage.error(`平仓失败：${e.message}`)
  }
}

async function resetAccount() {
  try {
    await ElMessageBox.confirm('将清空所有持仓并恢复初始资金 100 万，确定？', '重置账户', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    portfolio.value = await resetPaperAccount()
    ElMessage.success('账户已重置')
  } catch (e) {
    ElMessage.error(`重置失败：${e.message}`)
  }
}

onMounted(load)
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 900px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.stat-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat-value {
  font-size: 20px;
  font-weight: 800;
}
.form-panel {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.task-select {
  width: 380px;
  max-width: 100%;
}
.table-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 8px 10px;
}
</style>
