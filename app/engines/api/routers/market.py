import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.engines.api.deps import get_ccxt
from app.engines.api.models import LiquidityMapOut, SymbolOut
from app.engines.api.symbols import API_BASES, ccxt_symbol, display_symbol
from app.adapters.clients.ccxt.client import CcxtClient
from app.services.liquidity.builder import build_liquidity_map
from core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["market"])

_LIQUIDITY_CANDLE_TIMEFRAME = "4h"


@router.get("/symbols", response_model=list[SymbolOut])
async def list_symbols(ccxt_client: CcxtClient = Depends(get_ccxt)) -> list[SymbolOut]:
    """Каталог торгуемых символов с актуальной mark-ценой (один fetch_tickers)."""
    ccxt_symbols = [ccxt_symbol(base) for base in API_BASES]
    prices = await ccxt_client.fetch_last_prices(ccxt_symbols)
    return [
        SymbolOut(
            symbol=display_symbol(base),
            base=base,
            mark_price=prices.get(ccxt_symbol(base), 0.0),
        )
        for base in API_BASES
    ]


@router.get("/liquidity/{base}", response_model=LiquidityMapOut)
async def get_liquidity(
    base: str, ccxt_client: CcxtClient = Depends(get_ccxt)
) -> LiquidityMapOut:
    """Живая карта ликвидности символа: тянет 4h-свечи и стакан, считает карту.

    Стакан нефатален (сбой → карта без стен). Пустые свечи → 404.
    """
    normalized = base.upper()
    if normalized not in API_BASES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown symbol {base}"
        )
    symbol = ccxt_symbol(normalized)
    candles = await ccxt_client.fetch_ohlcv(
        symbol, _LIQUIDITY_CANDLE_TIMEFRAME, limit=settings.LIQUIDITY_PROFILE_WINDOW
    )
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no candles for {base}"
        )
    order_book = None
    try:
        order_book = await ccxt_client.fetch_order_book(symbol)
    except Exception:
        logger.warning("order book fetch failed for %s", symbol, exc_info=True)
    domain = build_liquidity_map(
        symbol=symbol,
        mark_price=candles[-1].close,
        candles=candles,
        order_book=order_book,
    )
    return LiquidityMapOut.from_domain(domain)
