function normalizeCell(value) {
  return String(value ?? "").replace(/"/g, '""');
}

function toCsv(rows) {
  return rows.map((row) => row.map((cell) => `"${normalizeCell(cell)}"`).join(",")).join("\r\n");
}

export function downloadFieldValidationTemplate({ filename, switchLabel, switchIp, rows }) {
  const header = [
    "camera_ip",
    "camera_label",
    "current_area",
    "current_switch_ip",
    "current_port",
    "current_vlan",
    "current_zone",
    "collected_area",
    "collected_switch_ip",
    "collected_port",
    "collected_vlan",
    "collected_mac",
    "collector",
    "verified_at",
    "field_note",
  ];
  const body = (rows || []).map((item) => [
    item.camera_ip || "",
    item.camera_label || "",
    item.current_area || item.zone || "",
    item.current_switch_ip || switchIp || "",
    item.current_port || item.port_name || "",
    item.current_vlan || item.vlan_id || "",
    item.current_zone || item.zone || "",
    "",
    switchIp || "",
    "",
    "",
    "",
    "",
    "",
    switchLabel ? `来自 ${switchLabel} 专属核实单` : "",
  ]);
  const csv = `\ufeff${toCsv([header, ...body])}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const href = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(href);
}
