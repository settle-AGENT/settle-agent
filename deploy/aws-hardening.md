# AWS 쪽에서 해야 하는 것

코드로 못 하는 것들이다. 콘솔이나 CLI로 한 번 적용하면 되고, 적용 여부가
리포에 드러나지 않으므로 여기에 적어 둔다. `BUCKET_NAME`·`INSTANCE_ID`는
실제 값으로 바꾼다.

## 1. S3 버킷 기본 암호화 — 필수

업로드되는 신분증 사진은 presigned PUT으로 브라우저가 직접 올린다. 그래서
서버가 요청에 `x-amz-server-side-encryption`을 붙일 수 없다 — 붙이면 올리는
쪽이 같은 헤더를 보내야 서명이 맞고, 프론트는 `Content-Type`만 보낸다.

**버킷 기본 암호화로 덮는 것이 유일한 방법이다.** 켜 두면 어떤 경로로 들어온
객체든 저장 시점에 암호화된다.

```bash
aws s3api put-bucket-encryption --bucket BUCKET_NAME \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

키를 직접 관리하려면 `AES256` 대신 `aws:kms`와 `KMSMasterKeyID`를 쓴다. 그
경우 앱의 IAM 역할에 `kms:GenerateDataKey`·`kms:Decrypt`가 추가로 필요하다.
`BucketKeyEnabled`는 SSE-KMS 전용이라 위의 AES256 설정에는 넣지 않는다.

생성된 PDF는 서버가 SDK로 직접 올리므로 코드에서 `ServerSideEncryption.AES256`을
명시해 두었다(`AwsS3FileGateway.uploadPdf`). 버킷 설정이 꺼져도 그쪽은 암호화된다.

확인:

```bash
aws s3api get-bucket-encryption --bucket BUCKET_NAME
```

## 2. 퍼블릭 액세스 차단 — 필수

신분증 사진과 생성 서류가 들어 있는 버킷이다.

```bash
aws s3api put-public-access-block --bucket BUCKET_NAME \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 3. IAM 정책에 `s3:DeleteObject` 추가 — 필수

`FileService`가 OCR이 끝난 신분증 원본을 즉시 지운다. 권한이 없으면 삭제가
실패하고(로그에 `업로드 원본 삭제 실패`가 찍힌다) 원본이 그대로 쌓인다.

삭제 권한은 `members/*/uploads/*` 로만 좁혀 두었다. 앱이 지우는 것은 업로드
원본뿐이고, 키를 잘못 계산하는 버그가 나더라도 서류함(`generated-documents/`)이
날아가지 않아야 한다.

갱신된 정책은 [`iam-s3-policy.json`](iam-s3-policy.json)에 있다.

```bash
aws iam put-role-policy --role-name EC2_ROLE_NAME \
  --policy-name settle-s3 --policy-document file://deploy/iam-s3-policy.json
```

## 4. 남아 있는 신분증 원본 정리 — 1회

즉시 삭제는 앞으로 올라오는 것에만 적용된다. 그 전에 쌓인 것은 남아 있다.

```bash
aws s3 ls s3://BUCKET_NAME/ --recursive | grep '/uploads/' | wc -l
aws s3 rm s3://BUCKET_NAME/ --recursive --exclude '*' --include '*/uploads/*'
```

`generated-documents/`는 서류함이라 지우면 안 된다. `--include` 패턴을 반드시
확인하고 돌린다.

## 5. EBS 볼륨 암호화 — 결정 필요

Postgres가 EC2 위의 컨테이너로 돌고 데이터는 `pgdata` 도커 볼륨, 즉 EBS에
있다. 체크포인트의 프로필이 여기 저장된다.

**EBS 암호화는 기존 볼륨에 제자리 적용이 안 된다.** 스냅샷 → 암호화 복사 →
새 볼륨 생성 → 교체가 필요하고 그동안 서비스가 멈춘다.

```bash
# 1) 중지
aws ssm send-command --instance-ids INSTANCE_ID \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cd /opt/settle && docker compose -f compose.selfhost.yml down"]'

# 2) 스냅샷 → 암호화 복사 → 새 볼륨 → detach/attach → 기동
#    (볼륨 ID·AZ 확인이 필요하므로 콘솔에서 하는 편이 안전하다)
```

앞으로 만드는 인스턴스에 자동 적용하려면 리전 기본값을 켠다. 기존 볼륨에는
영향이 없다.

```bash
aws ec2 enable-ebs-encryption-by-default --region ap-northeast-2
```

## 6. 보관기간 — 세션 30일

EC2에서 주기적으로 돌린다. 두 스크립트 모두 기본이 dry-run이고
`--apply`를 붙여야 실제로 지운다.

```bash
# 마지막 활동 기준 30일이 지난 상담 세션 (30일이 기본값이라 --days 생략 가능)
docker compose -f /opt/settle/compose.selfhost.yml exec -T ai \
  python scripts/purge_stale_sessions.py --apply

# 옛 체크포인트에 남은 OCR 원문 (1회)
docker compose -f /opt/settle/compose.selfhost.yml exec -T ai \
  python scripts/purge_raw_texts.py --apply
```

## 아직 안 한 것

- **컨테이너 로그의 개인정보** — 오류 응답에서는 걷어냈지만 서버 로그의
  traceback에는 남는다. 로그 보관기간과 수집 범위를 따로 정해야 한다.
- **외부 전송 고지** — 신분증 이미지가 네이버 클로바로(위탁), 사용자 발화와
  체류자격·국적 등이 Anthropic으로 나간다(국외이전). 처리방침과 위탁 계약이
  필요하다. 코드가 아니라 문서 작업이다.
- **고유식별정보 앱 레벨 암호화** — 외국인등록번호·여권번호가 체크포인트에
  평문으로 들어간다. 저장 매체 암호화(5번)와는 별개 의무다.
