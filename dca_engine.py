import logging
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backpack_client import BackpackClient
from config import (
    BP_API_KEY,
    BP_API_SECRET,
    MIN_USDC_BALANCE,
    ORDER_MAX_RETRIES,
    ORDER_PRICE_STEP_PCT,
    ORDER_RETRY_INTERVAL_SEC,
)
import state as st

logger = logging.getLogger(__name__)


class SkipReason(Enum):
    LOW_BALANCE = "잔고 부족"
    MARKET_ERROR = "시장 정보 조회 실패"
    NO_PRICE = "호가 데이터 없음"


@dataclass
class DCAResult:
    symbol: str
    target_usdc: float
    filled_usdc: float = 0.0
    filled_amount: float = 0.0
    avg_price: float = 0.0
    retries: int = 0
    skipped: bool = False
    skip_reason: Optional[SkipReason] = None
    usdc_balance_after: float = 0.0
    bp_balance_after: float = 0.0
    current_price: float = 0.0
    total_invested: float = 0.0
    total_bp: float = 0.0
    error: Optional[str] = None


def _decimals_from_step(step: str) -> int:
    if "." not in step:
        return 0
    return len(step.rstrip("0").split(".", 1)[1])


def _floor_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step


def execute_dca(symbol: str, target_usdc: float) -> DCAResult:
    client = BackpackClient(BP_API_KEY, BP_API_SECRET)
    result = DCAResult(symbol=symbol, target_usdc=target_usdc)
    base_token = symbol.split("_")[0]

    # --- 안전 체크: USDC 잔고 ---
    try:
        _, usdc_avail = client.get_usdc_balance()
    except Exception as e:
        result.skipped = True
        result.skip_reason = SkipReason.MARKET_ERROR
        result.error = f"잔고 조회 실패: {e}"
        return result

    if usdc_avail < MIN_USDC_BALANCE + target_usdc:
        result.skipped = True
        result.skip_reason = SkipReason.LOW_BALANCE
        result.error = (
            f"가용 USDC ${usdc_avail:.2f} < "
            f"최소 버퍼 ${MIN_USDC_BALANCE} + DCA ${target_usdc}"
        )
        return result

    # --- 마켓 정보 (틱 사이즈, 최소 수량) ---
    try:
        market = client.get_market_info(symbol)
        filters = market.get("filters", {})
        price_tick = filters.get("price", {}).get("tickSize", "0.0001")
        qty_step_str = filters.get("quantity", {}).get("stepSize", "0.01")
        min_qty = float(filters.get("quantity", {}).get("minQuantity", "0.01"))
        price_decimals = _decimals_from_step(price_tick)
        qty_step = float(qty_step_str)
        qty_decimals = _decimals_from_step(qty_step_str)
    except Exception as e:
        result.skipped = True
        result.skip_reason = SkipReason.MARKET_ERROR
        result.error = f"마켓 정보 조회 실패: {e}"
        return result

    # --- 초기 호가 조회 ---
    try:
        best_bid, best_ask = client.get_best_bid_ask(symbol)
        if best_bid is None and best_ask is None:
            result.skipped = True
            result.skip_reason = SkipReason.NO_PRICE
            result.error = "호가 데이터 없음"
            return result
        base_price = best_bid or best_ask
    except Exception as e:
        result.skipped = True
        result.skip_reason = SkipReason.MARKET_ERROR
        result.error = f"호가 조회 실패: {e}"
        return result

    # --- 가격 체이싱 DCA 루프 ---
    remaining_usdc = target_usdc
    total_filled_qty = 0.0
    total_filled_cost = 0.0

    for retry in range(ORDER_MAX_RETRIES):
        limit_price = round(base_price * (1 + retry * ORDER_PRICE_STEP_PCT / 100), price_decimals)

        qty = _floor_to_step(remaining_usdc / limit_price, qty_step)
        qty = round(qty, qty_decimals)

        if qty < min_qty:
            logger.info(f"수량 {qty} < 최소 {min_qty} — 종료")
            break

        price_str = f"{limit_price:.{price_decimals}f}"
        qty_str = f"{qty:.{qty_decimals}f}"
        client_id = (int(time.time() * 1000) + retry) % (2**31)

        logger.info(
            f"[시도 {retry + 1}/{ORDER_MAX_RETRIES}] {symbol} 매수 "
            f"{qty_str} @ {price_str} (남은: ${remaining_usdc:.2f})"
        )

        try:
            order = client.place_limit_order(symbol, "Bid", price_str, qty_str, client_id)
            order_id = str(order.get("id") or order.get("orderId", ""))
            if not order_id:
                result.error = f"주문 응답에 ID 없음: {order}"
                break
        except Exception as e:
            logger.error(f"주문 실패: {e}")
            result.error = str(e)
            break

        time.sleep(ORDER_RETRY_INTERVAL_SEC)

        # --- 주문 상태 확인 ---
        try:
            status_resp = client.get_order(symbol, order_id)
            status = status_resp.get("status", "")
            exec_qty = float(status_resp.get("executedQuantity", 0))
            exec_quote = float(status_resp.get("executedQuoteQuantity", 0))

            if exec_qty > 0:
                # executedQuoteQuantity가 없으면 limit_price로 추정
                avg_fill = exec_quote / exec_qty if exec_quote > 0 else limit_price
                total_filled_qty += exec_qty
                total_filled_cost += exec_qty * avg_fill
                remaining_usdc = max(0.0, remaining_usdc - exec_qty * avg_fill)
                result.retries = retry + 1
                logger.info(f"  체결: {exec_qty:.{qty_decimals}f} {base_token} @ ${avg_fill:.{price_decimals}f}")

            # 미체결 잔량 취소
            if status not in ("Filled",):
                client.cancel_order(symbol, order_id)

            if status == "Filled" or remaining_usdc < min_qty * limit_price:
                break

        except Exception as e:
            logger.error(f"주문 조회/취소 실패: {e}")
            try:
                client.cancel_order(symbol, order_id)
            except Exception:
                pass
            break

    # --- 최종 잔고 + 현재가 조회 ---
    try:
        _, usdc_after = client.get_usdc_balance()
        bp_total, _ = client.get_token_balance(base_token)
        result.usdc_balance_after = usdc_after
        result.bp_balance_after = bp_total
    except Exception:
        pass

    try:
        result.current_price = client.get_last_price(symbol)
    except Exception:
        pass

    if total_filled_qty > 0:
        result.filled_amount = total_filled_qty
        result.filled_usdc = total_filled_cost
        result.avg_price = total_filled_cost / total_filled_qty
        # 누적 cost basis 업데이트
        updated = st.update(total_filled_cost, total_filled_qty)
        result.total_invested = updated["total_invested_usdc"]
        result.total_bp = updated["total_bp_purchased"]
    else:
        result.error = result.error or "체결 없음"

    return result


