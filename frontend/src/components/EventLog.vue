<template>
  <div class="event-log">
    <div class="log-head">
      <span class="log-title">数据接入事件</span>
      <el-tag v-if="state.running" type="primary" effect="dark" size="small" class="live-tag">
        <span class="live-dot" /> LIVE
      </el-tag>
      <el-tag v-else-if="state.finished" type="success" effect="dark" size="small">完成</el-tag>
      <el-tag v-else type="info" effect="plain" size="small">IDLE</el-tag>
    </div>
    <div class="log-body">
      <div v-if="!state.events.length" class="log-empty faint">
        <el-icon :size="26"><Promotion /></el-icon>
        <div>选择股票和分析区间后点击「开始接入」，<br />实际数据获取状态会显示在这里</div>
      </div>
      <div v-for="e in state.events" :key="e.id" class="log-row">
        <span class="log-time faint">{{ e.time }}</span>
        <span class="log-stage faint">{{ e.stage }}</span>
        <span class="log-agent" :class="e.type">{{ e.agent }}</span>
        <span class="log-text muted">{{ e.text }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { state } from '../features/analysis/pipeline'
</script>

<style scoped>
.event-log {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.log-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  font-weight: 700;
}
.log-title {
  margin-right: auto;
}
.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #7dd3c8;
  display: inline-block;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% {
    opacity: 0.3;
  }
}
.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.log-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  font-size: 12px;
  margin-top: 40px;
}
.log-row {
  display: grid;
  grid-template-columns: 52px 64px auto 1fr;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  line-height: 1.5;
}
.log-time {
  font-variant-numeric: tabular-nums;
}
.log-stage {
  background: var(--panel-2);
  border-radius: 4px;
  padding: 1px 6px;
  text-align: center;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-agent {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-agent.success {
  color: var(--down);
}
.log-agent.warn {
  color: var(--gold);
}
.log-agent.error {
  color: var(--up);
}
.log-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
