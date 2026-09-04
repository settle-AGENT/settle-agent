#!/usr/bin/env bash
# 단일 박스 배포용 env 3종을 한 번에 만든다.
#
#   .env          compose 치환용
#   .env.secrets  backend  (compose 가 format: raw 로 읽는다 → 따옴표 금지)
#   runtime.env   ai       (동일)
#
# DB 비밀번호가 세 파일에 흩어지므로 손으로 쓰면 반드시 어긋난다.
# 비밀번호·JWT 는 여기서 생성하고, 외부 키만 물어본다.
#
# 배포 서버에서:  cd /opt/settle && ./make-env.sh
#   (CD 가 이미지를 배포하므로 서버에는 리포가 없다. 이 스크립트만 scp 로 옮긴다.)
# 로컬에서:      DEPLOY_ROOT=. ./deploy/make-env.sh
set -euo pipefail
cd "${DEPLOY_ROOT:-$PWD}"
echo "생성 위치: $PWD"

for f in .env .env.secrets runtime.env; do
  [ -e "$f" ] && { echo "FAIL: $f 가 이미 있습니다. 덮어쓰려면 먼저 지우세요."; exit 1; }
done
command -v openssl >/dev/null || { echo "FAIL: openssl 이 없습니다."; exit 1; }

ask() {   # ask VAR "프롬프트" [기본값]
  local __var="$1" __prompt="$2" __default="${3:-}" __in
  if [ -n "$__default" ]; then
    read -rp "  ${__prompt} [${__default}]: " __in
  else
    read -rp "  ${__prompt}: " __in
  fi
  __in="${__in:-$__default}"
  [ -n "$__in" ] || { echo "FAIL: ${__prompt} 는 비울 수 없습니다."; exit 1; }
  printf -v "$__var" '%s' "$__in"
}

echo "── 배포 설정 ──"
ask PUBLIC_DOMAIN     "도메인"            "kaffy.kro.kr"
ask AWS_REGION        "AWS 리전"          "ap-northeast-2"
ask AWS_S3_BUCKET     "S3 버킷명"
echo "── 외부 API 키 ──"
ask ANTHROPIC_API_KEY "ANTHROPIC_API_KEY"
ask CLOVA_INVOKE_URL  "CLOVA_INVOKE_URL"
ask CLOVA_SECRET_KEY  "CLOVA_SECRET_KEY"

DB_NAME=settle
DB_USER=settle
# hex 만 쓴다. compose 의 raw env 파서는 따옴표·특수문자를 그대로 값에 넣는다.
DB_PASS="$(openssl rand -hex 24)"
JWT_SECRET="$(openssl rand -hex 32)"

umask 077

cat > .env <<EOF
PUBLIC_DOMAIN=${PUBLIC_DOMAIN}
PUBLIC_HTTP_PORT=80
PUBLIC_HTTPS_PORT=443
FRONTEND_CONTAINER_PORT=3000
BACKEND_CONTAINER_PORT=8080
AI_CONTAINER_PORT=8000

POSTGRES_USER=${DB_USER}
POSTGRES_DB=${DB_NAME}
POSTGRES_PASSWORD=${DB_PASS}

# 빈 DB 첫 기동은 update. 테이블 생성 확인 후 validate 로 바꾸고
#   docker compose -f compose.selfhost.yml --env-file .env up -d --force-recreate backend
JPA_DDL_AUTO=update
EOF

cat > .env.secrets <<EOF
DB_URL=jdbc:postgresql://db:5432/${DB_NAME}
DB_USERNAME=${DB_USER}
DB_PASSWORD=${DB_PASS}
JWT_SECRET=${JWT_SECRET}
JWT_ACCESS_TOKEN_TTL_SECONDS=3600
AWS_REGION=${AWS_REGION}
AWS_S3_BUCKET=${AWS_S3_BUCKET}
AI_CONNECT_TIMEOUT_SECONDS=5
AI_READ_TIMEOUT_SECONDS=120
EOF

cat > runtime.env <<EOF
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@db:5432/${DB_NAME}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=claude-sonnet-4-5
CLOVA_INVOKE_URL=${CLOVA_INVOKE_URL}
CLOVA_SECRET_KEY=${CLOVA_SECRET_KEY}
RESEARCH_ENABLED=1
EOF

chmod 600 .env .env.secrets runtime.env
echo
echo "생성 완료 (모두 600):"
ls -l .env .env.secrets runtime.env
echo
echo "세 파일 모두 .gitignore 에 걸려 있습니다. 커밋되지 않습니다."
