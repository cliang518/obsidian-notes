<template>
  <div class="work-order-center-wrapper">
    <section class="workorder-slim-toolbar">
      <div class="workorder-slim-stats">
        <span>待派发 <strong class="text-amber">{{ stats.open }}</strong></span>
        <span>处理中 <strong class="text-blue">{{ stats.in_progress }}</strong></span>
        <span>待拓扑核实 <strong class="text-purple">{{ stats.field_verified }}</strong></span>
        <span>今日已闭环 <strong class="text-emerald">{{ stats.closed }}</strong></span>
      </div>
      <button class="action-btn create-btn" @click="createMockOrder">＋ 模拟新建</button>
    </section>

    <!-- 沉浸式看板主体 -->
    <main class="kanban-board">
      <div 
        v-for="column in columns" 
        :key="column.status"
        class="kanban-column"
        :class="`column-${column.status}`"
        @dragover.prevent="handleDragOver($event, column.status)"
        @drop.prevent="handleDrop($event, column.status)"
      >
        <div class="column-header">
          <span class="column-dot"></span>
          <h3>{{ column.title }}</h3>
          <span class="column-count">{{ getOrdersByStatus(column.status).length }}</span>
        </div>
        
        <div class="kanban-cards">
          <transition-group name="card-list" tag="div" class="cards-transition-wrapper">
            <div 
              v-for="order in getOrdersByStatus(column.status)" 
              :key="order.id"
              class="wo-card"
              :class="`priority-${order.priority}`"
              draggable="true"
              @dragstart="handleDragStart($event, order)"
              @click="openDetail(order)"
            >
              <div class="card-header">
                <span class="wo-id">WO-{{ 1000 + order.id }}</span>
                <span class="wo-priority">{{ priorityLabel(order.priority) }}</span>
              </div>
              
              <div class="card-body">
                <h4 class="wo-title">{{ order.title }}</h4>
                <div class="wo-meta">
                  <span v-if="order.asset_ip" class="meta-tag">
                    <i class="meta-icon">💻</i> {{ order.asset_ip }}
                  </span>
                  <span v-if="order.area" class="meta-tag">
                    <i class="meta-icon">📍</i> {{ order.area }}
                  </span>
                </div>
              </div>

              <div class="card-footer" v-if="order.topology_node_key">
                <!-- 核心黑科技：跃迁大盘核实按钮 -->
                <button 
                  v-if="column.status === 'field_verified'" 
                  class="jump-topology-btn pulse"
                  @click.stop="jumpToTopology(order)"
                >
                  <span class="btn-icon">🎯</span> 前往大盘一键核实
                </button>
                <div v-else class="topology-hint">
                  关联拓扑: {{ order.topology_node_key.split(':').pop() }}
                </div>
              </div>
            </div>
          </transition-group>
        </div>
      </div>
    </main>

    <!-- 右侧情报抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="`工单详情 / WO-${1000 + (selectedOrder?.id || 0)}`"
      size="400px"
      custom-class="cyber-drawer"
      destroy-on-close
    >
      <div v-if="selectedOrder" class="drawer-content">
        <div class="info-group">
          <label>故障描述</label>
          <p>{{ selectedOrder.title }}</p>
        </div>
        <div class="info-group">
          <label>关联告警源</label>
          <div class="alert-box">
            <span class="alert-id">ALT-0{{ selectedOrder.source_alert_id }}</span>
            <span class="alert-time">2026-05-06 09:12:00</span>
          </div>
        </div>
        <div class="info-group">
          <label>维修反馈</label>
          <textarea 
            class="cyber-textarea" 
            v-model="selectedOrder.resolution_note" 
            placeholder="请输入现场排查结果..."
            rows="4"
          ></textarea>
        </div>
      </div>
      <template #footer>
        <div class="drawer-actions">
          <button class="action-btn cancel" @click="drawerVisible = false">关闭</button>
          <button class="action-btn save" @click="saveDetail">保存更新</button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { fetchWorkOrderItems, updateWorkOrder } from '../api/client'; // 引入真接口

const router = useRouter();

// 看板列定义
const columns = ref([
  { status: 'open', title: '🔴 待派发' },
  { status: 'in_progress', title: '🟠 处理中' },
  { status: 'field_verified', title: '🟣 待拓扑核实' },
  { status: 'closed', title: '🟢 已闭环' }
]);

// 真实工单数据容器
const workOrders = ref([]);
const loading = ref(true);

// 页面加载时自动去后台拉取真实数据！
onMounted(async () => {
  await loadWorkOrders();
});

const loadWorkOrders = async () => {
  loading.value = true;
  try {
    const res = await fetchWorkOrderItems({ limit: 100 });
    // 如果后台返回的是 { items: [...] } 格式则取 items，否则直接取数组
    workOrders.value = Array.isArray(res) ? res : (res?.items || []);
  } catch (error) {
    console.error(error);
    ElMessage.error('无法连接指挥中心，拉取工单失败！');
  } finally {
    loading.value = false;
  }
};