def format_dca_notification(result: DCAResult) -> str:
    base_token = result.symbol.split("_")[0]

    if result.skipped:
        reason = result.skip_reason.value if result.skip_reason else "알 수 없음"
        return (
            f"⏭️ *DCA 건너뜀*\n"
            f"━━━━━━━━━━━━━━\n"
            f"• 심볼: `{result.symbol}`\n"
            f"• 이유: {reason}\n"
            f"• 상세: {result.error or ''}"
        )

    if result.filled_amount <= 0:
        return (
            f"❌ *DCA 실패*\n"
            f"━━━━━━━━━━━━━━\n"
            f"• 심볼: `{result.symbol}`\n"
            f"• 오류: {result.error or '체결 없음'}"
        )

    fill_pct = result.filled_usdc / result.target_usdc * 100 if result.target_usdc > 0 else 0
    status_emoji = "✅" if fill_pct >= 99 else "⚠️"

    cur = result.current_price or result.avg_price
    bp_value = result.bp_balance_after * cur
    total_value = result.usdc_balance_after + bp_value

    lines = [
        f"{status_emoji} *BP DCA 완료*",
        "━━━━━━━━━━━━━━",
        f"• 매수량: `{result.filled_amount:.4f} {base_token}`",
        f"• 평균가: `${result.avg_price:.4f}`",
        f"• 투자금: `${result.filled_usdc:.2f}` / `${result.target_usdc:.2f}`",
        f"• 체결률: `{fill_pct:.0f}%` (시도: {result.retries}회)",
        "",
        "💰 *잔고 현황*",
        f"• USDC: `${result.usdc_balance_after:.2f}`",
        f"• {base_token}: `{result.bp_balance_after:.4f}` @ `${cur:.4f}` = `${bp_value:.2f}`",
        f"• 총 포트폴리오: `${total_value:.2f}`",
    ]

    # 누적 PnL (state.json에 데이터 있을 때만)
    if result.total_bp > 0 and result.current_price > 0:
        avg_cost = result.total_invested / result.total_bp
        current_val = result.total_bp * result.current_price
        pnl = current_val - result.total_invested
        pnl_pct = pnl / result.total_invested * 100
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        lines += [
            "",
            f"{pnl_emoji} *누적 PnL*",
            f"• 총 투입: `${result.total_invested:.2f}`",
            f"• 현재 가치: `${current_val:.2f}`",
            f"• 평균 매수가: `${avg_cost:.4f}`",
            f"• 미실현 PnL: `{'%+.2f' % pnl}` (`{'%+.2f' % pnl_pct}%`)",
        ]

    return "\n".join(lines)
