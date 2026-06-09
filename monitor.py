import logging
from datetime import datetime, timezone, timedelta

from backpack_client import BackpackClient
from config import AEST_OFFSET, BP_API_KEY, BP_API_SECRET
import state as st

logger = logging.getLogger(__name__)

AEST = timezone(timedelta(hours=AEST_OFFSET))


def _pnl_emoji(pnl: float) -> str:
    if pnl > 0:
        return "📈"
    if pnl < 0:
        return "📉"
    return "➡️"


def _fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def get_status(symbol: str = "BP_USDC") -> str:
    client = BackpackClient(BP_API_KEY, BP_API_SECRET)
    base_token = symbol.split("_")[0]
    now_aest = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")

    # --- 잔고 ---
    try:
        raw = client.get_balances()
        bp_data = raw.get(base_token, {})
        bp_avail = float(bp_data.get("available", 0))
        bp_locked = float(bp_data.get("locked", 0))
        bp_staked = float(bp_data.get("staked", 0))
        bp_total = bp_avail + bp_locked + bp_staked
    except Exception as e:
        return f"❌ 잔고 조회 실패: {e}"

    try:
        usdc_total, _ = client.get_usdc_balance()  # collateral 기준
    except Exception as e:
        logger.warning(f"USDC 조회 실패: {e}")
        usdc_total = 0.0

    # --- 가격 ---
    last_price = 0.0
    change_pct = 0.0
    high_24h = low_24h = 0.0
    best_bid = best_ask = None
    try:
        ticker = client.get_ticker(symbol)
        last_price = float(ticker.get("lastPrice", 0))
        change_pct = float(ticker.get("priceChangePercent", 0)) * 100
        high_24h = float(ticker.get("high", 0))
        low_24h = float(ticker.get("low", 0))
        best_bid, best_ask = client.get_best_bid_ask(symbol)
    except Exception as e:
        logger.warning(f"가격 조회 실패: {e}")

    bp_value = bp_total * last_price
    total_portfolio = usdc_total + bp_value

    # --- DCA 누적 현황 (state.json) ---
    s = st.load()
    total_invested = s.get("total_invested_usdc", 0.0)
    total_bp_bought = s.get("total_bp_purchased", 0.0)

    # --- 포맷팅 ---
    change_emoji = "🟢" if change_pct >= 0 else "🔴"
    lines = [
        f"📊 *BP DCA 현황*",
        f"🕐 {now_aest}",
        "━━━━━━━━━━━━━━",
        f"",
        f"🎯 *{base_token} 보유*",
        f"• 총 보유량: `{bp_total:,.2f} {base_token}`",
        f"  ├ 가용: `{bp_avail:,.2f}`",
    ]
    if bp_staked > 0:
        lines.append(f"  └ 스테이킹: `{bp_staked:,.2f}`")
    lines += [
        f"• 평가금액: `${bp_value:,.2f}`",
        "",
        f"💵 *USDC 잔고*: `${usdc_total:,.2f}`",
        f"",
        f"💼 *총 포트폴리오*: `${total_portfolio:,.2f}`",
        "",
        f"━━━━━━━━━━━━━━",
        f"",
        f"{change_emoji} *{symbol} 가격*",
        f"• 현재가: `${last_price:.5f}` ({_fmt_pct(change_pct)} 24h)",
        f"• 고가: `${high_24h:.5f}` / 저가: `${low_24h:.5f}`",
    ]
    if best_bid and best_ask:
        spread_pct = (best_ask - best_bid) / best_ask * 100
        lines += [
            f"• Bid: `${best_bid:.5f}` / Ask: `${best_ask:.5f}`",
            f"• 스프레드: `{spread_pct:.3f}%`",
        ]

    # DCA 누적 PnL (state.json에 데이터 있을 때만)
    if total_invested > 0 and total_bp_bought > 0 and last_price > 0:
        avg_cost = total_invested / total_bp_bought
        current_val = total_bp_bought * last_price
        pnl = current_val - total_invested
        pnl_pct = pnl / total_invested * 100
        pnl_emoji = _pnl_emoji(pnl)
        lines += [
            "",
            "━━━━━━━━━━━━━━",
            "",
            f"{pnl_emoji} *DCA 누적 현황*",
            f"• 총 투입: `${total_invested:,.2f}`",
            f"• 총 매수량: `{total_bp_bought:,.4f} {base_token}`",
            f"• 평균 매수가: `${avg_cost:.5f}`",
            f"• 현재 가치: `${current_val:,.2f}`",
            f"• 미실현 PnL: `{'%+.2f' % pnl}` (`{_fmt_pct(pnl_pct)}`)",
        ]
    elif total_invested == 0:
        lines += [
            "",
            "━━━━━━━━━━━━━━",
            "📝 _DCA 미실행 — /dca 로 첫 매수 가능_",
        ]

    return "\n".join(lines)


def get_price_ticker(symbol: str = "BP_USDC") -> str:
    client = BackpackClient(BP_API_KEY, BP_API_SECRET)
    base_token = symbol.split("_")[0]
    now_aest = datetime.now(AEST).strftime("%H:%M AEST")

    try:
        ticker = client.get_ticker(symbol)
        last_price = float(ticker.get("lastPrice", 0))
        change_pct = float(ticker.get("priceChangePercent", 0)) * 100
        high_24h = float(ticker.get("high", 0))
        low_24h = float(ticker.get("low", 0))
    except Exception as e:
        logger.warning(f"가격 티커 조회 실패: {e}")
        return f"❌ 가격 조회 실패: {e}"

    return f"🎒 ${last_price:.4f} ({_fmt_pct(change_pct)} 24h)"
