<template>
  <div class="stage-render">
    <!-- 1. 数据接入 -->
    <div v-if="stageKey === 'ingest' && data" class="ingest-wrap">
      <div v-for="(item, i) in data.items" :key="i" class="ingest-item">
        <el-icon class="ok"><CircleCheckFilled /></el-icon>
        <div class="ingest-body">
          <div class="ingest-name">{{ item.name }}</div>
          <div class="ingest-note">{{ item.note }}</div>
        </div>
      </div>
      <div v-if="data.meta" class="meta-tags">
        <el-tag v-for="(v, k) in data.meta" :key="k" effect="plain" size="small" class="meta-tag">
          {{ k }}：{{ v }}
        </el-tag>
      </div>
    </div>

    <!-- 2. 分析师研报 -->
    <div v-else-if="stageKey === 'analyst' && data" class="analyst-grid">
      <div v-for="a in data" :key="a.agent" class="panel analyst-card">
        <div class="analyst-head">
          <div class="analyst-icon"><el-icon><component :is="a.icon" /></el-icon></div>
          <div class="analyst-meta">
            <div class="analyst-name">{{ a.agent }}</div>
            <div class="analyst-group faint">{{ a.group }}</div>
          </div>
          <div v-if="a.rating != null" class="analyst-score">
            <span class="score-num">{{ a.rating }}</span>
            <span class="faint">分</span>
          </div>
          <el-tag v-else type="info" effect="plain" size="small">待接入 LLM</el-tag>
        </div>
        <ul class="analyst-lines">
          <li v-for="(line, i) in a.lines" :key="i">{{ line }}</li>
        </ul>
      </div>
    </div>

    <!-- 3. 多空辩论 -->
    <div v-else-if="stageKey === 'debate' && data" class="debate-wrap">
      <div v-for="r in data" :key="r.round" class="debate-round">
        <div class="debate-round-label faint">第 {{ r.round }} 轮</div>
        <div class="debate-msg bull">
          <div class="avatar bull">🐂</div>
          <div class="bubble">
            <div class="bubble-head"><b>多头研究员</b><span class="faint">{{ r.bull.title }}</span></div>
            <div class="bubble-body">{{ r.bull.content }}</div>
          </div>
        </div>
        <div class="debate-msg bear">
          <div class="bubble">
            <div class="bubble-head"><b>空头研究员</b><span class="faint">{{ r.bear.title }}</span></div>
            <div class="bubble-body">{{ r.bear.content }}</div>
          </div>
          <div class="avatar bear">🐻</div>
        </div>
      </div>
    </div>

    <!-- 4. 交易提案 -->
    <div v-else-if="stageKey === 'trader' && data" class="proposal-wrap">
      <div class="duel">
        <div class="duel-side bull-side">
          <div class="duel-score">{{ data.bullScore }}</div>
          <div class="muted">多头评分</div>
        </div>
        <div class="duel-bar">
          <div class="duel-fill bull" :style="{ width: data.bullScore + '%' }" />
        </div>
        <div class="duel-bar">
          <div class="duel-fill bear" :style="{ width: data.bearScore + '%' }" />
        </div>
        <div class="duel-side bear-side">
          <div class="duel-score">{{ data.bearScore }}</div>
          <div class="muted">空头评分</div>
        </div>
      </div>
      <div class="proposal-fields">
        <div class="pf-item">
          <span class="faint">操作方向</span>
          <b :class="data.directionType">{{ data.direction }}</b>
        </div>
        <div class="pf-item">
          <span class="faint">目标价</span>
          <b>{{ data.target }} 元</b>
        </div>
        <div class="pf-item">
          <span class="faint">止损价</span>
          <b>{{ data.stop }} 元</b>
        </div>
        <div class="pf-item">
          <span class="faint">建议仓位</span>
          <b>{{ data.position }}</b>
        </div>
        <div class="pf-item">
          <span class="faint">持有周期</span>
          <b>{{ data.horizon }}</b>
        </div>
      </div>
      <div class="proposal-rationale muted">{{ data.rationale }}</div>
    </div>

    <!-- 5. 风控评审 -->
    <div v-else-if="stageKey === 'risk' && data" class="risk-grid">
      <div v-for="r in data" :key="r.name" class="panel risk-card">
        <div class="risk-head">
          <div class="risk-name">
            <span class="risk-dot" :class="r.tone" />
            {{ r.name }}
          </div>
          <el-tag :type="r.tone === 'up' ? 'danger' : r.tone === 'warn' ? 'warning' : 'success'" effect="dark" size="small">
            {{ r.verdict }}
          </el-tag>
        </div>
        <div class="risk-score">
          <span class="score-num">{{ r.score }}</span>
          <span class="faint">/ 100</span>
        </div>
        <el-progress :percentage="+r.score" :stroke-width="5" :show-text="false"
          :color="r.tone === 'up' ? '#ef4444' : r.tone === 'warn' ? '#d4a72c' : '#22c55e'" />
        <div class="risk-comment muted">{{ r.comment }}</div>
        <div class="risk-limit faint">仓位上限：{{ r.limit }}</div>
      </div>
    </div>

    <!-- 6. PM 决策 -->
    <div v-else-if="stageKey === 'pm' && data" class="pm-wrap">
      <div class="pm-summary muted">{{ data.summary }}</div>
      <div class="pm-block">
        <div class="pm-block-title">决策依据</div>
        <ul>
          <li v-for="(r, i) in data.reasons" :key="i">{{ r }}</li>
        </ul>
      </div>
      <div class="pm-block">
        <div class="pm-block-title">风险提示</div>
        <ul class="risk-list">
          <li v-for="(r, i) in data.risks" :key="i">{{ r }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ stageKey: { type: String, required: true }, data: { type: Object, required: true } })
