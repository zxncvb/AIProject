param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$Token,
  [Parameter(Mandatory=$true)][string]$DatasetPath,
  [double]$MinPassRate = 0.95,
  [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$headers = @{ Authorization = "Bearer $Token" }
$cases = Get-Content -Raw -Encoding utf8 $DatasetPath | ConvertFrom-Json
if (-not $cases -or $cases.Count -eq 0) { throw "评测集不能为空" }
$passed = 0

foreach ($case in $cases) {
  $payload = @{ input = $case.input }
  if ($case.PSObject.Properties.Name -contains 'version' -and $null -ne $case.version) { $payload.version = [int]$case.version }
  $run = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/workflows/$($case.workflow_id)/runs" -Headers $headers -ContentType 'application/json' -Body ($payload | ConvertTo-Json -Depth 20)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    Start-Sleep -Seconds 2
    $result = Invoke-RestMethod -Uri "$BaseUrl/api/runs/$($run.run_id)" -Headers $headers
  } while ($result.status -in @('queued', 'running', 'waiting_approval') -and (Get-Date) -lt $deadline)
  $text = ($result.output | ConvertTo-Json -Depth 20 -Compress)
  $expected = @($case.expected_contains)
  $ok = $result.status -eq 'succeeded' -and ($expected | Where-Object { $text -notlike "*$_*" }).Count -eq 0
  if ($ok) { $passed++ }
  Write-Output ("{0}: {1} ({2})" -f $case.workflow_id, ($(if ($ok) { '通过' } else { '失败' })), $result.status)
}

$passRate = $passed / [double]$cases.Count
Write-Output ("评测通过率：{0:P2}，门禁：{1:P2}" -f $passRate, $MinPassRate)
if ($passRate -lt $MinPassRate) { throw "评测门禁失败" }
