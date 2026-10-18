param(
  [string]$ImagePrefix = "enterprise_ai_platform",
  [switch]$VerifySignatures
)

$ErrorActionPreference = "Stop"
$images = @("${ImagePrefix}-backend:latest", "${ImagePrefix}-worker:latest", "${ImagePrefix}-frontend:latest")
foreach ($image in $images) {
  if (Get-Command trivy -ErrorAction SilentlyContinue) {
    trivy image --exit-code 1 --severity HIGH,CRITICAL $image
  } else {
    Write-Warning "未找到 trivy，跳过镜像漏洞扫描: $image"
  }
  if ($VerifySignatures -and (Get-Command cosign -ErrorAction SilentlyContinue)) {
    cosign verify $image
  }
}
Write-Output "安全扫描流程完成。生产 CI 必须将 HIGH/CRITICAL 结果作为发布门禁。"
