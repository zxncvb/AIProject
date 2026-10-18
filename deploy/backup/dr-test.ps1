param(
  [Parameter(Mandatory=$true)][string]$DumpFile,
  [Parameter(Mandatory=$true)][string]$ArtifactsFile,
  [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$started = Get-Date
Write-Output "开始灾备恢复演练: $started"

& "$PSScriptRoot\restore.ps1" -DumpFile $DumpFile -ArtifactsFile $ArtifactsFile
if ($LASTEXITCODE -ne 0) { throw "恢复脚本执行失败" }

$ready = Invoke-RestMethod -Uri "http://localhost:18080/readyz" -Method Get
if (-not $ready.ok) { throw "恢复后就绪检查失败" }

$ended = Get-Date
$elapsed = ($ended - $started).TotalSeconds
Write-Output "灾备恢复演练通过，耗时 ${elapsed}s"
Write-Output "请将耗时与企业 RTO 目标对比，并人工核对登录、知识库和工作流数据。"
