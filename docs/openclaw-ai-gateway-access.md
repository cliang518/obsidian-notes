# OpenClaw AI 网关接入

## 运行端口

AI 网关随 V2 后端运行，不单独占用端口。

- 后端端口: `8011`
- 统一入口: `http://192.168.119.149:8011/api/ai/gateway`
- 网关总览: `http://192.168.119.149:8011/api/ai/summary`
- 前端页面: `http://192.168.119.149:3011/ai-gateway`

## 服务密钥

OpenClaw 不使用管理员账号密码，使用专用服务密钥访问 AI 网关。

- Header 名称: `X-AI-Gateway-Key`
- Key 文件: `E:\cctv-maintenance\platform_v2\runtime\ai_gateway\openclaw.service-key.txt`
- 默认允许客户端: `192.168.119.15`, `192.168.119.149`, `127.0.0.1`, `::1`

运行时配置文件:

`E:\cctv-maintenance\platform_v2\runtime\ai_gateway\ai_gateway.yaml`

其中 `service_keys` 节点保存 OpenClaw 的服务密钥、允许来源和权限范围。

## OpenClaw 调用示例

PowerShell:

```powershell
$key = "把 openclaw.service-key.txt 里的 Value 填到这里"

$body = @{
  task = "查询 10.0.56.149 这台摄像头的信息"
  task_type = "device_query"
  payload = @{
    ip = "10.0.56.149"
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://192.168.119.149:8011/api/ai/gateway" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ "X-AI-Gateway-Key" = $key } `
  -Body $body
```

curl:

```bash
curl -X POST "http://192.168.119.149:8011/api/ai/gateway" \
  -H "Content-Type: application/json" \
  -H "X-AI-Gateway-Key: 替换为 openclaw.service-key.txt 里的 Value" \
  -d "{\"task\":\"查询 10.0.56.149 这台摄像头的信息\",\"task_type\":\"device_query\",\"payload\":{\"ip\":\"10.0.56.149\"}}"
```

## 安全边界

- OpenClaw 只通过 AI 网关读取和分析平台数据。
- 不把平台管理员账号密码交给 OpenClaw。
- 不允许 OpenClaw 直接修改 200、205、250 第三方平台。
- 不允许 OpenClaw 直接修改交换机、录像机、防火墙配置。
- 代码开发仍由用户在 Codex 中发起，Codex 执行。
