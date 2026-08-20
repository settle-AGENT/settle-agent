# ai — 검색 코퍼스와 RAG 파이프라인

질문이 들어오면 `app/nodes/qa.py` 가 두 코퍼스를 함께 검색하고,
검색된 근거 안에서만 LLM이 답한다. 근거 밖의 문장은 만들지 않는다.

| 코퍼스 | 무엇 | 단위 | 개수 |
|---|---|---|---|
| `rules/corpus.json` | 법령 조문 (출입국관리법·시행령·금융실명법·특정금융정보법) | 조문 | 397 |
| `rules/manual.json` | 「외국인체류 안내매뉴얼」(법무부 출입국·외국인정책본부, 2026. 8.) | 체류자격 × 쪽 | 1,212 |

법령은 **무엇이 규정인지**를, 매뉴얼은 **체류자격별로 무엇을 어떻게 내는지**를 담당한다.
"체류기간 연장 서류 뭐 필요해요?" 같은 질문의 실제 답은 법령이 아니라 매뉴얼에 있다.

## 코퍼스 만들기

```bash
uv run python scripts/build_corpus.py corpus rules/corpus.json
```

```bash
uv run python scripts/build_manual.py corpus/manual rules/manual.json
```

`corpus/` 는 법령 PDF, `corpus/manual/` 은 안내매뉴얼 PDF다.
`build_corpus.py` 의 glob 은 재귀하지 않으므로 매뉴얼이 조문 파서로 새어 들어가지 않는다.