</script>

<style scoped>
.stage-render {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 数据接入 */
.ingest-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--panel-2);
}
.ingest-item .ok {
  color: var(--down);
  font-size: 16px;
  margin-top: 2px;
}
.ingest-name {
  font-weight: 600;
  margin-bottom: 2px;
}
.ingest-note {
  font-size: 13px;
  color: var(--text-2);
}
.meta-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 分析师 */
.analyst-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}
.analyst-card {
  padding: 14px;
}
.analyst-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.analyst-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: rgba(79, 124, 255, 0.12);
  font-size: 18px;
}
.analyst-name {
  font-weight: 700;
}
.analyst-group {
  font-size: 12px;
}
.analyst-score {
  margin-left: auto;
  text-align: right;
}
.score-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--accent);
}
.score-num {
  color: var(--accent);
}
.analyst-lines {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.8;
}

/* 辩论 */
.debate-round {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.debate-round-label {
  font-size: 12px;
  text-align: center;
  margin-bottom: 2px;
}
.debate-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.debate-msg.bull {
  justify-content: flex-start;
}
.debate-msg.bear {
  justify-content: flex-end;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 16px;
  flex-shrink: 0;
}
.avatar.bull {
  background: var(--up-bg);
  border: 1px solid rgba(239, 68, 68, 0.35);
}
.avatar.bear {
  background: var(--down-bg);
  border: 1px solid rgba(34, 197, 94, 0.35);
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--panel-2);
}
.debate-msg.bull .bubble {
  border-top-left-radius: 4px;
}
.debate-msg.bear .bubble {
  border-top-right-radius: 4px;
}
.bubble-head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  margin-bottom: 6px;
}
.bubble-body {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
}

/* 提案 */
.proposal-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.duel {
  display: flex;
  align-items: center;
  gap: 10px;
}
.duel-side {
  width: 70px;
  text-align: center;
}
.duel-score {
  font-size: 22px;
  font-weight: 800;
}
.bull-side .duel-score {
  color: var(--up);
}
.bear-side .duel-score {
  color: var(--down);
}
.duel-bar {
  flex: 1;
  height: 8px;
  background: var(--panel-2);
  border-radius: 4px;
  overflow: hidden;
}
.duel-bar:first-of-type {
  direction: rtl;
}
.duel-fill {
  height: 100%;
  border-radius: 4px;
}
.duel-fill.bull {
  background: linear-gradient(90deg, #ef4444, #f87171);
}
.duel-fill.bear {
  background: linear-gradient(90deg, #22c55e, #4ade80);
}
.proposal-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
.pf-item {
  background: var(--panel-2);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pf-item span {
  font-size: 12px;
}
.proposal-rationale {
  font-size: 13px;
  line-height: 1.7;
  padding: 10px 12px;
  border-left: 3px solid var(--accent);
  background: var(--panel-2);
  border-radius: 0 8px 8px 0;
}

/* 风控 */
.risk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.risk-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.risk-name {
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
}
.risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.risk-dot.up {
  background: var(--up);
}
.risk-dot.warn {
  background: var(--gold);
}
.risk-dot.down {
  background: var(--down);
}
.risk-score .score-num {
  color: var(--text);
}
.risk-comment {
  font-size: 13px;
  line-height: 1.7;
  flex: 1;
}
.risk-limit {
  font-size: 12px;
}

/* PM */
.pm-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.pm-summary {
  font-size: 13px;
  line-height: 1.8;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--panel-2);
}
.pm-block-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.pm-block ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
  color: var(--text-2);
  font-size: 13px;
}
.pm-block .risk-list {
  color: #f59e9e;
}
</style>
