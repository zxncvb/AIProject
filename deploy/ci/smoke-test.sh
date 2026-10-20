#!/usr/bin/env bash
set -Eeuo pipefail

base_url="${PLATFORM_BASE_URL:-http://127.0.0.1:18080}"
: "${BOOTSTRAP_ADMIN_EMAIL:?缺少 BOOTSTRAP_ADMIN_EMAIL}"
: "${BOOTSTRAP_ADMIN_PASSWORD:?缺少 BOOTSTRAP_ADMIN_PASSWORD}"
for _ in $(seq 1 90); do
  if curl --fail --silent "$base_url/readyz" >/dev/null; then break; fi
  sleep 2
done
curl --fail --silent "$base_url/readyz" | jq -e '.ok == true' >/dev/null
login_payload="$(jq -n --arg email "$BOOTSTRAP_ADMIN_EMAIL" --arg password "$BOOTSTRAP_ADMIN_PASSWORD" '{email:$email,password:$password}')"
token="$(curl --fail --silent --show-error -H 'Content-Type: application/json' -d "$login_payload" "$base_url/api/auth/login" | jq -er '.access_token')"
auth=(-H "Authorization: Bearer $token")
curl --fail --silent "${auth[@]}" "$base_url/api/me" | jq -e '.user.email != null' >/dev/null
project_id="$(curl --fail --silent "${auth[@]}" "$base_url/api/projects" | jq -er '.[0].id')"
kb_name="CI 知识库 $(date +%s)"
kb_id="$(curl --fail --silent --show-error "${auth[@]}" -H 'Content-Type: application/json' -d "$(jq -n --arg project_id "$project_id" --arg name "$kb_name" '{project_id:$project_id,name:$name}')" "$base_url/api/knowledge-bases" | jq -er '.id')"
sample_file="$(mktemp)"
trap 'rm -f -- "$sample_file"' EXIT
printf '企业知识库 CI 测试文档\n' > "$sample_file"
curl --fail --silent --show-error "${auth[@]}" -F "file=@$sample_file;filename=ci-document.txt" "$base_url/api/knowledge-bases/$kb_id/documents" | jq -e '.security_status == "clean"' >/dev/null
curl --fail --silent "${auth[@]}" "$base_url/api/admin/jobs/summary" | jq -e '.dead >= 0' >/dev/null
curl --fail --silent "$base_url/metrics" | grep -q 'ai_platform_job_queue_messages'
curl --fail --silent http://127.0.0.1:13000/ | grep -q 'lang="zh-CN"'
printf '生产拓扑冒烟测试通过\n'
