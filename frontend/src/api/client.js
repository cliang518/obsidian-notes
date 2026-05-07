import axios from "axios";
import { clearAuthSession, getAuthToken, setAuthSession } from "../state/auth";

export const api = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearAuthSession();
      const currentPath = window.location.pathname;
      if (currentPath !== "/login") {
        const redirect = encodeURIComponent(`${currentPath}${window.location.search || ""}`);
        window.location.replace(`/login?redirect=${redirect}`);
      }
    }
    return Promise.reject(error);
  },
);

export async function loginWithPassword(username, password) {
  const { data } = await api.post("/auth/login", { username, password });
  return data;
}

export async function registerWithPassword(payload) {
  const { data } = await api.post("/auth/register", payload);
  return data;
}

export async function fetchCurrentUser() {
  const { data } = await api.get("/auth/me");
  return data;
}

export async function logoutSession() {
  const { data } = await api.post("/auth/logout");
  clearAuthSession();
  return data;
}

export async function changePassword(currentPassword, newPassword) {
  const { data } = await api.post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return data;
}

export async function fetchRuntimeCounts() {
  const { data } = await api.get("/assets/runtime-counts");
  return data;
}

export async function fetchFloorPlanSummary() {
  const { data } = await api.get("/floor-plans/summary");
  return data;
}

export async function fetchFloorPlanDocuments() {
  const { data } = await api.get("/floor-plans/documents");
  return data;
}

export async function fetchFloorPlanDetail(documentId) {
  const { data } = await api.get(`/floor-plans/documents/${documentId}`);
  return data;
}

export async function reparseFloorPlan(documentId) {
  const { data } = await api.post(`/floor-plans/documents/${documentId}/reparse`);
  return data;
}

