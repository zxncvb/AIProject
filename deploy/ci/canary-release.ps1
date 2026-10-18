param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$Token,
  [Parameter(Mandatory=$true)][string]$WorkflowId,
  [int]$Version = 0,
  [ValidateRange(1,100)][int]$TrafficPercent = 10
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$headers = @{ Authorization = "Bearer $Token" }
$body = @{ environment = 'production'; traffic_percent = $TrafficPercent }
if ($Version -gt 0) { $body.version = $Version }
$release = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/workflows/$WorkflowId/release" -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json)
Write-Output ("已发布灰度版本 v{0}，流量比例 {1}%，状态：{2}" -f $release.version, $release.traffic_percent, $release.status)
