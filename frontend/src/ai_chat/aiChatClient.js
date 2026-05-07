const SAME_ORIGIN_GATEWAY_URL = "/api/ai/gateway";
const OPENCLAW_GATEWAY_URL = "http://192.168.119.149:8011/api/ai/gateway";
const AI_GATEWAY_KEY = "yj-ai-yHd_0q5HrVBjWHWIOjx4KT3ZspBQQAah7Y22BZQnwgw";

function currentHostGatewayUrl() {
  if (typeof window === "undefined" || !window.location?.hostname) {
    return "";
  }
  return `${window.location.protocol}//${window.location.hostname}:8011/api/ai/gateway`;
}

function gatewayCandidates() {
  const candidates = [SAME_ORIGIN_GATEWAY_URL, currentHostGatewayUrl(), OPENCLAW_GATEWAY_URL].filter(Boolean);
  return [...new Set(candidates)];
}

async function postGateway(url, payload, signal) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-AI-Gateway-Key": AI_GATEWAY_KEY,
    },
    body: JSON.stringify(payload),
    signal,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof data === "string" ? data : data?.detail?.message || data?.detail || response.statusText;
    throw new Error(`AI 网关请求失败：${message}`);
  }
  return data;
}

export async function sendAiChatTask({ task, taskType = "general", payload = {}, llmKey = "", sessionId = "", signal = null }) {
  const body = {
    task: String(task || "").trim(),
    task_type: taskType,
    payload,
    llm_key: String(llmKey || "").trim(),
    session_id: sessionId || null,
  };

  if (!body.task) {
    throw new Error("请输入要发送给 AI 网关的内容。");
  }

  let firstError = null;
  for (const [index, endpoint] of gatewayCandidates().entries()) {
    try {
      const data = await postGateway(endpoint, body, signal);
      return {
        data,
        endpoint,
        fallback: index > 0,
        primary_error: firstError?.message || "",
      };
    } catch (error) {
      if (error?.name === "AbortError") {
        throw error;
      }
      if (!firstError) {
        firstError = error;
      }
    }
  }

  if (firstError) {
    throw firstError;
  }
  throw new Error("AI 网关请求失败：没有可用的网关地址。");
}

export function inferTaskType(text) {
  const value = String(text || "");
  if (/(多少|几个|几台|数量|总数|一共|总共|count|how many|total|分布|类型|构成|占比|分类|统计|明细|breakdown|distribution)/i.test(value) && /(设备|摄像头|交换机|录像机|解码器|通道|device|camera|switch|nvr|decoder|channel)/i.test(value)) {
    return "ops_summary";
  }
  if (/(告警|报警|alert|alarm)/i.test(value) && /(处置|闭环|跟进|响应|派单|派工|工单|巡检|复核|review|inspection|workflow|follow up|response|dispatch)/i.test(value)) {
    return "ops_summary";
  }
  if (/快照|截图|抓图|抓拍|取图|snapshot|capture/i.test(value)) {
    return "snapshot_capture";
  }
  if (/告警|报警|异常|离线|抖动|恢复|alert|alarm|offline|flap|recover/i.test(value)) {
    return "alert_analyze";
  }
  if (/报告|日报|周报|月报|总结|生成/.test(value)) {
    return "report_generate";
  }
  if (/拓扑|链路|归属|端口|vlan|交换机.*摄像头|摄像头.*交换机/i.test(value)) {
    return "topology_query";
  }
  if (/系统状态|平台状态|服务状态|健康|网关状态/i.test(value)) {
    return "system_status";
  }
  if (/用户|账号|权限|审批|通知|飞书|微信|工单|派工|移动端|手机端|备份|user|account|permission|approval|notification|notify|message|wechat|feishu|wecom|work order|ticket|dispatch|mobile|phone|app|backup|restore/i.test(value)) {
    return "ops_summary";
  }
  if (/\b\d{1,3}(?:\.\d{1,3}){3}\b/.test(value) || /设备|摄像头|交换机|通道|rtsp/i.test(value)) {
    return "device_query";
  }
  return "general";
}

export function extractPayload(text, taskType) {
  const value = String(text || "");
  const ip = value.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/)?.[0] || "";
  if (taskType === "device_query") {
    return {
      ip,
      query: ip || value,
    };
  }
  if (taskType === "snapshot_capture") {
    return {
      ip,
      query: ip || value,
      refresh: true,
    };
  }
  if (taskType === "topology_query") {
    return {
      ip,
      query: ip || value,
    };
  }
  if (taskType === "ops_summary") {
    return {
      query: value,
    };
  }
  if (taskType === "report_generate") {
    return {
      report_type: /月报/.test(value) ? "monthly" : /周报/.test(value) ? "weekly" : "daily",
      sections: ["运行概况", "告警处置", "设备状态", "下一步建议"],
    };
  }
  return {};
}
