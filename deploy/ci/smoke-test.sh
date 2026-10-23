#!/usr/bin/env bash
set -Eeuo pipefail

base_url="${PLATFORM_BASE_URL:-http://127.0.0.1:18080}"
: "${BOOTSTRAP_ADMIN_EMAIL:?缺少 BOOTSTRAP_ADMIN_EMAIL}"
: "${BOOTSTRAP_ADMIN_PASSWORD:?缺少 BOOTSTRAP_ADMIN_PASSWORD}"
tenant_slug="${BOOTSTRAP_TENANT_SLUG:-acme}"
for _ in $(seq 1 90); do
  if curl --fail --silent "$base_url/readyz" >/dev/null; then break; fi
  sleep 2
done
curl --fail --silent "$base_url/readyz" | jq -e '.ok == true' >/dev/null
login_payload="$(jq -n --arg email "$BOOTSTRAP_ADMIN_EMAIL" --arg password "$BOOTSTRAP_ADMIN_PASSWORD" '{email:$email,password:$password}')"
token="$(curl --fail --silent --show-error -H 'Content-Type: application/json' -d "$login_payload" "$base_url/api/auth/login" | jq -er '.access_token')"
auth=(-H "Authorization: Bearer $token")
cookie_jar="$(mktemp)"
cookie_login="$(curl --fail --silent --show-error -c "$cookie_jar" -H 'Content-Type: application/json' -H 'X-Browser-Session: 1' -d "$login_payload" "$base_url/api/auth/login")"
echo "$cookie_login" | jq -e '.user.email != null and .access_token == "" and .refresh_token == null' >/dev/null
grep -q '#HttpOnly_.*eai_access_token' "$cookie_jar"
grep -q '#HttpOnly_.*eai_refresh_token' "$cookie_jar"
csrf_token="$(awk '$6 == "eai_csrf_token" {print $7}' "$cookie_jar")"
test -n "$csrf_token"
curl --fail --silent --show-error -b "$cookie_jar" "$base_url/api/me" | jq -e '.user.email != null' >/dev/null
csrf_probe_status="$(curl --silent --output /dev/null --write-out '%{http_code}' -b "$cookie_jar" -X POST "$base_url/api/auth/logout")"
test "$csrf_probe_status" = "403"
curl --fail --silent --show-error -b "$cookie_jar" -c "$cookie_jar" -H "X-CSRF-Token: $csrf_token" -H 'Content-Type: application/json' -H 'X-Browser-Session: 1' -d '{}' "$base_url/api/auth/refresh" | jq -e '.user.email != null and .access_token == "" and .refresh_token == null' >/dev/null
csrf_token="$(awk '$6 == "eai_csrf_token" {print $7}' "$cookie_jar")"
curl --fail --silent --show-error -b "$cookie_jar" -H "X-CSRF-Token: $csrf_token" -X POST "$base_url/api/auth/logout" | jq -e '.revoked == true' >/dev/null
curl --fail --silent "${auth[@]}" "$base_url/api/me" | jq -e '.user.email != null' >/dev/null
curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg email "$BOOTSTRAP_ADMIN_EMAIL" '{email:$email}')" "$base_url/api/auth/password-reset/request" | jq -e '.accepted == true' >/dev/null
invite_email="ci-invite-$(date +%s)@example.local"
invite_json="$(curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg email "$invite_email" '{email:$email,display_name:"CI Invite",role:"viewer"}')" "$base_url/api/members/invite")"
echo "$invite_json" | jq -e '.invited == true' >/dev/null
invite_token="$(echo "$invite_json" | jq -er '.debug_token')"
new_password="CI_invited_password_123!"
curl --fail --silent --show-error -H 'Content-Type: application/json' -d "$(jq -n --arg token "$invite_token" --arg password "$new_password" '{token:$token,new_password:$password}')" "$base_url/api/auth/password-reset/confirm" | jq -e '.reset == true' >/dev/null
curl --fail --silent --show-error -H 'Content-Type: application/json' -d "$(jq -n --arg email "$invite_email" --arg password "$new_password" '{email:$email,password:$password}')" "$base_url/api/auth/login" | jq -e '.access_token != null' >/dev/null
project_id="$(curl --fail --silent "${auth[@]}" "$base_url/api/projects" | jq -er '.[0].id')"
kb_name="CI 知识库 $(date +%s)"
kb_id="$(curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg project_id "$project_id" --arg name "$kb_name" '{project_id:$project_id,name:$name}')" "$base_url/api/knowledge-bases" | jq -er '.id')"
sample_file="$(mktemp)"
trap 'rm -f -- "$sample_file" "$cookie_jar"' EXIT
printf '企业知识库 CI 测试文档\n' > "$sample_file"
curl --fail --silent --show-error "${auth[@]}" -F "file=@$sample_file;filename=ci-document.txt" "$base_url/api/knowledge-bases/$kb_id/documents" | jq -e '.security_status == "clean"' >/dev/null