// 拖拽状态
const draggedOrder = ref(null);
const drawerVisible = ref(false);
const selectedOrder = ref(null);

// 统计数据
const stats = computed(() => {
  const s = { open: 0, in_progress: 0, field_verified: 0, closed: 0 };
  workOrders.value.forEach(wo => {
    if (s[wo.status] !== undefined) s[wo.status]++;
  });
  return s;
});

// 获取对应列的工单
const getOrdersByStatus = (status) => {
  return workOrders.value.filter(wo => wo.status === status).sort((a, b) => b.id - a.id);
};

// 优先级映射
const priorityLabel = (p) => {
  const map = { critical: '致命', high: '高', medium: '中', low: '低' };
  return map[p] || '普通';
};

// --- HTML5 原生拖拽逻辑 (对接真接口) ---
const handleDragStart = (e, order) => {
  draggedOrder.value = order;
  e.dataTransfer.effectAllowed = 'move';
  setTimeout(() => { e.target.style.opacity = '0.5'; }, 0);
};

const handleDragOver = (e, targetStatus) => {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
};

const handleDrop = async (e, targetStatus) => {
  e.preventDefault();
  const order = draggedOrder.value;
  
  if (order && order.status !== targetStatus) {
    const oldStatus = order.status;
    order.status = targetStatus; // 前端先变色，保证手感丝滑

    try {
      // 使用现成的万能接口，将完整的工单数据（包含标题等必填项）传回给后端！
      await updateWorkOrder(order.id, order);
      ElMessage.success(`WO-${1000 + order.id} 状态已更新为: ${columns.value.find(c=>c.status===targetStatus).title}`);
    } catch (error) {
      // 如果后台拒绝或报错，立刻把卡片弹回原来的列
      order.status = oldStatus;
      console.error(error);
      ElMessage.error('状态更新失败，已被中央服务器拦截！');
    }
  }
  
  document.querySelectorAll('.wo-card').forEach(el => el.style.opacity = '1');
  draggedOrder.value = null;
};

// --- 详情抽屉 ---
const openDetail = (order) => {
  selectedOrder.value = { ...order }; // Clone
  drawerVisible.value = true;
};

const saveDetail = () => {
  const index = workOrders.value.findIndex(wo => wo.id === selectedOrder.value.id);
  if (index !== -1) {
    workOrders.value[index] = { ...selectedOrder.value };
    ElMessage.success('工单情报已更新保存');
  }
  drawerVisible.value = false;
};

const createMockOrder = () => {
  workOrders.value.push({
    id: Math.floor(Math.random() * 1000) + 10,
    title: '探针发现未知 MAC 接入，需现场确认设备身份',
    status: 'open',
    priority: 'medium',
    source_alert_id: 120,
    asset_ip: '10.0.56.148',
    area: '2F南楼',
    topology_node_key: '10.0.56.148' 
  });
  ElMessage.success('已伪造高级权限凭证，直接注入待核实工单！');
};

// --- 核心联动：跃迁拓扑大盘 ---
const jumpToTopology = (order) => {
  if (!order.topology_node_key) {
    ElMessage.warning('中央处理器提示：该工单暂无拓扑坐标锚点！');
    return;
  }
  
  ElMessage.success(`🚀 跃迁引擎启动！已锁定目标设备：${order.topology_node_key.split(':').pop()}`);
  
  // 核心魔法：调用 Vue Router，带着设备坐标，直接杀向拓扑大盘！
  setTimeout(() => {
    router.push({
      path: '/topology',
      query: { focusNode: order.topology_node_key } // 把坐标传给拓扑图
    });
  }, 600);
};
</script>

<style scoped>
/* 深空蓝暗黑工业风底色 */
.work-order-center-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  min-height: 600px;
  background-color: #080b12;
  background-image: radial-gradient(circle at top right, rgba(14, 165, 233, 0.05), transparent 40%),
                    radial-gradient(circle at bottom left, rgba(245, 158, 11, 0.05), transparent 40%);
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  overflow: hidden;
}

.workorder-slim-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 24px 8px;
}

.workorder-slim-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.workorder-slim-stats span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 999px;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.5);
  font-size: 12px;
  font-weight: 700;
}

.workorder-slim-stats strong {
  font-family: Consolas, monospace;
  text-shadow: 0 0 10px currentColor;
}

