"""체크포인트에 남아 있는 OCR 원문(raw_texts)을 지운다.

배경
  raw_texts 는 신분증에서 읽어낸 텍스트 전문이다. 읽는 코드가 없는데
  체크포인터가 AgentState 를 통째로 직렬화하는 바람에 평문으로 쌓였다.
  코드에서는 제거했지만(그 커밋 이후로는 새로 쌓이지 않는다) 이미 저장된
  것은 그대로 남아 있다. 이 스크립트가 그것을 지운다.

지우는 곳
  checkpoint_blobs    channel = 'raw_texts'  ← 값이 실제로 있는 곳
  checkpoint_writes   channel = 'raw_texts'  ← 처리 중이던 쓰기
  checkpoints.metadata                       ← 옛 LangGraph 는 writes 를 여기
                                               담았다. 지금 버전은 아니지만,
                                               그때 만들어진 행이 있을 수 있다.

지우지 않는 것
  checkpoints.checkpoint 의 channel_versions 에 남는 'raw_texts' 항목.
  버전 문자열일 뿐 값이 아니고, 로더가 checkpoint_blobs 를 INNER JOIN 으로
  붙이므로 blob 이 없으면 그 채널은 조용히 빠진다. 건드리면 오히려 체크포인트
  구조를 흔든다.

백업하지 않는다
  지우는 목적이 보관하지 않는 것이다. 파일로 빼두면 같은 데이터가 장소만
  옮겨 남는다. 그래서 이 스크립트는 어떤 원문도 화면이나 디스크에 쓰지 않는다.

사용
  DATABASE_URL=postgresql://... uv run python scripts/purge_raw_texts.py
      무엇이 얼마나 있는지만 센다 (기본값, 아무것도 지우지 않는다)

  DATABASE_URL=postgresql://... uv run python scripts/purge_raw_texts.py --apply
      실제로 지운다. 한 트랜잭션으로 처리하고 끝나면 다시 세어 확인한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CHANNEL = "raw_texts"


def _strip(value):
    """중첩 구조 어디에 있든 raw_texts 키를 걷어낸다."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k != CHANNEL}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def survey(conn) -> dict[str, int]:
    """무엇이 얼마나 남아 있는지. 값 자체는 읽지 않는다 — 세기만 한다."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), count(DISTINCT thread_id) FROM checkpoint_blobs "
            "WHERE channel = %s", (CHANNEL,))
        blob_rows, blob_threads = cur.fetchone()

        cur.execute(
            "SELECT count(*), count(DISTINCT thread_id) FROM checkpoint_writes "
            "WHERE channel = %s", (CHANNEL,))
        write_rows, write_threads = cur.fetchone()

        # metadata 는 jsonb 다. 문자열 포함 검사로 후보만 좁히고, 실제 판단은
        # 파이썬에서 한다 — 'raw_texts' 가 값 안에 우연히 들어 있을 수도 있다.
        cur.execute(
            "SELECT count(*) FROM checkpoints "
            "WHERE metadata::text LIKE %s", (f"%{CHANNEL}%",))
        (meta_rows,) = cur.fetchone()

    return {
        "blob_rows": blob_rows, "blob_threads": blob_threads,
        "write_rows": write_rows, "write_threads": write_threads,
        "meta_rows": meta_rows,
    }


def purge(conn) -> dict[str, int]:
    """한 트랜잭션으로 지운다. 중간에 실패하면 전부 되돌아간다."""
    deleted = {"blobs": 0, "writes": 0, "metadata": 0}

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM checkpoint_blobs WHERE channel = %s", (CHANNEL,))
        deleted["blobs"] = cur.rowcount

        cur.execute("DELETE FROM checkpoint_writes WHERE channel = %s", (CHANNEL,))
        deleted["writes"] = cur.rowcount

        cur.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id, metadata "
            "FROM checkpoints WHERE metadata::text LIKE %s", (f"%{CHANNEL}%",))
        for thread_id, ns, checkpoint_id, metadata in cur.fetchall():
            cleaned = _strip(metadata)
            if cleaned == metadata:
                continue                     # 문자열만 스쳤다 — 건드리지 않는다
            with conn.cursor() as upd:
                upd.execute(
                    "UPDATE checkpoints SET metadata = %s "
                    "WHERE thread_id = %s AND checkpoint_ns = %s "
                    "AND checkpoint_id = %s",
                    (json.dumps(cleaned), thread_id, ns, checkpoint_id))
            deleted["metadata"] += 1

    return deleted


def integrity(conn) -> tuple[int, int]:
    """지운 뒤에도 체크포인트가 온전한지. 세션 수와 최신 체크포인트 수를 센다."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT thread_id), count(*) FROM checkpoints")
        return cur.fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="실제로 지운다. 없으면 세기만 한다.")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2

    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        threads, checkpoints = integrity(conn)
        print(f"전체    · 세션 {threads}개 · 체크포인트 {checkpoints}행")

        before = survey(conn)
        print(f"blobs   · {before['blob_rows']}행 "
              f"(세션 {before['blob_threads']}개)")
        print(f"writes  · {before['write_rows']}행 "
              f"(세션 {before['write_threads']}개)")
        print(f"metadata· {before['meta_rows']}행 (후보)")

        total = before["blob_rows"] + before["write_rows"] + before["meta_rows"]
        if total == 0:
            print("\n남아 있는 것이 없습니다.")
            return 0

        if not args.apply:
            print("\n세기만 했습니다. 실제로 지우려면 --apply 를 붙이세요.")
            return 0

        print("\n지웁니다...")
        deleted = purge(conn)
        print(f"  blobs    {deleted['blobs']}행 삭제")
        print(f"  writes   {deleted['writes']}행 삭제")
        print(f"  metadata {deleted['metadata']}행 수정")

        after = survey(conn)
        left = after["blob_rows"] + after["write_rows"]
        threads_after, checkpoints_after = integrity(conn)

        print(f"\n확인 · 남은 raw_texts {left}행")
        print(f"확인 · 세션 {threads_after}개 · 체크포인트 {checkpoints_after}행 "
              f"({'변동 없음' if (threads, checkpoints) == (threads_after, checkpoints_after) else '변동 있음 — 확인 필요'})")
        return 0 if left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
