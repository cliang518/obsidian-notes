<template>
  <main class="dashboard-view">
    <section class="metrics-grid">
      <article v-for="metric in coreMetrics" :key="metric.label" class="metric-card" :style="{ '--accent': metric.color }">
        <div class="metric-orb">{{ metric.icon }}</div>
        <div class="metric-copy">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}<small>{{ metric.unit }}</small></strong>
          <em :class="{ down: metric.trend < 0 }">
            {{ metric.trend > 0 ? "↑" : "↓" }} {{ Math.abs(metric.trend) }}% 较昨日
          </em>
        </div>
      </article>
    </section>

    <section class="chart-grid chart-grid-main">
      <article class="chart-card">
        <div class="chart-head">
          <div>
            <span>HEALTH MATRIX</span>
            <h3>全网健康度环形图</h3>
          </div>
          <b>在线 / 离线 / 故障</b>
        </div>
        <div ref="donutChartRef" class="chart-stage"></div>
      </article>

      <article class="chart-card span-wide">
        <div class="chart-head">
          <div>
            <span>ALERT TREND</span>
            <h3>7 日告警与处理趋势</h3>
          </div>
          <b>渐变面积追踪</b>
        </div>
        <div ref="lineChartRef" class="chart-stage"></div>
      </article>
    </section>

    <section class="chart-grid chart-grid-bottom">
      <article class="chart-card">
        <div class="chart-head">
          <div>
            <span>WORK ORDER FUNNEL</span>
            <h3>工单流转效率漏斗</h3>
          </div>
          <b>告警 → 落盘</b>
        </div>
        <div ref="funnelChartRef" class="chart-stage"></div>
      </article>

      <article class="chart-card">
        <div class="chart-head">
          <div>
            <span>AREA RADAR</span>
            <h3>区域异常频率雷达</h3>
          </div>
          <b>南北楼热点</b>
        </div>
        <div ref="radarChartRef" class="chart-stage"></div>
      </article>
    </section>
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import * as echarts from "echarts";

const donutChartRef = ref(null);
const lineChartRef = ref(null);
const funnelChartRef = ref(null);
const radarChartRef = ref(null);
const charts = [];

const coreMetrics = [
  { label: "全网设备", value: "1,284", unit: "台", icon: "⛓", color: "#38bdf8", trend: 2.4 },
  { label: "在线率", value: "98.5", unit: "%", icon: "⚡", color: "#10b981", trend: 0.8 },
  { label: "今日告警", value: "45", unit: "条", icon: "!", color: "#ef4444", trend: -12.5 },
  { label: "待办工单", value: "8", unit: "单", icon: "✓", color: "#f59e0b", trend: -5.0 },
];

function chartBase() {
  return {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1", fontFamily: "Bahnschrift, Microsoft YaHei, sans-serif" },
  };
}

function initDonutChart() {
  const chart = echarts.init(donutChartRef.value);
  chart.setOption({
    ...chartBase(),
    tooltip: { trigger: "item", backgroundColor: "rgba(15,23,42,.92)", borderColor: "rgba(56,189,248,.24)", textStyle: { color: "#f8fafc" } },
    legend: { bottom: 0, textStyle: { color: "#94a3b8" }, itemWidth: 10, itemHeight: 10 },
    series: [{
      name: "全网健康",
      type: "pie",
      radius: ["52%", "76%"],
      center: ["50%", "46%"],
      avoidLabelOverlap: true,
      label: { color: "#e2e8f0", formatter: "{b}\n{d}%" },
      labelLine: { lineStyle: { color: "rgba(148,163,184,.35)" } },
      itemStyle: { borderColor: "#05080f", borderWidth: 3, borderRadius: 10 },
      data: [
        { value: 1260, name: "在线", itemStyle: { color: "#10b981" } },
        { value: 15, name: "离线", itemStyle: { color: "#ef4444" } },
        { value: 9, name: "故障", itemStyle: { color: "#f59e0b" } },
      ],
    }],
  });
  charts.push(chart);
}

function initLineChart() {
  const chart = echarts.init(lineChartRef.value);
  chart.setOption({
    ...chartBase(),
    tooltip: { trigger: "axis", backgroundColor: "rgba(15,23,42,.92)", borderColor: "rgba(56,189,248,.24)", textStyle: { color: "#f8fafc" } },
    legend: { top: 4, right: 10, textStyle: { color: "#94a3b8" } },
    grid: { left: 36, right: 22, top: 54, bottom: 34 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: ["05-01", "05-02", "05-03", "05-04", "05-05", "05-06", "05-07"],
      axisLine: { lineStyle: { color: "rgba(148,163,184,.24)" } },
      axisTick: { show: false },
      axisLabel: { color: "#64748b" },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,.1)" } },
    },
    series: [
      {
        name: "新增告警",
        type: "line",
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 3, color: "#ef4444" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(239,68,68,.36)" },
            { offset: 1, color: "rgba(239,68,68,0)" },
          ]),
        },
        data: [120, 132, 101, 134, 90, 230, 45],
      },
      {
        name: "已处理",
        type: "line",
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 3, color: "#10b981" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(16,185,129,.34)" },
            { offset: 1, color: "rgba(16,185,129,0)" },
          ]),
        },
        data: [110, 125, 98, 130, 85, 210, 40],
      },
    ],
  });
  charts.push(chart);
}