.text-amber { color: #fbbf24; }
.text-blue { color: #38bdf8; }
.text-purple { color: #c084fc; }
.text-emerald { color: #34d399; }

.action-btn {
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid #0ea5e9;
  color: #38bdf8;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}
.action-btn:hover { background: rgba(14, 165, 233, 0.25); box-shadow: 0 0 12px rgba(14, 165, 233, 0.4); }

/* 看板核心区 */
.kanban-board {
  display: flex;
  gap: 16px;
  padding: 0 24px 24px 24px;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
}

.kanban-column {
  flex: 1;
  min-width: 320px;
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  transition: background 0.3s;
}

.column-open .column-header { border-bottom-color: rgba(239, 68, 68, 0.3); }
.column-in_progress .column-header { border-bottom-color: rgba(245, 158, 11, 0.3); }
.column-field_verified .column-header { border-bottom-color: rgba(168, 85, 247, 0.3); }
.column-closed .column-header { border-bottom-color: rgba(16, 185, 129, 0.3); }

.column-header {
  padding: 16px;
  border-bottom: 2px solid;
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(30, 41, 59, 0.3);
  border-radius: 12px 12px 0 0;
}
.column-header h3 { margin: 0; font-size: 15px; color: #f1f5f9; flex: 1; }
.column-count { background: #334155; color: #94a3b8; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }

.kanban-cards {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
}

.cards-transition-wrapper {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 卡片样式 */
.wo-card {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(100, 116, 139, 0.2);
  border-radius: 10px;
  padding: 14px;
  cursor: grab;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  position: relative;
  overflow: hidden;
}
.wo-card:active { cursor: grabbing; }
.wo-card:hover { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2); border-color: rgba(148, 163, 184, 0.5); }

/* 左侧优先级色条 */
.wo-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
}
.priority-critical::before { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
.priority-high::before { background: #f97316; }
.priority-medium::before { background: #3b82f6; }
.priority-low::before { background: #94a3b8; }

.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.wo-id { color: #94a3b8; font-size: 12px; font-weight: bold; font-family: 'Consolas', monospace; }
.wo-priority { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1); }
.priority-critical .wo-priority { color: #fca5a5; background: rgba(239, 68, 68, 0.2); }

.wo-title { margin: 0 0 12px 0; font-size: 14px; color: #e2e8f0; line-height: 1.4; }

.wo-meta { display: flex; gap: 8px; flex-wrap: wrap; }
.meta-tag { font-size: 11px; background: rgba(15, 23, 42, 0.6); padding: 4px 8px; border-radius: 6px; color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.1); }
.meta-icon { font-style: normal; margin-right: 4px; opacity: 0.8; }

.card-footer { margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(148, 163, 184, 0.2); }
.topology-hint { font-size: 11px; color: #64748b; font-family: monospace; }

/* 跃迁按钮特效 */
.jump-topology-btn {
  width: 100%;
  background: linear-gradient(90deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.2));
  border: 1px solid #a855f7;
  color: #d8b4fe;
  padding: 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.jump-topology-btn:hover {
  background: linear-gradient(90deg, rgba(168, 85, 247, 0.4), rgba(139, 92, 246, 0.4));
  box-shadow: 0 0 12px rgba(168, 85, 247, 0.5);
  transform: scale(1.02);
}
.jump-topology-btn.pulse { animation: btn-pulse 2s infinite; }
@keyframes btn-pulse {
  0% { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0.4); }
  70% { box-shadow: 0 0 0 6px rgba(168, 85, 247, 0); }
  100% { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0); }
}

/* 动画过渡 */
.card-list-enter-active, .card-list-leave-active { transition: all 0.3s ease; }
.card-list-enter-from { opacity: 0; transform: translateY(-20px); }
.card-list-leave-to { opacity: 0; transform: scale(0.9); }

/* 抽屉内样式 */
:deep(.cyber-drawer) {
  background: rgba(15, 23, 42, 0.95) !important;
  border-left: 1px solid rgba(14, 165, 233, 0.3);
  backdrop-filter: blur(20px);
}
:deep(.el-drawer__header) {
  color: #38bdf8 !important; border-bottom: 1px solid rgba(148, 163, 184, 0.2); margin-bottom: 0; padding-bottom: 16px; font-weight: bold;
}
.drawer-content { padding: 24px 0; display: flex; flex-direction: column; gap: 20px; }
.info-group label { display: block; font-size: 12px; color: #94a3b8; margin-bottom: 8px; font-weight: bold; }
.info-group p { margin: 0; color: #e2e8f0; font-size: 14px; line-height: 1.5; }
.alert-box { display: inline-flex; flex-direction: column; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); padding: 8px 12px; border-radius: 6px; }
.alert-id { color: #fca5a5; font-weight: bold; font-size: 14px; }
.alert-time { color: #94a3b8; font-size: 11px; margin-top: 4px; }
.cyber-textarea { width: 100%; box-sizing: border-box; background: rgba(0,0,0,0.3); border: 1px solid rgba(148, 163, 184, 0.3); color: #f8fafc; padding: 12px; border-radius: 8px; resize: vertical; font-family: inherit; }
.cyber-textarea:focus { outline: none; border-color: #38bdf8; box-shadow: 0 0 8px rgba(14, 165, 233, 0.3); }
.drawer-actions { display: flex; justify-content: flex-end; gap: 12px; }
.action-btn.cancel { background: transparent; border-color: rgba(148, 163, 184, 0.4); color: #cbd5e1; }
.action-btn.save { background: rgba(16, 185, 129, 0.2); border-color: #10b981; color: #34d399; }
</style>