export async function uploadFloorPlan(payload) {
  const { data } = await api.post("/floor-plans/upload", payload, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return data;
}

export async function fetchSystemRuntime() {
  const { data } = await api.get("/system/runtime");
  return data;
}

export async function fetchSystemBackups(limit = 20) {
  const { data } = await api.get("/system/backups", {
    params: { limit },
  });
  return data;
}

export async function createSystemBackup() {
  const { data } = await api.post("/system/backup");
  return data;
}

export async function deleteSystemBackup(filename) {
  const { data } = await api.delete(`/system/backups/${encodeURIComponent(filename)}`);
  return data;
}

export async function pruneSystemBackups(payload = {}) {
  const keepLatest = Number(payload.keep_latest ?? payload.keepLatest ?? 20);
  const dryRun = payload.dry_run ?? payload.dryRun ?? true;
  const { data } = await api.post("/system/backups/prune", null, {
    params: {
      keep_latest: Number.isFinite(keepLatest) ? keepLatest : 20,
      dry_run: !!dryRun,
    },
  });
  return data;
}

export async function fetchLicenseStatus() {
  const { data } = await api.get("/license/status");
  return data;
}

export async function activateLicense(licenseData) {
  const { data } = await api.post("/license/activate", { license_data: licenseData });
  return data;
}

export async function fetchAgentGatewaySummary() {
  const { data } = await api.get("/agent-gateway/summary");
  return data;
}

export async function fetchAgentServices() {
  const { data } = await api.get("/agent-gateway/services");
  return data;
}

export async function createAgentService(payload) {
  const { data } = await api.post("/agent-gateway/services", payload);
  return data;
}

export async function updateAgentService(serviceId, payload) {
  const { data } = await api.put(`/agent-gateway/services/${serviceId}`, payload);
  return data;
}

export async function fetchAiGatewaySummary() {
  const { data } = await api.get("/ai/summary");
  return data;
}

export async function fetchAiGatewayConnection() {
  const { data } = await api.get("/ai/connection");
  return data;
}

export async function fetchAiGatewayLogs(limit = 120) {
  const { data } = await api.get("/ai/logs", {
    params: { limit },
  });
  return data;
}

export async function cleanupAiGatewayLogs(payload = {}) {
  const { data } = await api.post("/ai/logs/cleanup", payload);
  return data;
}

export async function runAiGatewayTask(payload) {
  const { data } = await api.post("/ai/gateway", payload);
  return data;
}

export async function registerAiAgent(payload) {
  const { data } = await api.post("/ai/agents/register", payload);
  return data;
}

export async function registerAiLlm(payload) {
  const { data } = await api.post("/ai/llm/register", payload);
  return data;
}

export async function fetchAiLlms() {
  const { data } = await api.get("/ai/llm/register");
  return data.items || [];
}

export async function deleteAiLlm(llmKey) {
  const { data } = await api.post(`/ai/llm/register/${encodeURIComponent(llmKey)}/delete`);
  return data;
}

export async function fetchAiSessions(limit = 50) {
  const { data } = await api.get("/ai/session", { params: { limit } });
  return data.items || [];
}

export async function fetchAiSession(sessionId) {
  const { data } = await api.get(`/ai/session/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function deleteAiSession(sessionId) {
  const { data } = await api.delete(`/ai/session/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function cleanupAiTestSessions(payload = {}) {
  const { data } = await api.post("/ai/session/cleanup-test", payload);
  return data;
}

export async function analyzeAlertsWithAi(payload = {}) {
  const { data } = await api.post("/ai/alerts/analyze", payload);
  return data;
}

export async function generateAiReport(payload = {}) {
  const { data } = await api.post("/ai/reports/generate", payload);
  return data;
}

export async function queryDeviceWithAi(payload = {}) {
  const { data } = await api.post("/ai/device/query", payload);
  return data;
}

export async function fetchMobileSummary() {
  const { data } = await api.get("/mobile/summary");
  return data;
}

export async function fetchMobileDispatchBoard() {
  const { data } = await api.get("/mobile/dispatch-board");
  return data;
}

export async function fetchMobileDispatchSummary() {
  const { data } = await api.get("/mobile/dispatch-summary");
  return data;
}

export async function fetchMobileDispatchItems() {
  const { data } = await api.get("/mobile/dispatch-items");
  return data;
}

export async function createMobileDispatchFromAlert(alertId, payload = {}) {
  const { data } = await api.post(`/mobile/dispatch-items/from-alert/${alertId}`, payload);
  return data;
}

export async function createMobileDispatchFromWorkOrder(workOrderId, payload = {}) {
  const { data } = await api.post(`/mobile/dispatch-items/from-work-order/${workOrderId}`, payload);
  return data;
}

export async function createMobileDispatchFromInspection(inspectionId, payload = {}) {
  const { data } = await api.post(`/mobile/dispatch-items/from-inspection/${inspectionId}`, payload);
  return data;
}

export async function updateMobileDispatchItem(dispatchId, payload) {
  const { data } = await api.put(`/mobile/dispatch-items/${dispatchId}`, payload);
  return data;
}

export async function fetchNotificationSummary() {
  const { data } = await api.get("/notifications/summary");
  return data;
}

export async function fetchAlertGuardSettings() {
  const { data } = await api.get("/alerts/guard-settings");
  return data;
}

export async function updateAlertGuardSettings(payload) {
  const { data } = await api.put("/alerts/guard-settings", payload);
  return data;
}

export async function fetchNotificationChannels() {
  const { data } = await api.get("/notifications/channels");
  return data;
}

export async function fetchNotificationDeliveries(limit = 50) {
  const { data } = await api.get("/notifications/deliveries", {
    params: { limit },
  });
  return data;
}

export async function createNotificationChannel(payload) {
  const { data } = await api.post("/notifications/channels", payload);
  return data;
}

export async function updateNotificationChannel(channelId, payload) {
  const { data } = await api.put(`/notifications/channels/${channelId}`, payload);
  return data;
}

export async function testNotificationChannel(channelId) {
  const { data } = await api.post(`/notifications/channels/${channelId}/test`);
  return data;
}

export async function dispatchAlertNotifications(payload = {}) {
  const { data } = await api.post("/notifications/dispatch-alerts", payload);
  return data;
}

export async function fetchMobileChannels() {
  const { data } = await api.get("/mobile/channels");
  return data;
}

export async function createMobileChannel(payload) {
  const { data } = await api.post("/mobile/channels", payload);
  return data;
}

export async function updateMobileChannel(channelId, payload) {
  const { data } = await api.put(`/mobile/channels/${channelId}`, payload);
  return data;
}

export async function fetchControlPlatformSummary() {
  const { data } = await api.get("/control-platform/summary");
  return data;
}

export async function fetchControlDomainSummary() {
  const { data } = await api.get("/control-domain/summary");
  return data;
}

export async function fetchControlDomainRegistrationSummary(registrationId) {
  const { data } = await api.get(`/control-domain/registrations/${registrationId}/summary`);
  return data;
}

export async function fetchControlDomainCompare(leftRegistrationId, rightRegistrationId) {
  const { data } = await api.get("/control-domain/compare", {
    params: {
      left_registration_id: leftRegistrationId,
      right_registration_id: rightRegistrationId,
    },
  });
  return data;
}

export async function fetchControlDomainDevices(params = {}) {
  const { data } = await api.get("/control-domain/devices", { params });
  return data;
}

export async function fetchControlDomainPoints(params = {}) {
  const { data } = await api.get("/control-domain/points", { params });
  return data;
}

export async function fetchControlDomainScenarios(params = {}) {
  const { data } = await api.get("/control-domain/scenarios", { params });
  return data;
}

export async function fetchControlDomainEvents(params = {}) {
  const { data } = await api.get("/control-domain/events", { params });
  return data;
}

export async function fetchControlDomainMenus(params = {}) {
  const { data } = await api.get("/control-domain/menus", { params });
  return data;
}

export async function fetchControlDomainMenuTree(registrationId) {
  const { data } = await api.get(`/control-domain/registrations/${registrationId}/menu-tree`);
  return data;
}

export async function fetchControlPlatformRegistrations() {
  const { data } = await api.get("/control-platform/registrations");
  return data;
}

export async function fetchControlPlatformInstances() {
  const { data } = await api.get("/control-platform/instances");
  return data;
}

export async function fetchControlPlatformRegistrationActivity(registrationId) {
  const { data } = await api.get(`/control-platform/registrations/${registrationId}/activity`);
  return data;
}

export async function exportControlPlatformRegistration(registrationId) {
  const { data } = await api.get(`/control-platform/registrations/${registrationId}/export`);
  return data;
}

export async function fetchControlPlatformAuditTemplate(trackKey = "new_control_platform") {
  const { data } = await api.get("/control-platform/audit-template", {
    params: { track_key: trackKey },
  });
  return data;
}

export async function inspectControlAuditBundle(bundleDir) {
  const { data } = await api.get("/control-platform/audit-inspect", {
    params: { bundle_dir: bundleDir },
  });
  return data;
}

export async function previewControlAuditBundle(bundleDir) {
  const { data } = await api.get("/control-platform/audit-preview", {
    params: { bundle_dir: bundleDir },
  });
  return data;
}

export async function compareControlAuditBundles(leftBundleDir, rightBundleDir) {
  const { data } = await api.get("/control-platform/audit-compare", {
    params: {
      left_bundle_dir: leftBundleDir,
      right_bundle_dir: rightBundleDir,
    },
  });
  return data;
}

export async function fetchControlPlatformImportPlan(registrationId, bundleDir, compareBundleDir) {
  const { data } = await api.get(`/control-platform/registrations/${registrationId}/import-plan`, {
    params: {
      bundle_dir: bundleDir,
      compare_bundle_dir: compareBundleDir,
    },
  });
  return data;
}

export async function importControlAuditBundle(registrationId, bundleDir) {
  const { data } = await api.post(`/control-platform/import-audit-bundle/${registrationId}`, null, {
    params: { bundle_dir: bundleDir },
  });
  return data;
}

export async function createControlPlatformRegistration(payload) {
  const { data } = await api.post("/control-platform/registrations", payload);
  return data;
}

export async function updateControlPlatformRegistration(registrationId, payload) {
  const { data } = await api.put(`/control-platform/registrations/${registrationId}`, payload);
  return data;
}

export async function clearControlPlatformAuditData(registrationId) {
  const { data } = await api.delete(`/control-platform/registrations/${registrationId}/audit-data`);
  return data;
}

export async function fetchStorageSummary() {
  const { data } = await api.get("/storage/summary");
  return data;
}

export async function fetchStorageProviders() {
  const { data } = await api.get("/storage/providers");
  return data;
}

export async function createStorageProvider(payload) {
  const { data } = await api.post("/storage/providers", payload);
  return data;
}

export async function updateStorageProvider(providerId, payload) {
  const { data } = await api.put(`/storage/providers/${providerId}`, payload);
  return data;
}

export async function fetchLlmSummary() {
  const { data } = await api.get("/llm/summary");
  return data;
}

export async function fetchLlmProviders() {
  const { data } = await api.get("/llm/providers");
  return data;
}

export async function createLlmProvider(payload) {
  const { data } = await api.post("/llm/providers", payload);
  return data;
}

export async function updateLlmProvider(providerId, payload) {
  const { data } = await api.put(`/llm/providers/${providerId}`, payload);
  return data;
}

export async function fetchLearningSummary() {
  const { data } = await api.get("/learning/summary");
  return data;
}

export async function fetchDocsCatalog() {
  const { data } = await api.get("/docs");
  return data;
}

export async function fetchUserSummary() {
  const { data } = await api.get("/users/summary");
  return data;
}

export async function fetchUserAccounts(params = {}) {
  const { data } = await api.get("/users/accounts", { params });
  return data;
}

export async function fetchUserRoleMatrix() {
  const { data } = await api.get("/users/role-matrix");
  return data;
}

export async function createUserAccount(payload) {
  const { data } = await api.post("/users/accounts", payload);
  return data;
}

export async function updateUserAccount(accountId, payload) {
  const { data } = await api.put(`/users/accounts/${accountId}`, payload);
  return data;
}

export async function approveUserAccount(accountId) {
  const { data } = await api.post(`/users/accounts/${accountId}/approve`);
  return data;
}

export async function disableUserAccount(accountId) {
  const { data } = await api.post(`/users/accounts/${accountId}/disable`);
  return data;
}

export async function resetUserPassword(accountId) {
  const { data } = await api.post(`/users/accounts/${accountId}/reset-password`);
  return data;
}

export async function fetchAssetSummary() {
  const { data } = await api.get("/assets/summary");
  return data;
}

export async function fetchIntegrationSources() {
  const { data } = await api.get("/integrations/sources");
  return data;
}

export async function fetchIntegrationSummary() {
  const { data } = await api.get("/integrations/summary");
  return data;
}

export async function fetchIntegrationSourceDetail(sourceId) {
  const { data } = await api.get(`/integrations/sources/${sourceId}`);
  return data;
}

export async function fetchFuchengAlignment() {
  try {
    const { data } = await api.get("/integrations/fucheng-alignment-v2");
    return data;
  } catch (error) {
    const { data } = await api.get("/integrations/fucheng-alignment");
    return data;
  }
}

export async function fetchFuchengDataQuality() {
  const { data } = await api.get("/integrations/fucheng-data-quality");
  return data;
}

export async function downloadFuchengDataQualityCsv() {
  const response = await api.get("/integrations/fucheng-data-quality-export.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function fetchFuchengAreaNormalizationPreview() {
  const { data } = await api.get("/integrations/fucheng-area-scope-normalization-preview");
  return data;
}

export async function applyFuchengAreaNormalization() {
  const { data } = await api.post("/integrations/fucheng-area-scope-normalization-apply");
  return data;
}

export async function fetchFuchengRepairPlan() {
  const { data } = await api.get("/integrations/fucheng-repair-plan");
  return data;
}

export async function downloadFuchengRepairPlanCsv() {
  const response = await api.get("/integrations/fucheng-repair-plan-export.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function downloadFuchengFieldValidationTemplateCsv() {
  const response = await api.get("/integrations/fucheng-field-validation-template.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function applyFuchengAreaSuggestions(payload = {}) {
  const { data } = await api.post("/integrations/fucheng-repair-plan/apply-area-suggestions", payload);
  return data;
}

export async function downloadFuchengAlignmentCsv() {
  const response = await api.get("/integrations/fucheng-alignment-export.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function fetchTgSwitchAuditCoverage() {
  const { data } = await api.get("/integrations/tg-switch-audit-coverage");
  return data;
}

export async function downloadTgSwitchAuditCoverageCsv() {
  const response = await api.get("/integrations/tg-switch-audit-coverage-export.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function fetchAlertSummary() {
  const { data } = await api.get("/alerts/summary");
  return data;
}

export async function fetchAlerts(params = {}) {
  const { data } = await api.get("/alerts", { params });
  return data;
}

export async function exportAlertsCsv(params = {}) {
  const response = await api.get("/alerts/export.csv", {
    params,
    responseType: "blob",
  });
  return response.data;
}

export async function bulkActionAlerts(action, ids) {
  const { data } = await api.post("/alerts/bulk-action", {
    action,
    ids,
  });
  return data;
}

export async function cleanupAlerts(payload = {}) {
  const { data } = await api.post("/alerts/cleanup", payload);
  return data;
}

export async function createWorkOrderFromAlert(alertId) {
  const { data } = await api.post(`/alerts/${alertId}/create-work-order`);
  return data;
}

export async function fetchDevices(params = {}) {
  const { data } = await api.get("/assets/devices", { params });
  return data;
}

export async function fetchDeviceDetail(deviceId) {
  const { data } = await api.get(`/assets/devices/${deviceId}`);
  return data;
}

export async function createDevice(payload) {
  const { data } = await api.post("/assets/devices", payload);
  return data;
}

export async function updateDevice(deviceId, payload) {
  const { data } = await api.put(`/assets/devices/${deviceId}`, payload);
  return data;
}

export async function archiveDevice(deviceId) {
  const { data } = await api.delete(`/assets/devices/${deviceId}`);
  return data;
}

export async function fetchDeviceTypes() {
  const { data } = await api.get("/assets/device-types");
  return data;
}

export async function fetchSourceTypes() {
  const { data } = await api.get("/assets/source-types");
  return data;
}

export async function fetchLinkEvidence() {
  const { data } = await api.get("/assets/link-evidence");
  return data;
}

export async function fetchAreas(params = {}) {
  const { data } = await api.get("/assets/areas", { params });
  return data;
}

export async function fetchAreaBreakdown() {
  const { data } = await api.get("/assets/area-breakdown");
  return data;
}

export async function fetchTopologySummary() {
  const { data } = await api.get("/topology/summary");
  return data;
}

export async function runTopologySwitchLiveProbe(payload = {}) {
  const { data } = await api.post("/topology/switch-live-probe/run", payload);
  return data;
}

export async function fetchTopologySwitchLiveProbes(limit = 80) {
  const { data } = await api.get("/topology/switch-live-probe", {
    params: { limit },
  });
  return data;
}

export async function fetchTopologyGraph() {
  const { data } = await api.get("/topology/graph");
  return data;
}

export async function fetchTopologySwitchFocusOptions(params = {}) {
  const { data } = await api.get("/topology/switch-focus-options", { params });
  return data;
}

export async function fetchTopologySwitchFocus(switchId, limit = 80) {
  const { data } = await api.get(`/topology/switch-focus/${switchId}`, {
    params: { limit },
  });
  return data;
}

export async function fetchTopologySkeleton() {
  const { data } = await api.get("/topology/skeleton");
  return data;
}

export async function fetchCentralAvenueArchitecture() {
  const { data } = await api.get("/topology/architecture/central-avenue");
  return data;
}

export async function rebuildCentralAvenueArchitecture() {
  const { data } = await api.post("/topology/architecture/central-avenue/rebuild");
  return data;
}

export async function updateArchitectureNode(nodeId, payload) {
  const { data } = await api.put(`/topology/architecture/nodes/${nodeId}`, payload);
  return data;
}

export async function createArchitectureNode(payload) {
  const { data } = await api.post("/topology/architecture/nodes", payload);
  return data;
}

export async function createArchitectureEdge(payload) {
  const { data } = await api.post("/topology/architecture/edges", payload);
  return data;
}

export async function deleteArchitectureNode(nodeId) {
  const { data } = await api.delete(`/topology/architecture/nodes/${nodeId}`);
  return data;
}

export async function deleteArchitectureEdge(edgeId) {
  const { data } = await api.delete(`/topology/architecture/edges/${edgeId}`);
  return data;
}

export async function applyTopologyManualUplinks(payload) {
  const { data } = await api.post("/topology/skeleton/manual-uplinks", payload);
  return data;
}

export async function fetchTopologyAreaDetail(areaId) {
  const { data } = await api.get(`/topology/areas/${areaId}`);
  return data;
}

export async function fetchTopologyVlanAttribution() {
  const { data } = await api.get("/topology/vlan-attribution");
  return data;
}

export async function fetchTopologyUnattributedLinks(limit = 300) {
  const { data } = await api.get("/topology/vlan-attribution/unattributed", {
    params: { limit },
  });
  return data;
}

export async function downloadTopologyUnattributedCsv() {
  const response = await api.get("/topology/vlan-attribution/unattributed.csv", {
    responseType: "blob",
  });
  return response.data;
}

export async function applyTopologyManualVlan(payload) {
  const { data } = await api.post("/topology/vlan-attribution/manual-apply", payload);
  return data;
}

export async function fetchChannels(params = {}) {
  const { data } = await api.get("/assets/channels", { params });
  return data;
}

export async function updateChannelTopologyBinding(channelId, payload) {
  const { data } = await api.put(`/assets/channels/${channelId}/topology-binding`, payload);
  return data;
}

export async function updateAssetPosition(payload) {
  const { data } = await api.post("/assets/update_pos", payload);
  return data;
}

export async function clearAssetTopologyBinding(payload) {
  const { data } = await api.post("/assets/clear_pos", payload);
  return data;
}

export async function importLatestStreamDiagnostics() {
  const { data } = await api.post("/assets/stream-diagnostics/import-latest-report");
  return data;
}

export async function fetchLatestStreamDiagnosticReportStatus() {
  const { data } = await api.get("/assets/stream-diagnostics/latest-report-status");
  return data;
}

export async function importFieldValidationCameraSheet(file) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/assets/field-validation/import-camera-sheet", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return data;
}

export async function fetchFieldValidationProgressSummary() {
  const { data } = await api.get("/assets/field-validation/progress-summary");
  return data;
}

export async function importFieldValidationSwitchGapSheet(file) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/assets/field-validation/import-switch-gap-sheet", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return data;
}

export async function fetchStreamDiagnosticSummary() {
  const { data } = await api.get("/assets/stream-diagnostics/summary");
  return data;
}

export function buildChannelSnapshotUrl(channelId, options = {}) {
  const id = Number(channelId || 0);
  if (!id) {
    return "";
  }
  const params = new URLSearchParams();
  const token = getAuthToken();
  if (token) {
    params.set("access_token", token);
  }
  if (options.refresh) {
    params.set("refresh", "true");
  }
  if (options.cacheBust ?? true) {
    params.set("_", String(Date.now()));
  }
  const query = params.toString();
  return `/api/assets/channels/${id}/snapshot.jpg${query ? `?${query}` : ""}`;
}

export function buildChannelMjpegUrl(channelId, options = {}) {
  const id = Number(channelId || 0);
  if (!id) {
    return "";
  }
  const params = new URLSearchParams();
  const token = getAuthToken();
  if (token) {
    params.set("access_token", token);
  }
  if (options.cacheBust ?? true) {
    params.set("_", String(Date.now()));
  }
  const query = params.toString();
  return `/api/assets/channels/${id}/mjpeg${query ? `?${query}` : ""}`;
}

export function buildChannelFlvUrl(channelId, options = {}) {
  const id = Number(channelId || 0);
  if (!id) {
    return "";
  }
  const params = new URLSearchParams();
  const token = getAuthToken();
  if (token) {
    params.set("access_token", token);
  }
  if (options.cacheBust ?? true) {
    params.set("_", String(Date.now()));
  }
  const query = params.toString();
  return `/api/assets/channels/${id}/flv${query ? `?${query}` : ""}`;
}

export async function fetchLinks() {
  const { data } = await api.get("/assets/links");
  return data;
}

export async function importKnownAudits() {
  const { data } = await api.post("/setup/import-known-audits");
  return data;
}

export async function importSingleSource(sourceKey) {
  const { data } = await api.post(`/setup/import-source/${sourceKey}`);
  return data;
}

export async function fetchWorkOrderSummary() {
  const { data } = await api.get("/work-orders/summary");
  return data;
}

export async function fetchWorkOrderItems(params = {}) {
  const { data } = await api.get("/work-orders/items", { params });
  return data;
}

export async function createWorkOrder(payload) {
  const { data } = await api.post("/work-orders/items", payload);
  return data;
}

export async function updateWorkOrder(itemId, payload) {
  const { data } = await api.put(`/work-orders/items/${itemId}`, payload);
  return data;
}

export async function createInspectionFromWorkOrder(itemId) {
  const { data } = await api.post(`/work-orders/${itemId}/create-inspection`);
  return data;
}

export async function fetchInspectionSummary() {
  const { data } = await api.get("/inspection/summary");
  return data;
}

export async function fetchInspectionTasks(params = {}) {
  const { data } = await api.get("/inspection/items", { params });
  return data;
}

export async function createInspectionTask(payload) {
  const { data } = await api.post("/inspection/items", payload);
  return data;
}

export async function updateInspectionTask(itemId, payload) {
  const { data } = await api.put(`/inspection/items/${itemId}`, payload);
  return data;
}

// --- V2.0 现场维修闭环垂直切片新增接口 ---

/**
 * 拓扑核实后一键结单 (大事务 Saga)
 */
export async function resolveWorkOrderFromTopology(workOrderId, payload) {
  const { data } = await api.post(`/work-orders/${workOrderId}/resolve-from-topology`, payload);
  return data;
}

/**
 * 更新工单状态 (支持拖拽看板)
 */
export async function updateWorkOrderStatus(workOrderId, status) {
  const { data } = await api.patch(`/work-orders/items/${workOrderId}/status`, { status });
  return data;
}