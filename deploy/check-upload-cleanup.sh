#!/usr/bin/env bash
# 신분증 원본이 실제로 지워지고 있는지 확인한다.
#
# 왜 필요한가
#   FileService.discardOriginal 은 삭제 실패를 삼키고 로그만 남긴다 —
#   추출은 이미 끝났으므로 성공한 요청을 실패로 뒤집지 않으려는 의도된 설계다.
#   그 대가로 권한이 빠지거나 키가 어긋나면 개인정보가 조용히 쌓이고, 화면과
#   헬스체크에는 아무 이상이 없다. 2026-09-05 에 실제로 그 일이 있었다
#   (EC2 역할에 s3:DeleteObject 누락 → 신분증 원본 29건 잔존).
#
# 사용
#   BUCKET=<버킷명> /opt/settle/check-upload-cleanup.sh
#
# 이상이 있으면 journald 에 warning 으로 남고 종료코드 1 을 낸다.
#   journalctl -t settle-cleanup -p warning --since -7d
set -uo pipefail

TAG=settle-cleanup
COMPOSE="${COMPOSE:-/opt/settle/compose.selfhost.yml}"
ENVFILE="${ENVFILE:-/opt/settle/.env}"
BUCKET="${BUCKET:-}"
AGE_HOURS="${AGE_HOURS:-24}"
fail=0

note()  { logger -t "$TAG" "$*"; echo "ok   $*"; }
warn()  { logger -t "$TAG" -p user.warning "$*"; echo "WARN $*" >&2; fail=1; }

# ── 1. 앱 로그 — 삭제가 예외로 실패한 흔적 (추가 권한 불필요) ──
hits="$(docker compose -f "$COMPOSE" --env-file "$ENVFILE" logs --since 24h backend 2>/dev/null \
        | grep -c '업로드 원본 삭제 실패')"
if [ "${hits:-0}" -gt 0 ]; then
  warn "최근 24시간 삭제 실패 로그 ${hits}건 — IAM 권한과 객체 키를 확인할 것"
else
  note "삭제 실패 로그 없음"
fi

# ── 2. S3 — 지워졌어야 할 원본이 남아 있는가 ──────────────────
# s3:ListBucket 이 없으면 건너뛴다. 1번만으로도 대부분의 실패는 잡힌다.
if [ -z "$BUCKET" ]; then
  note "BUCKET 미지정 — S3 잔존 검사 생략"
else
  cutoff="$(date -u -d "${AGE_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)"
  out="$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix 'members/' \
           --query "Contents[?LastModified<='${cutoff}'].Key" --output text 2>&1)"
  if printf '%s' "$out" | grep -q 'AccessDenied\|not authorized'; then
    note "s3:ListBucket 권한 없음 — S3 잔존 검사 생략"
  else
    left="$(printf '%s' "$out" | tr '\t' '\n' | grep -c '/uploads/')"
    if [ "${left:-0}" -gt 0 ]; then
      warn "신분증 원본 ${left}건이 ${AGE_HOURS}시간 넘게 남아 있다 — 즉시 삭제가 동작하지 않는다"
    else
      note "S3 에 남은 신분증 원본 없음"
    fi
  fi
fi

exit "$fail"