> **안내매뉴얼 PDF 는 리포에 없다.** 15MB라 gitignore 했다.
> [하이코리아](https://www.hikorea.go.kr) 정보광장 → 자료실에서 「외국인체류 안내매뉴얼」을
> 받아 `corpus/manual/` 에 두고 `build_manual.py` 를 돌린다.
> 결과물인 `rules/manual.json` 은 커밋되어 있으므로, 코퍼스를 다시 만들 때만 원본이 필요하다.

### 매뉴얼 파싱이 하는 일

매뉴얼에는 조문이 없다. 대신 장(章) 하나가 체류자격 하나다.
**장 경계를 틀리면 D-2 유학생에게 E-9 규정을 물어다 주게 되므로** 여기가 파서의 핵심이다.

- `extraction_mode="layout"` 으로 읽어 표의 좌측 표제 열이 본문과 섞이지 않게 한다.
- 장 시작 = 쪽 머리의 `유     학(D-2)` 꼴 제목 줄. 41개 장 중 7개는 제목이 세로쓰기로
  그려져 텍스트로 추출되지 않는다 → `_UNDETECTED` 에 쪽 번호를 적고, 그 쪽에 해당
  키워드가 실제로 있는지 검증한다. 매뉴얼 판이 바뀌어 어긋나면 경고를 찍고 그 장을 건너뛴다.
- 조각 = 쪽 단위(길면 900자에서 문장·불릿 경계로 분할, 짧으면 앞 쪽에 병합).
  쪽 단위라 인용이 검증 가능하다 — `외국인체류 안내매뉴얼 유학(D-2) p.42`.
- 조각마다 `visa` (해당 체류자격 목록)를 붙인다. 검색 가중치가 이걸 쓴다.

조각 길이를 900자로 잡은 이유: 임베딩 모델 `multilingual-e5-small` 이 512토큰에서 자른다.
이보다 길면 뒷부분이 벡터에 실리지 않는다.

## 색인·적재

**평소에는 손댈 일이 없다.** 서버가 기동할 때 `app/tools/rag_store.py` 가 알아서
`rag.chunk` 를 채운다. 코퍼스·모델이 그대로면 아무것도 하지 않고, 바뀌었으면 다시 넣는다.
진행 상태는 `/health` 의 `rag` 에 나온다.

```json
{"rag": {"state": "ready", "chunks": 1609, "expected": 1609, "ready": true}}
```

`ready` 가 false 면 벡터 검색이 죽어 있고 BM25 단독으로 돌고 있다는 뜻이다.
프로덕션 배포는 이 값이 true 여야 통과한다(`cd-production.yml`).

임베딩은 이미지 빌드 때 미리 계산해 `/app/rag_chunks.jsonl` 로 굽는다. 그래서
컨테이너 기동은 upsert 만 하고 몇 초에 끝난다.

### 손으로 돌려야 할 때

```bash
uv run python scripts/export_rag.py            # 임베딩 다시 굽기 (ai/rag_chunks.jsonl)
DATABASE_URL=postgresql://... uv run python scripts/load_rag.py [--force]
```

로컬 DB 는 리포 루트의 `docker compose up -d db` (pgvector/pgvector:pg16).

## 검색

`qa.search(query, visa=...)` 는 질의를 한국어로 맞춘 뒤 두 검색기의 순위를 RRF로 합친다.

### 1. 질의 번역 (`_korean`)

코퍼스는 전부 한국어 행정 문서다. 영문 질의를 그대로 넣으면 양쪽 검색기가 같이 무너진다 —
BM25는 한글 음절 바이그램이라 영문에서 신호를 못 내고(사실상 무작위 노이즈를 낸다),
벡터도 한국어 조문과 거리가 멀다. 그래서 한글이 한 글자도 없는 질의는
`llm.translate_query()` 로 먼저 옮긴다.

직역이 아니라 **문서에 실제로 쓰인 낱말로 갈아끼우는** 게 요점이다.
`part-time job` → "시간제 일자리"로는 안 걸리고 `시간제취업 체류자격 외 활동`이어야 걸린다.
체류자격 코드·시험명·숫자(`D-2`, `TOPIK`)는 원문 그대로 둔다.
번역 결과는 `lru_cache` 로 재사용하고, LLM 이 없으면 원문으로 검색한다.

### 2. 하이브리드 검색

- **BM25** (한글 음절 바이그램) — 조문 번호, `TOPIK`, `D-2-1` 같은 고유 표현에 강하다.
  DB나 임베딩 모델이 없어도 이쪽만으로 동작한다.
- **벡터** (`rag.chunk`, pgvector 코사인) — 표현이 달라도 뜻이 같으면 잡는다.

### 3. 체류자격 가중치

합친 순위에 곱한다.

| 조각 | 가중치 |
|---|---|
| 사용자 자격과 일치 (`D-2-1` 소지자 ↔ `D-2` 장) | ×1.6 |
| 다른 자격 전용 | ×0.45 |
| 법령·공통사항 (`visa` 비어 있음) | ×1.0 |

체류자격은 `profile.visa_type` 에서 온다. 등록증을 아직 안 올려 프로필이 비어 있으면
가중치 없이 검색하고, 매뉴얼 조각은 자격을 밝혀 인용되므로 답변이 오도되지 않는다.

## 검색이 정상인지 확인

```bash
DATABASE_URL=postgresql://settle:settle@localhost:5432/settle uv run python eval/retrieval_check.py
```

정답 문서를 하나로 특정하기는 어려우므로, 무너지면 반드시 깨지는 것만 본다 —
**내 자격 문서가 남의 자격 문서에 밀리지 않는가**, 그리고 핵심 낱말이 상위 결과에 있는가.
다른 자격 조각이 후보 뒤쪽에 붙는 것 자체는 정상이다. "D-2에서 E-7으로 바꾸려면?" 같은
질문은 상대 자격 문서를 봐야 답이 되기 때문에 하드 필터가 아니라 감점으로 두었다.

`DATABASE_URL` 없이 돌리면 BM25 단독 성능을 본다.

## 코퍼스 갱신

법령은 개정되고 매뉴얼은 판이 바뀐다. 새 PDF 로 교체한 뒤:

```bash
uv run python scripts/build_manual.py corpus/manual rules/manual.json && uv run python scripts/export_rag.py
```

`build_manual.py` 출력의 장 목록(41개 + 공통사항)과 쪽 범위를 눈으로 확인하고,
`! p175 에서 '회화지도' 를 찾지 못했습니다` 같은 경고가 없는지 본다.
