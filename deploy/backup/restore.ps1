param(
  [Parameter(Mandatory=$true)][string]$DumpFile,
  [string]$ArtifactsFile = ""
)

$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectDirectory
try {
  Write-Warning "恢复会覆盖当前数据库内容，请确认备份文件和目标环境。"
  Get-Content -Path $DumpFile -AsByteStream | docker compose exec -T postgres pg_restore -U platform -d platform --clean --if-exists --no-owner
  if ($ArtifactsFile) {
    docker run --rm -i -v enterprise_ai_platform-platform-artifacts:/data -v "$(Split-Path -Parent (Resolve-Path $ArtifactsFile)):/backup" alpine:3.22 sh -c "rm -rf /data/*; tar -xzf /backup/$(Split-Path -Leaf $ArtifactsFile) -C /data"
  }
}
finally {
  Pop-Location
}
