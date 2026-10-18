param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$Token,
  [Parameter(Mandatory=$true)][string]$WorkflowId,
  [string]$PrometheusUrl = "http://localhost:19090",
  [double]$MaxErrorRate = 0.10,
  [int]$WindowMinutes = 5,
  [string]$Environment = "production"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$headers = @{ Authorization = "Bearer $Token" }
$query = 'sum(rate(ai_platform_workflow_runs_total{status="failed"}[' + $WindowMinutes + 'm])) / clamp_min(sum(rate(ai_platform_workflow_runs_total[' + $WindowMinutes + 'm])), 1)'
$encoded = [System.Uri]::EscapeDataString($query)
$result = Invoke-RestMethod -Uri "$PrometheusUrl/api/v1/query?query=$encoded"
if ($result.status -ne "success") { throw "Prometheus 查询失败" }
$value = 0.0
if ($result.data.result.Count -gt 0) { $value = [double]$result.data.result[0].value[1] }
Write-Output ("当前失败率：{0:P2}，阈值：{1:P2}" -f $value, $MaxErrorRate)

if ($value -gt $MaxErrorRate) {
  $body = @{ environment = $Environment } | ConvertTo-Json
  $rollback = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/workflows/$WorkflowId/rollback" -Headers $headers -ContentType "application/json" -Body $body
  Write-Output ("已自动回滚工作流 {0} 到稳定版本 v{1}" -f $WorkflowId, $rollback.stable_version)
  exit 2
}

Write-Output "失败率在阈值内，无需回滚"
