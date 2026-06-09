import asyncio
import logging
from datetime import time as dt_time, timezone

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from config import (
    AEST_OFFSET,
    DCA_AMOUNT_USDC,
    DCA_SYMBOL,
    DCA_TIME_AEST,
    MIN_USDC_BALANCE,
    ORDER_MAX_RETRIES,
    ORDER_RETRY_INTERVAL_SEC,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TICKER_INTERVAL_SEC,
)
from dca_engine import execute_dca, format_dca_notification
from monitor import get_status, get_price_ticker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

OWNER_FILTER = filters.Chat(TELEGRAM_CHAT_ID)

_dca_running = False


def _aest_to_utc(hour: int, minute: int) -> tuple[int, int]:
    total_min = (hour * 60 + minute) - AEST_OFFSET * 60
    total_min = total_min % (24 * 60)
    return total_min // 60, total_min % 60


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    utc_h, utc_m = _aest_to_utc(*DCA_TIME_AEST)
    text = (
        f"🤖 *BP DCA Bot*\n"
        f"━━━━━━━━━━━━━━\n"
        f"• 심볼: `{DCA_SYMBOL}`\n"
        f"• DCA 금액: `${DCA_AMOUNT_USDC:.2f} USDC / 8시간`\n"
        f"• 첫 실행: `{DCA_TIME_AEST[0]:02d}:{DCA_TIME_AEST[1]:02d} AEST`"
        f" (UTC `{utc_h:02d}:{utc_m:02d}`)\n"
        f"\n📌 *명령어*\n"
        f"/status (또는 /s) — 잔고·가격·PnL 현황\n"
        f"/dca — 수동 DCA 즉시 실행\n"
        f"/config — 현재 설정 확인\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_status(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ 조회 중...", parse_mode="Markdown")
    status = await asyncio.to_thread(get_status, DCA_SYMBOL)
    await msg.edit_text(status, parse_mode="Markdown")


async def cmd_dca(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text(
        f"⏳ `{DCA_SYMBOL}` DCA 실행 중 (${DCA_AMOUNT_USDC:.2f} USDC)...",
        parse_mode="Markdown",
    )
    result = await asyncio.to_thread(execute_dca, DCA_SYMBOL, DCA_AMOUNT_USDC)
    await msg.edit_text(format_dca_notification(result), parse_mode="Markdown")


async def cmd_config(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    utc_h, utc_m = _aest_to_utc(*DCA_TIME_AEST)
    text = (
        f"⚙️ *현재 설정*\n"
        f"━━━━━━━━━━━━━━\n"
        f"• 심볼: `{DCA_SYMBOL}`\n"
        f"• DCA 금액: `${DCA_AMOUNT_USDC:.2f} USDC / 8시간`\n"
        f"• 실행 시각: `{DCA_TIME_AEST[0]:02d}:{DCA_TIME_AEST[1]:02d} AEST`"
        f" (UTC `{utc_h:02d}:{utc_m:02d}`)\n"
        f"• 최소 USDC 버퍼: `${MIN_USDC_BALANCE:.2f}`\n"
        f"• 최대 재시도: `{ORDER_MAX_RETRIES}회`\n"
        f"• 재시도 간격: `{ORDER_RETRY_INTERVAL_SEC}초`\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def job_dca(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    global _dca_running
    logger.info(f"스케줄 DCA 실행: {DCA_SYMBOL} ${DCA_AMOUNT_USDC}")
    _dca_running = True
    try:
        result = await asyncio.to_thread(execute_dca, DCA_SYMBOL, DCA_AMOUNT_USDC)
    finally:
        _dca_running = False
    await ctx.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=format_dca_notification(result),
        parse_mode="Markdown",
    )


async def job_price_ticker(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if _dca_running:
        logger.info("DCA 진행 중 — 가격 티커 스킵")
        return
    try:
        text = await asyncio.to_thread(get_price_ticker, DCA_SYMBOL)
        await ctx.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"가격 티커 전송 실패: {e}")


def main() -> None:
    async def post_init(application: Application) -> None:
        commands = [
            BotCommand("s", "잔고·가격·PnL 현황"),
            BotCommand("dca", "수동 DCA 즉시 실행"),
            BotCommand("config", "현재 설정 확인"),
            BotCommand("start", "봇 정보 및 명령어 목록"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info(f"Telegram 명령어 등록 완료: {[c.command for c in commands]}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status, filters=OWNER_FILTER))
    app.add_handler(CommandHandler("s", cmd_status, filters=OWNER_FILTER))
    app.add_handler(CommandHandler("dca", cmd_dca, filters=OWNER_FILTER))
    app.add_handler(CommandHandler("config", cmd_config, filters=OWNER_FILTER))

    utc_h, utc_m = _aest_to_utc(*DCA_TIME_AEST)
    app.job_queue.run_repeating(
        job_dca,
        interval=8 * 3600,
        first=dt_time(utc_h, utc_m, tzinfo=timezone.utc),
        name="interval_dca",
    )
    logger.info(
        f"DCA 스케줄 등록: 8시간마다 (첫 실행 {DCA_TIME_AEST[0]:02d}:{DCA_TIME_AEST[1]:02d} AEST"
        f" / UTC {utc_h:02d}:{utc_m:02d})"
    )

    app.job_queue.run_repeating(
        job_price_ticker,
        interval=TICKER_INTERVAL_SEC,
        first=TICKER_INTERVAL_SEC,
        name="price_ticker",
    )
    logger.info(f"가격 티커 스케줄 등록: {TICKER_INTERVAL_SEC}초 간격")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
