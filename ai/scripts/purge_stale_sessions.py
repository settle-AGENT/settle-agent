"""오래 손대지 않은 상담 세션을 통째로 지운다 (보관기간 시행).

무엇을 지우는가
  체크포인터에 쌓인 세션 상태 전부 — profile(외국인등록번호·여권번호·주소
  포함), 대화 이력, 과제 진행 상황. 마지막 체크포인트 시각이 기준일보다
  오래된 thread 를 통째로 없앤다.

무엇을 지우지 않는가
  생성된 서류(S3)와 회원 계정. 서류함은 상담 세션이 아니라 회원 소유
  자산이라서 세션이 사라져도 남아야 한다 — GeneratedDocumentService 의
  listReady 주석과 같은 판단이다. 그쪽 보관기간은 별도로 정해야 한다.

기준
  thread 별 max(checkpoint->>'ts') 를 마지막 활동 시각으로 본다. ts 는
  ISO 8601 UTC 문자열이라 문자열 비교로 정렬·비교가 성립한다.

  '마지막 활동' 기준이지 '생성' 기준이 아니다. 90일 기한을 추적하는 앱이라,
  계속 쓰는 사람의 상태를 나이만으로 지우면 D-day 가 매번 리셋된다.

보관기간
  기본 30일. 외국인등록 기한이 90일인 것을 감안하면 짧지만, 그 사이 한 번도
  들어오지 않은 사람이라면 처음부터 다시 시작하는 편이 자연스럽다. 늘리려면
  --days 로 덮는다.

사용
  DATABASE_URL=postgresql://... uv run python scripts/purge_stale_sessions.py
      대상만 센다 (기본값, 아무것도 지우지 않는다)

  DATABASE_URL=postgresql://... uv run python scripts/purge_stale_sessions.py --apply
      실제로 지운다.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

TABLES = ("checkpoint_blobs", "checkpoint_writes", "checkpoints")

# 정해진 보관기간. 바꾸려면 여기와 README·deploy/aws-hardening.md 를 같이 고친다.
RETENTION_DAYS = 30


def stale_threads(conn, cutoff: str) -> list[str]:
    """마지막 활동이 cutoff 보다 오래된 thread_id 목록."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT thread_id FROM checkpoints "
            "GROUP BY thread_id "
            "HAVING max(checkpoint->>'ts') < %s "
            "ORDER BY max(checkpoint->>'ts')", (cutoff,))
        return [row[0] for row in cur.fetchall()]


def totals(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT thread_id), count(*) FROM checkpoints")
        return cur.fetchone()


def purge(conn, threads: list[str]) -> dict[str, int]:
    """세 테이블에서 해당 thread 를 지운다. 한 트랜잭션으로 처리한다."""
    deleted = {t: 0 for t in TABLES}
    if not threads:
        return deleted

    with conn.transaction(), conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DELETE FROM {table} WHERE thread_id = ANY(%s)", (threads,))
            deleted[table] = cur.rowcount
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=RETENTION_DAYS,
                        help=f"이 일수보다 오래 손대지 않은 세션을 지운다 "
                             f"(기본 {RETENTION_DAYS}일).")
    parser.add_argument("--apply", action="store_true",
                        help="실제로 지운다. 없으면 세기만 한다.")
    args = parser.parse_args()

    if args.days < 1:
        print("--days 는 1 이상이어야 합니다.", file=sys.stderr)
        return 2

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        threads_before, rows_before = totals(conn)
        stale = stale_threads(conn, cutoff)

        print(f"기준     · {args.days}일 (cutoff {cutoff[:19]}Z)")
        print(f"전체     · 세션 {threads_before}개 · 체크포인트 {rows_before}행")
        print(f"삭제 대상· 세션 {len(stale)}개")

        if not stale:
            print("\n지울 세션이 없습니다.")
            return 0

        if not args.apply:
            print("\n세기만 했습니다. 실제로 지우려면 --apply 를 붙이세요.")
            return 0

        print("\n지웁니다...")
        deleted = purge(conn, stale)
        for table in TABLES:
            print(f"  {table:<18} {deleted[table]}행 삭제")

        threads_after, rows_after = totals(conn)
        left = stale_threads(conn, cutoff)
        print(f"\n확인 · 남은 대상 {len(left)}개")
        print(f"확인 · 세션 {threads_before} → {threads_after}개 · "
              f"체크포인트 {rows_before} → {rows_after}행")
        return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
