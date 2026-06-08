import base64
import time
from typing import Optional, Tuple

import httpx
import nacl.signing

BASE_URL = "https://api.backpack.exchange"


class BackpackClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self._signing_key = nacl.signing.SigningKey(base64.b64decode(api_secret))

    def _sign(self, instruction: str, params: dict, window: int = 5000) -> Tuple[str, int]:
        ts = int(time.time() * 1000)
        parts = [f"instruction={instruction}"]
        if params:
            parts.append("&".join(f"{k}={params[k]}" for k in sorted(params)))
        parts.append(f"timestamp={ts}")
        parts.append(f"window={window}")
        sig = base64.b64encode(
            self._signing_key.sign("&".join(parts).encode()).signature
        ).decode()
        return sig, ts

    def _auth_headers(self, instruction: str, params: dict = None) -> dict:
        sig, ts = self._sign(instruction, params or {})
        return {
            "X-API-Key": self.api_key,
            "X-Signature": sig,
            "X-Timestamp": str(ts),
            "X-Window": "5000",
            "Content-Type": "application/json; charset=utf-8",
        }

    def get_balances(self) -> dict:
        resp = httpx.get(
            f"{BASE_URL}/api/v1/capital",
            headers=self._auth_headers("balanceQuery"),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_usdc_balance(self) -> Tuple[float, float]:
        """Returns (total, available) USDC via collateral endpoint.
        Backpack auto-uses lending balance for spot trades, so totalQuantity
        is the real tradeable amount regardless of availableQuantity."""
        resp = httpx.get(
            f"{BASE_URL}/api/v1/capital/collateral",
            headers=self._auth_headers("collateralQuery"),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        for entry in data.get("collateral", []):
            if entry.get("symbol") == "USDC":
                total = float(entry.get("totalQuantity", 0))
                avail = float(entry.get("availableQuantity", 0))
                # lending balance counts as spendable — use total
                return total, total
        return 0.0, 0.0

    def get_token_balance(self, token: str) -> Tuple[float, float]:
        """Returns (total, available) for given token. total = available + locked + staked."""
        data = self.get_balances()
        tok = data.get(token, {})
        avail = float(tok.get("available", 0))
        total = avail + float(tok.get("locked", 0)) + float(tok.get("staked", 0))
        return total, avail

    def get_orderbook(self, symbol: str) -> dict:
        resp = httpx.get(
            f"{BASE_URL}/api/v1/depth",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_best_bid_ask(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        ob = self.get_orderbook(symbol)
        # Backpack returns bids ascending (best bid = last element)
        # asks ascending (best ask = first element)
        best_bid = float(ob["bids"][-1][0]) if ob.get("bids") else None
        best_ask = float(ob["asks"][0][0]) if ob.get("asks") else None
        return best_bid, best_ask

    def get_ticker(self, symbol: str) -> dict:
        resp = httpx.get(
            f"{BASE_URL}/api/v1/ticker",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_last_price(self, symbol: str) -> float:
        return float(self.get_ticker(symbol).get("lastPrice", 0))

    def get_market_info(self, symbol: str) -> dict:
        resp = httpx.get(f"{BASE_URL}/api/v1/markets", timeout=10)
        resp.raise_for_status()
        for m in resp.json():
            if m.get("symbol") == symbol:
                return m
        raise ValueError(f"Symbol {symbol} not found on Backpack")

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        client_id: Optional[int] = None,
    ) -> dict:
        """side: 'Bid' (buy) or 'Ask' (sell)."""
        # Sign only core order fields, matching backpackModule.js openOrder pattern
        sig_params = {
            "orderType": "Limit",
            "price": price,
            "quantity": quantity,
            "side": side,
            "symbol": symbol,
        }
        headers = self._auth_headers("orderExecute", sig_params)
        body: dict = dict(sig_params)
        if client_id is not None:
            body["clientId"] = client_id
        resp = httpx.post(f"{BASE_URL}/api/v1/order", headers=headers, json=body, timeout=10)
        if not resp.is_success:
            raise ValueError(f"주문 실패 {resp.status_code}: {resp.text}")
        return resp.json()

    def get_order(self, symbol: str, order_id: str) -> dict:
        params = {"orderId": order_id, "symbol": symbol}
        resp = httpx.get(
            f"{BASE_URL}/api/v1/order",
            headers=self._auth_headers("orderQuery", params),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        body = {"orderId": order_id, "symbol": symbol}
        headers = self._auth_headers("orderCancel", {k: str(v) for k, v in body.items()})
        resp = httpx.request("DELETE", f"{BASE_URL}/api/v1/order", headers=headers, json=body, timeout=10)
        return resp.status_code < 300