function initFunnelChart() {
  const chart = echarts.init(funnelChartRef.value);
  chart.setOption({
    ...chartBase(),
    tooltip: { trigger: "item", backgroundColor: "rgba(15,23,42,.92)", borderColor: "rgba(56,189,248,.24)", textStyle: { color: "#f8fafc" } },
    series: [{
      name: "闭环转化",
      type: "funnel",
      left: "8%",
      top: 24,
      bottom: 18,
      width: "84%",
      minSize: "26%",
      maxSize: "92%",
      sort: "descending",
      gap: 3,
      label: { position: "inside", color: "#f8fafc", fontWeight: 800 },
      itemStyle: { borderColor: "#05080f", borderWidth: 2 },
      data: [
        { value: 100, name: "告警触发", itemStyle: { color: "#ef4444" } },
        { value: 82, name: "系统立单", itemStyle: { color: "#f59e0b" } },
        { value: 64, name: "现场核实", itemStyle: { color: "#38bdf8" } },
        { value: 46, name: "拓扑落盘", itemStyle: { color: "#10b981" } },
      ],
    }],
  });
  charts.push(chart);
}

function initRadarChart() {
  const chart = echarts.init(radarChartRef.value);
  chart.setOption({
    ...chartBase(),
    tooltip: { backgroundColor: "rgba(15,23,42,.92)", borderColor: "rgba(56,189,248,.24)", textStyle: { color: "#f8fafc" } },
    radar: {
      radius: "68%",
      center: ["50%", "52%"],
      splitNumber: 4,
      axisName: { color: "#cbd5e1", fontWeight: 700 },
      axisLine: { lineStyle: { color: "rgba(56,189,248,.18)" } },
      splitLine: { lineStyle: { color: "rgba(56,189,248,.16)" } },
      splitArea: { areaStyle: { color: ["rgba(14,165,233,.04)", "rgba(14,165,233,.11)"] } },
      indicator: [
        { name: "南楼", max: 100 },
        { name: "北楼", max: 100 },
        { name: "核心机房", max: 100 },
        { name: "链路热点", max: 100 },
        { name: "视频流", max: 100 },
      ],
    },
    series: [{
      name: "异常频率",
      type: "radar",
      data: [{
        value: [65, 48, 18, 72, 80],
        name: "热点",
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { width: 2, color: "#38bdf8" },
        itemStyle: { color: "#38bdf8" },
        areaStyle: { color: "rgba(14,165,233,.34)" },
      }],
    }],
  });
  charts.push(chart);
}

function initCharts() {
  initDonutChart();
  initLineChart();
  initFunnelChart();
  initRadarChart();
}

function handleResize() {
  charts.forEach((chart) => chart.resize());
}

onMounted(() => {
  window.setTimeout(() => {
    initCharts();
    window.addEventListener("resize", handleResize);
  }, 80);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  charts.forEach((chart) => chart.dispose());
  charts.length = 0;
});
</script>

<style scoped>
.dashboard-view {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background:
    radial-gradient(circle at 76% 6%, rgba(56, 189, 248, 0.16), transparent 30%),
    radial-gradient(circle at 8% 12%, rgba(245, 158, 11, 0.1), transparent 24%),
    linear-gradient(135deg, #05080f 0%, #07111f 52%, #081827 100%);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card,
.chart-card {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.14);
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.76), rgba(2, 6, 23, 0.58));
  backdrop-filter: blur(14px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
}

.metric-card::before,
.chart-card::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(115deg, rgba(255, 255, 255, 0.08), transparent 34%),
    linear-gradient(rgba(125, 211, 252, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(125, 211, 252, 0.035) 1px, transparent 1px);
  background-size: 100% 100%, 24px 24px, 24px 24px;
  opacity: 0.72;
}

.metric-card {
  min-height: 118px;
  border-radius: 18px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.metric-orb {
  position: relative;
  z-index: 1;
  width: 58px;
  height: 58px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  box-shadow: 0 0 24px color-mix(in srgb, var(--accent) 34%, transparent);
  font-size: 22px;
  font-weight: 900;
}

.metric-copy {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 4px;
}

.metric-copy span {
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
}

.metric-copy strong {
  color: #f8fafc;
  font-size: 30px;
  line-height: 1;
  font-family: Consolas, monospace;
}

.metric-copy small {
  margin-left: 4px;
  color: #64748b;
  font-size: 13px;
}

.metric-copy em {
  color: #f87171;
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
}

.metric-copy em.down {
  color: #34d399;
}

.chart-grid {
  display: grid;
  gap: 18px;
}

.chart-grid-main {
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.7fr);
}

.chart-grid-bottom {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.chart-card {
  min-height: 330px;
  border-radius: 22px;
  padding: 18px;
  display: flex;
  flex-direction: column;
}

.chart-head {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.chart-head span {
  color: #38bdf8;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.18em;
}

.chart-head h3 {
  margin: 4px 0 0;
  color: #f8fafc;
  font-size: 16px;
}

.chart-head b {
  padding: 3px 8px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  border-radius: 999px;
  color: #7dd3fc;
  background: rgba(14, 165, 233, 0.08);
  font-size: 11px;
}

.chart-stage {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 260px;
}

:global(body.graphics-low) .metric-card,
:global(body.graphics-low) .chart-card {
  backdrop-filter: none;
  background: #0b1120;
  box-shadow: none;
}

:global(body.graphics-medium) .metric-card,
:global(body.graphics-medium) .chart-card {
  backdrop-filter: blur(10px);
}

:global(body.graphics-ultra) .metric-card,
:global(body.graphics-ultra) .chart-card {
  backdrop-filter: blur(20px);
  box-shadow: 0 24px 74px rgba(14, 165, 233, 0.16), 0 18px 50px rgba(0, 0, 0, 0.34);
}

@media (max-width: 1280px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid-main,
  .chart-grid-bottom {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .dashboard-view {
    padding: 14px;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
