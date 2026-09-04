#!/usr/bin/env bash
# EC2 에서 SSM 이 실행하는 배포 스크립트.
# CD 가 compose.selfhost.yml · Caddyfile 과 함께 이 파일을 base64 로 실어 보낸다.
#
# 전제
#   /opt/settle 에 .env · .env.secrets · runtime.env 가 이미 있다.
#   이 세 파일은 배포가 건드리지 않는다 — deploy/make-env.sh 로 한 번만 만든다.
#
# 필수 환경변수: IMAGE_PREFIX · IMAGE_TAG
set -euo pipefail

DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/settle}"
: "${IMAGE_PREFIX:?IMAGE_PREFIX is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
export IMAGE_PREFIX IMAGE_TAG

cd "$DEPLOY_ROOT"

for f in .env .env.secrets runtime.env; do
  [ -f "$f" ] || {
    echo "FAIL: ${DEPLOY_ROOT}/${f} 가 없습니다. deploy/make-env.sh 를 먼저 돌리세요." >&2
    exit 1
  }
done

compose() {
  docker compose --project-directory "$DEPLOY_ROOT" \
    -f "$DEPLOY_ROOT/compose.selfhost.yml" --env-file "$DEPLOY_ROOT/.env" "$@"
}

compose config --quiet
compose pull --quiet frontend backend ai
compose up -d --remove-orphans
# Caddyfile 이 바뀌었을 수 있다. gateway 만 항상 새로 만든다.
compose up -d --no-deps --force-recreate gateway
compose ps

# ── 헬스체크 ────────────────────────────────────────────────
# 인스턴스 안에서만 본다. 빨리 실패시키는 게 목적이고, 외부에서 진짜
# 접속되는지는 러너가 공인 DNS 로 따로 확인한다 (--resolve 로는 증명 못 한다).
domain="$(sed -n 's/^PUBLIC_DOMAIN=//p' "$DEPLOY_ROOT/.env" | head -n1)"
[ -n "$domain" ] || { echo "FAIL: .env 에 PUBLIC_DOMAIN 이 없습니다." >&2; exit 1; }

dump_logs() { compose logs --tail=200 backend ai gateway >&2 || true; }

probe() {   # probe <레이블> <경로> <jq식|TEXT:기대문자열> <타임아웃초>
  local label="$1" path="$2" check="$3" deadline=$(( $(date +%s) + $4 )) n=0 body
  while [ "$(date +%s)" -lt "$deadline" ]; do
    n=$((n + 1))
    if body="$(curl --connect-timeout 3 --max-time 5 --fail --silent \
                    --resolve "${domain}:443:127.0.0.1" "https://${domain}${path}" 2>/dev/null)"; then
      if [ "${check#TEXT:}" != "$check" ]; then
        [ "$(printf '%s' "$body" | tr -d '[:space:]')" = "${check#TEXT:}" ] && {
          echo "OK   ${label} (${n}회)"; return 0; }
      elif printf '%s' "$body" | jq -e "$check" >/dev/null 2>&1; then
        echo "OK   ${label} (${n}회)"; return 0
      fi
    fi
    sleep 5
  done
  echo "FAIL ${label} — ${4}초 안에 준비되지 않았습니다" >&2
  dump_logs
  return 1
}

probe frontend /health        'TEXT:ok'                                              120
probe backend  /health/backend '.status == "ok"'                                     300
probe ai       /health/ai      '.ok == true and .mode == "agent"
                                and .persistent == true and .rag.ready == true'      600

docker image prune -f --filter 'until=168h'
echo "deploy done — ${IMAGE_PREFIX}/*:${IMAGE_TAG}"
