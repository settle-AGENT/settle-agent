# 정기 작업 (systemd timer)

Amazon Linux 2023 은 cron 을 기본 설치하지 않는다(`/etc/cron.d` 가 없고
`crond` 도 inactive). 패키지를 더 깔지 않고 systemd timer 를 쓴다.

| 타이머 | 주기 | 하는 일 |
|---|---|---|
| `settle-cleanup-check` | 매일 03:15 KST | 신분증 원본 삭제가 실제로 되는지 감시 |
| `settle-purge-sessions` | 매일 03:30 KST | 마지막 활동 30일 지난 상담 세션 삭제 |

서버는 UTC 로 돌기 때문에 `OnCalendar` 은 UTC 로 적혀 있다(18:15 = 03:15 KST).

`purge_raw_texts.py` 는 여기에 없다. 코드에서 `raw_texts` 를 이미 제거해
새로 쌓이지 않으므로 1회성이다. 2026-09-05 에 적용해 blobs·writes 각 43행을
지웠다.

## 설치

`check-upload-cleanup.sh` 와 유닛 파일들은 CD 로 전달되지 않는다. SSM 으로
한 번 올린다.

```bash
aws ssm send-command --instance-ids <INSTANCE_ID> --document-name AWS-RunShellScript \
  --parameters 'commands=["systemctl daemon-reload","systemctl enable --now settle-cleanup-check.timer settle-purge-sessions.timer"]'
```

## 확인

```bash
systemctl list-timers 'settle-*'
journalctl -t settle-cleanup -p warning --since -7d   # 이상이 있을 때만 나온다
```
