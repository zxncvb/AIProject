param(
  [string]$OutputDirectory = "$(Join-Path $PSScriptRoot 'archives')"
)

$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$archiveDirectory = New-Item -ItemType Directory -Force -Path $OutputDirectory
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $archiveDirectory "platform-$stamp.dump"
$artifactPath = Join-Path $archiveDirectory "artifacts-$stamp.tar.gz"

Push-Location $projectDirectory
try {
  $postgresContainer = (docker compose ps -q postgres).Trim()
  if (-not $postgresContainer) { throw "找不到正在运行的 PostgreSQL 容器" }
  docker exec $postgresContainer pg_dump -U platform -d platform --format=custom -f /tmp/platform.dump
  docker cp "${postgresContainer}:/tmp/platform.dump" $dumpPath
  docker exec $postgresContainer rm -f /tmp/platform.dump
  docker run --rm -v enterprise_ai_platform-platform-artifacts:/data -v "$($archiveDirectory.FullName):/backup" alpine:3.22 tar -czf "/backup/artifacts-$stamp.tar.gz" -C /data .
  Write-Output "数据库备份: $dumpPath"
  Write-Output "附件备份: $artifactPath"
}
finally {
  Pop-Location
}