# Exercise the public asynchronous application loop without requiring a model
# provider: input node -> output node, then publish/invoke/poll the result.
workflow_slug="ci-async-$(date +%s)"
workflow_json="$(curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg project_id "$project_id" --arg slug "$workflow_slug" '{project_id:$project_id,name:"CI Async Workflow",slug:$slug,graph:{nodes:[{id:"input",type:"default",data:{kind:"input"}},{id:"output",type:"default",data:{kind:"output",value:"{{input.answer}}"}}],edges:[{id:"input-output",source:"input",target:"output"}]},input_schema:{type:"object",required:["answer"],properties:{answer:{type:"string",maxLength:200}}},changelog:"CI async result smoke test"}')" "$base_url/api/workflows")"
workflow_id="$(echo "$workflow_json" | jq -er '.id')"
curl --fail --silent --show-error "${auth[@]}" -X POST "$base_url/api/workflows/$workflow_id/publish" | jq -e '.status == "published"' >/dev/null

app_slug="ci-public-async-$(date +%s)"
app_json="$(curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg project_id "$project_id" --arg slug "$app_slug" --arg workflow_id "$workflow_id" '{project_id:$project_id,name:"CI Public Async App",slug:$slug,app_type:"low_code",runtime:{public:true,input_schema:{type:"object",required:["answer"],properties:{answer:{type:"string",maxLength:200}}},workflow_id:$workflow_id,actions:[{type:"workflow",workflow_id:$workflow_id,input:"{{input}}"}]},source:{}}')" "$base_url/api/applications")"
app_id="$(echo "$app_json" | jq -er '.id')"
curl --fail --silent --show-error "${auth[@]}" -X POST "$base_url/api/applications/$app_id/deploy" | jq -e '.status == "deployed"' >/dev/null
invoke_json="$(curl --fail --silent --show-error -H 'Content-Type: application/json' -d '{"input":{"answer":"async-result-ok"}}' "$base_url/api/v1/public/apps/$tenant_slug/$app_slug/invoke")"
result_token="$(echo "$invoke_json" | jq -er '.result_token')"
result_json=''
for _ in $(seq 1 60); do
  result_json="$(curl --fail --silent --show-error "$base_url/api/v1/public/runs/$result_token")"
  result_status="$(echo "$result_json" | jq -r '.status')"
  if [[ "$result_status" == "succeeded" || "$result_status" == "failed" || "$result_status" == "cancelled" ]]; then break; fi
  sleep 2
done
echo "$result_json" | jq -e '.status == "succeeded" and .output.value == "async-result-ok"' >/dev/null

# Verify that an administrator can revoke the signed result token and that
# the public polling endpoint immediately rejects it thereafter.
curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg result_token "$result_token" '{result_token:$result_token}')" "$base_url/api/public/result-tokens/revoke" | jq -e '.revoked == true' >/dev/null
revoked_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "$base_url/api/v1/public/runs/$result_token")"
test "$revoked_status" = "410"

curl --fail --silent "${auth[@]}" "$base_url/api/admin/jobs/summary" | jq -e '.dead >= 0' >/dev/null
curl --fail --silent "$base_url/metrics" | grep -q 'ai_platform_job_queue_messages'
curl --fail --silent http://127.0.0.1:13000/ | grep -q 'lang="zh-CN"'
printf '生产拓扑冒烟测试通过\n'
