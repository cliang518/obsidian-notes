<template>
  <section class="page">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">学习中心</p>
        <h2>学习引擎与经验沉淀</h2>
        <p class="lead">
          学习中心负责把告警历史、工单结果、拓扑快照、第三方平台同步结果和人工经验沉淀成可执行建议。
          当前策略是“先学习、后建议、再人工确认”，避免在现场网络复杂的情况下直接自动修改策略。
        </p>
      </div>
      <div class="hero-side">
        <div class="hero-badge">
          <span>学习模式</span>
          <strong>{{ strategyLabel(learning.strategy) }}</strong>
        </div>
        <div class="hero-metrics">
          <div>
            <label>学习源</label>
            <strong>{{ learning.data_sources?.length || 0 }}</strong>
          </div>
          <div>
            <label>输出项</label>
            <strong>{{ learning.planned_outputs?.length || 0 }}</strong>
          </div>
        </div>
      </div>
    </header>

    <section class="cards">
      <article class="card">
        <span>学习阶段</span>
        <strong>{{ stageLabel(learning.stage) }}</strong>
      </article>
      <article class="card">
        <span>学习源数量</span>
        <strong>{{ learning.data_sources?.length || 0 }}</strong>
      </article>
      <article class="card">
        <span>输出项数量</span>
        <strong>{{ learning.planned_outputs?.length || 0 }}</strong>
      </article>
      <article class="card">
        <span>模型类型</span>
        <strong>{{ llm.provider_types?.length || 0 }}</strong>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>学习原则</h3>
        <ul class="plain-list compact-list">
          <li v-for="(item, index) in learning.design_notes || []" :key="`ln-${index}`">
            {{ item }}
          </li>
        </ul>
      </article>

      <article class="panel accent-panel">
        <h3>模型层原则</h3>
        <ul class="plain-list compact-list">
          <li v-for="(item, index) in llm.design_notes || []" :key="`llm-${index}`">
            {{ item }}
          </li>
        </ul>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>学习数据源</h3>
        <div class="stack-list">
          <div v-for="item in learning.data_sources || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ item.value }}</span>
          </div>
        </div>
      </article>

      <article class="panel">
        <h3>输出结果</h3>
        <div class="stack-list">
          <div v-for="item in learning.planned_outputs || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ outputStatusLabel(item.status) }}</span>
          </div>
        </div>
      </article>
    </section>

    <section class="panel-grid">
      <article class="panel">
        <h3>大模型可承接场景</h3>
        <div class="stack-list">
          <div v-for="item in llm.planned_use_cases || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ item.mode }}</span>
          </div>
        </div>
      </article>

      <article class="panel">
        <h3>模型层可选类型</h3>
        <div class="stack-list">
          <div v-for="item in llm.provider_types || []" :key="item.name" class="stack-item">
            <strong>{{ item.name }}</strong>
            <span>{{ outputStatusLabel(item.status) }}</span>
          </div>
        </div>
      </article>
    </section>

    <article class="panel">
      <h3>建议落地路径</h3>
      <div class="roadmap-grid">
        <div class="roadmap-item">
          <strong>第一步</strong>
          <span>沉淀抖动设备、高发区域、重复异常和恢复节奏</span>
        </div>
        <div class="roadmap-item">
          <strong>第二步</strong>
          <span>结合工单闭环时长与人工备注，生成根因候选与处理建议</span>
        </div>
        <div class="roadmap-item">
          <strong>第三步</strong>
          <span>形成周报、月报、区域风险画像与疑难设备档案</span>
        </div>
        <div class="roadmap-item">
          <strong>第四步</strong>
          <span>在人工确认后再逐步启用阈值建议与策略优化</span>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { fetchLearningSummary, fetchLlmSummary } from "../api/client";

const learning = ref({});
const llm = ref({});

onMounted(async () => {
  try {
    learning.value = await fetchLearningSummary();
    llm.value = await fetchLlmSummary();
  } catch (error) {
    console.error(error);
  }
});

function stageLabel(value) {
  const mapping = {
    planned_foundation: "规划打底",
    testing: "联调测试",
    active: "正式运行",
  };
  return mapping[value] || value || "-";
}

function strategyLabel(value) {
  const mapping = {
    human_approved_learning: "人工确认式学习",
  };
  return mapping[value] || value || "-";
}

function outputStatusLabel(value) {
  const mapping = {
    planned: "计划中",
    running: "运行中",
    active: "已启用",
  };
  return mapping[value] || value || "-";
}
</script>

<style scoped>
.roadmap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.roadmap-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(232, 242, 255, 0.96));
  border: 1px solid rgba(63, 114, 175, 0.14);
}
</style>
