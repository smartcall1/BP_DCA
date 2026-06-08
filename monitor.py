import logging
from datetime import datetime, timezone, timedelta

from backpack_client import BackpackClient
from config import AEST_OFFSET, BP_API_KEY, BP_API_SECRET

logger = logging.getLogger(__name__)

AEST = timezone(timedelta(hours=AEST_OFFSET))


def get_status(symbol: str = "BP_USDC") -> str:
    client = BackpackClient(BP_API_KEY, BP_API_SECRET)
    base_token = symbol.split("_")[0]
    now_aest = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")

    try:
        balances = client.get_balances()
        usdc = balances.get("USDC", {})
        bp = balances.get(base_token, {})
        usdc_total = float(usdc.get("total", 0))
        usdc_avail = float(usdc.get("available", 0))
        bp_total = float(bp.get("total", 0))
    except Exception as e:
        return f"❌ 잔고 조회 실패: {e}"

    last_price = 0.0
    best_bid: float | None = None
    best_ask: float | None = None
    try:
        last_price = client.get_last_price(symbol)
        best_bid, best_ask = client.get_best_bid_ask(symbol)
    except Exception as e:
        logger.warning(f"가격 조회 실패: {e}")

    bp_value = bp_total * last_price
    total_portfolio = usdc_total + bp_value

    lines = [
        f"📊 *BP DCA 현황* — {now_aest}",
        "━━━━━━━━━━━━━━",
        f"💵 USDC: `${usdc_total:.2f}` (가용: `${usdc_avail:.2f}`)",
        f"🎯 {base_token}: `{bp_total:.4f}` ≈ `${bp_value:.2f}`",
        f"📈 총 포트폴리오: `${total_portfolio:.2f}`",
        "",
        f"📉 *{symbol} 호가*",
        f"• 최근가: `${last_price:.4f}`",
    ]

    if best_bid and best_ask:
        spread_pct = (best_ask - best_bid) / best_ask * 100
        lines += [
            f"• 매수호가(Bid): `${best_bid:.4f}`",
            f"• 매도호가(Ask): `${best_ask:.4f}` (스프레드: `{spread_pct:.3f}%`)",
        ]

    return "\n".join(lines)
