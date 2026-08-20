#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT

mkdir -p "$test_root/bin" "$test_root/deploy"

cat > "$test_root/bin/aws" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "$*" in
  *rds-test-secret*)
    printf '%s\n' '{"username":"test_user","password":"safe$QqZ3M"}'
    ;;
  *app-test-secret*)
    printf '%s\n' '{"AUTH_PASSCODE":"12$code","JWT_SECRET":"jwt$segment"}'
    ;;
  *)
    printf 'unexpected aws invocation: %s\n' "$*" >&2
    exit 1
    ;;
esac
EOF
chmod 700 "$test_root/bin/aws"

cp "$repo_root/compose.production.yml" "$test_root/deploy/compose.production.yml"
mkdir -p "$test_root/deploy/deploy"
cp "$repo_root/deploy/Caddyfile" "$test_root/deploy/deploy/Caddyfile"

cat > "$test_root/deploy/deploy.env" <<'EOF'
ECR_REGISTRY=registry.example.invalid
ECR_FRONTEND_REPOSITORY=fsai/frontend
ECR_BACKEND_REPOSITORY=fsai/backend
ECR_AI_REPOSITORY=fsai/ai
IMAGE_TAG=test
EOF

PATH="$test_root/bin:$PATH" \
DEPLOY_ROOT="$test_root/deploy" \
AWS_REGION="ap-northeast-2" \
RDS_SECRET_ID="rds-test-secret" \
APP_SECRET_ID="app-test-secret" \
RDS_ENDPOINT="db.example.internal" \
RDS_PORT="5432" \
RDS_DATABASE="settlement" \
AWS_S3_BUCKET="test-bucket" \
  "$repo_root/deploy/prepare-runtime-env.sh"

compose_stderr="$test_root/compose.stderr"
rendered_json="$(
  docker compose \
    --env-file "$test_root/deploy/deploy.env" \
    -f "$test_root/deploy/compose.production.yml" \
    config --format json 2>"$compose_stderr"
)"

if grep -q 'variable is not set' "$compose_stderr"; then
  cat "$compose_stderr" >&2
  exit 1
fi

jq -e '
  .services.backend.environment.DB_PASSWORD == "safe$$QqZ3M" and
  .services.backend.environment.AUTH_PASSCODE == "12$$code" and
  .services.backend.environment.JWT_SECRET == "jwt$$segment"
' <<<"$rendered_json" >/dev/null

printf '%s\n' 'runtime env rendering: ok'
