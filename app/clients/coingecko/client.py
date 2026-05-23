from __future__ import annotations

import asyncio
import logging

import httpx

from app.clients._shared.errors import log_api_error, log_key_status
from app.clients.coingecko.models import MacroSnapshot
from core import settings

logger = logging.getLogger(__name__)

_SERVICE = "CoinGecko"
_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """Клиент CoinGecko для макро-данных. Использовать как async context manager.

    API key опционален: без него работает с публичными лимитами. С ключом
    добавляется заголовок x-cg-demo-api-key для повышенных лимитов demo-тарифа.
    """

    def __init__(self) -> None:
        log_key_status(_SERVICE, settings.COINGECKO_API_KEY, optional=True)
        headers: dict[str, str] = {"accept": "application/json"}
        if settings.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL, headers=headers, timeout=settings.HTTP_TIMEOUT_S
        )

    async def __aenter__(self) -> CoinGeckoClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    async def fetch_macro_snapshot(self) -> MacroSnapshot:
        """Снимок макро-рынка: BTC доминация, цена и изменения за 24h/7d.

        Использует /coins/markets для BTC (там есть 7d через price_change_percentage),
        т.к. /simple/price не поддерживает 7d-изменение.
        """
        try:
            global_resp, markets_resp = await asyncio.gather(
                self._http.get("/global"),
                self._http.get(
                    "/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "ids": "bitcoin",
                        "price_change_percentage": "24h,7d",
                    },
                ),
            )
            global_resp.raise_for_status()
            markets_resp.raise_for_status()
        except httpx.HTTPError as exc:
            log_api_error(_SERVICE, exc, path="/global+/coins/markets")
            raise

        gdata = global_resp.json()["data"]
        mdata = markets_resp.json()[0]

        return MacroSnapshot(
            btc_dominance=float(gdata["market_cap_percentage"]["btc"]),
            btc_price_usd=float(mdata["current_price"]),
            btc_change_24h=float(mdata.get("price_change_percentage_24h") or 0.0),
            btc_change_7d=float(
                mdata.get("price_change_percentage_7d_in_currency") or 0.0
            ),
            total_market_cap_change_24h=float(
                gdata.get("market_cap_change_percentage_24h_usd") or 0.0
            ),
        )
