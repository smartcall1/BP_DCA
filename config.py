import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])

BP_API_KEY: str = os.environ["BP_API_KEY"]
BP_API_SECRET: str = os.environ["BP_API_SECRET"]

DCA_SYMBOL: str = os.getenv("DCA_SYMBOL", "BP_USDC")
DCA_AMOUNT_USDC: float = float(os.environ["DCA_AMOUNT_USDC"])

_t = os.getenv("DCA_TIME_AEST", "09:00").split(":")
DCA_TIME_AEST: tuple[int, int] = (int(_t[0]), int(_t[1]))

MIN_USDC_BALANCE: float = float(os.getenv("MIN_USDC_BALANCE", "20.0"))

ORDER_RETRY_INTERVAL_SEC: int = int(os.getenv("ORDER_RETRY_INTERVAL_SEC", "30"))
ORDER_PRICE_STEP_PCT: float = float(os.getenv("ORDER_PRICE_STEP_PCT", "0.1"))
ORDER_MAX_RETRIES: int = int(os.getenv("ORDER_MAX_RETRIES", "10"))

TICKER_INTERVAL_SEC: int = int(os.getenv("TICKER_INTERVAL_SEC", "180"))

AEST_OFFSET: int = 10
