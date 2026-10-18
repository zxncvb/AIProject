param(
  [string]$BaseUrl = "http://localhost:18080",
  [string]$Email = "admin",
  [Parameter(Mandatory = $true)][string]$Password
)

$ErrorActionPreference = "Stop"
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login" -ContentType "application/json" -Body (@{ email = $Email; password = $Password } | ConvertTo-Json)
$headers = @{ Authorization = "Bearer $($login.access_token)" }
$ready = Invoke-RestMethod -Uri "$BaseUrl/readyz"
if (-not $ready.ok) { throw "readyz failed" }
$openapi = Invoke-RestMethod -Uri "$BaseUrl/openapi.json"
$required = @(
  "/api/me/mfa/setup",
  "/scim/v2.0/{tenant_slug}/Users",
  "/api/compute/gpu/leases",
  "/api/runtime/sandbox/runs",
  "/api/evaluations/jobs",
  "/api/admin/alerts/test",
  "/api/admin/security/rotate-secrets"
)
foreach ($path in $required) { if (-not ($openapi.paths.PSObject.Properties.Name -contains $path)) { throw "missing endpoint: $path" } }
$token = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/admin/scim/tokens" -Headers $headers -ContentType "application/json" -Body (@{ name = "acceptance-$([guid]::NewGuid())" } | ConvertTo-Json)
try {
  $scimHeaders = @{ Authorization = "Bearer $($token.token)" }
  $users = Invoke-RestMethod -Uri "$BaseUrl/scim/v2.0/acme/Users" -Headers $scimHeaders
  $sandbox = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/runtime/sandbox/runs" -Headers $headers -ContentType "application/json" -Body (@{ runtime = "python"; source = @{ command = @("sh", "-c", "echo acceptance") } } | ConvertTo-Json -Depth 5)
  [pscustomobject]@{ ready = $ready.ok; scim_users = $users.totalResults; sandbox_id = $sandbox.id; sandbox_status = $sandbox.status; endpoints = $required.Count } | ConvertTo-Json -Compress
}
finally {
  Invoke-RestMethod -Method Delete -Uri "$BaseUrl/api/admin/scim/tokens/$($token.id)" -Headers $headers | Out-Null
}
