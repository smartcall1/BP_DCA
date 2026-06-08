# BP DCA Bot

Backpack Exchange에서 BP 토큰을 매일 자동 매수하는 DCA 봇.
Telegram으로 알림 수신 및 현황 조회 가능. Termux(Android) 운영 최적화.

## 기능

- 매일 설정한 시각에 USDC로 BP 자동 매수
- 리밋 오더 + 가격 체이싱 (미체결 시 가격 올려서 재시도)
- DCA 완료 후 Telegram 알림 (매수량, 평균가, 누적 PnL)
- `/s` 명령어로 언제든 잔고·가격·PnL 실시간 조회

## 설치

```bash
pkg install python git   # Termux
pip install -r requirements.txt
cp .env.example .env
nano .env
python bp_dca_bot.py
```

백그라운드 실행:
```bash
nohup python bp_dca_bot.py &
```

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram 봇 토큰 (@BotFather) |
| `TELEGRAM_CHAT_ID` | 알림 받을 채팅 ID |
| `BP_API_KEY` | Backpack API 공개키 (base64) |
| `BP_API_SECRET` | Backpack API 비밀키 seed (base64) |
| `DCA_SYMBOL` | 거래 심볼 (기본: `BP_USDC`) |
| `DCA_AMOUNT_USDC` | 일일 매수 금액 (USDC) |
| `DCA_TIME_AEST` | 매수 시각 AEST 기준 (예: `09:00`) |
| `MIN_USDC_BALANCE` | 최소 USDC 버퍼 — 미달 시 DCA 스킵 |
| `ORDER_MAX_RETRIES` | 최대 재시도 횟수 (기본: 10) |
| `ORDER_PRICE_STEP_PCT` | 재시도마다 가격 상승률 % (기본: 0.1) |
| `ORDER_RETRY_INTERVAL_SEC` | 재시도 간격 초 (기본: 30) |

## Backpack API 키 발급

Backpack Exchange → Settings → API Keys → 새 키 생성 (Trade 권한 필요)

## Telegram 명령어

| 명령어 | 설명 |
|--------|------|
| `/s` | 잔고·BP가격·누적 PnL 현황 |
| `/dca` | 수동 DCA 즉시 실행 |
| `/config` | 현재 설정 확인 |
| `/start` | 봇 정보 |
