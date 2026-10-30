<template>
  <div class="app-shell">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-mark">FA</div>
        <div class="logo-text">
          <b>FinAgent Lab</b>
          <span class="faint">A股多智能体投研平台</span>
        </div>
      </div>
      <nav class="nav">
        <div class="nav-item active">
          <el-icon><Monitor /></el-icon>
          <span>投研工作台</span>
        </div>
        <div class="nav-item disabled">
          <el-icon><Document /></el-icon>
          <span>研究报告</span>
          <el-tag size="small" type="info" effect="plain">规划中</el-tag>
        </div>
        <div class="nav-item disabled">
          <el-icon><Coin /></el-icon>
          <span>模拟交易</span>
          <el-tag size="small" type="info" effect="plain">规划中</el-tag>
        </div>
        <div class="nav-item disabled">
          <el-icon><Clock /></el-icon>
          <span>历史任务</span>
          <el-tag size="small" type="info" effect="plain">规划中</el-tag>
        </div>
      </nav>
      <div class="sidebar-foot faint">
        <div class="pipeline-mini">
          <div class="pm-label">Agent 协作链路</div>
          <div class="pm-chain">
            <span>数据</span><i>→</i><span>研报</span><i>→</i><span>辩论</span><i>→</i>
            <span>提案</span><i>→</i><span>风控</span><i>→</i><span>PM</span>
          </div>
        </div>
        <div style="font-size: 11px">LangGraph · FastAPI · SSE · Vue</div>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="main">
      <div class="topbar">
        <div class="crumb">
          <span class="faint">工作台</span>
          <el-icon class="faint" :size="12"><ArrowRight /></el-icon>
          <span>A 股多智能体投研分析</span>
        </div>
        <div class="topbar-right faint">
          示例任务：贵州茅台(600519) · 观点由 AI 生成，不构成投资建议
        </div>
      </div>
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { Monitor, Document, Coin, Clock, ArrowRight } from '@element-plus/icons-vue'
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #0e131d;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  gap: 20px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-mark {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(135deg, #4f7cff, #7c5cff);
  color: #fff;
  font-weight: 900;
  display: grid;
  place-items: center;
  font-size: 14px;
  flex-shrink: 0;
}
.logo-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.logo-text b {
  font-size: 15px;
}
.logo-text span {
  font-size: 11px;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 9px;
  cursor: pointer;
  color: var(--text-2);
  font-size: 13.5px;
  transition: all 0.15s;
}
.nav-item .el-tag {
  margin-left: auto;
  transform: scale(0.9);
}
.nav-item.active {
  background: rgba(79, 124, 255, 0.13);
  color: var(--accent);
  font-weight: 700;
}
.nav-item.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.sidebar-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pipeline-mini {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
}
.pm-label {
  font-size: 11px;
  margin-bottom: 8px;
}
.pm-chain {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  color: var(--text-2);
  flex-wrap: wrap;
}
.pm-chain i {
  color: var(--accent);
  font-style: normal;
}
.main {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}
.topbar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--border);
  background: rgba(11, 14, 20, 0.8);
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(6px);
}
.crumb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.topbar-right {
  font-size: 12px;
}
</style>