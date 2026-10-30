<template>
  <div class="stage-progress">
    <template v-for="(s, i) in stages" :key="s.key">
      <div class="stage-node" :class="{ done: isDone(s), running: isRunning(s), pending: !isDone(s) && !isRunning(s) }">
        <div class="node-circle">
          <el-icon v-if="isDone(s)"><CircleCheckFilled /></el-icon>
          <el-icon v-else-if="isRunning(s)" class="is-loading"><Loading /></el-icon>
          <span v-else class="node-idx">{{ i + 1 }}</span>
        </div>
        <div class="node-label">{{ s.label }}</div>
        <div class="node-desc faint">{{ s.desc }}</div>
      </div>
      <div v-if="i < stages.length - 1" class="node-link" :class="{ active: isDone(s) }">
        <span class="link-fill" :style="{ width: isDone(s) ? '100%' : '0%' }" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { state } from '../features/analysis/pipeline'
import { STAGES } from '../features/analysis/content'

const stages = STAGES
const isDone = (s) => !!state.completed[s.key]
const isRunning = (s) => state.currentIndex === STAGES.findIndex((x) => x.key === s.key)
</script>

<style scoped>
.stage-progress {
  display: flex;
  align-items: flex-start;
}
.stage-node {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  text-align: center;
  min-width: 0;
}
.node-circle {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 16px;
  transition: all 0.25s;
}
.node-idx {
  font-size: 13px;
}
.stage-node.pending .node-circle {
  background: var(--panel-2);
  border: 1px solid var(--border);
  color: var(--text-3);
}
.stage-node.pending .node-label {
  color: var(--text-3);
}
.stage-node.running .node-circle {
  background: rgba(79, 124, 255, 0.15);
  border: 1px solid var(--accent);
  color: var(--accent);
}
.stage-node.running .node-label {
  color: var(--accent);
  font-weight: 700;
}
.stage-node.done .node-circle {
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid var(--down);
  color: var(--down);
}
.stage-node.done .node-label {
  color: var(--text);
  font-weight: 700;
}
.node-label {
  font-size: 13px;
  white-space: nowrap;
}
.node-desc {
  font-size: 11px;
  white-space: nowrap;
  transform: scale(0.92);
  transform-origin: top center;
}
.node-link {
  flex: 0 0 26px;
  height: 2px;
  background: var(--border);
  margin-top: 16px;
  overflow: hidden;
  border-radius: 1px;
}
.node-link .link-fill {
  display: block;
  height: 100%;
  background: var(--down);
  transition: width 0.4s;
}
</style>
