"""MersennetOrders - CLOB interaction for Mersennet."""

from typing import List, Optional

from .provider import MersennetProvider
from .types import Order, OrderBook, OrderBookLevel, Trade


def _to_hex_amount(s: str) -> str:
    if s.startswith("0x"):
        return s
    return hex(int(s))


class MersennetOrders:
    """High-level API for Mersennet order book operations."""

    def __init__(self, provider: MersennetProvider):
        self.provider = provider

    # Markets are seeded deterministically from the node's genesis config; the
    # unsigned addMarket RPC was removed (it only mutated one node's state).

    _SIGNED_ORDER_MSG = (
        "Orders are now signed transactions to the CLOB precompile "
        "(0x0000000000000000000000000000000000000100). The unsigned "
        "owner-field RPC was removed for security (it let anyone trade as "
        "anyone). Build a placeOrder/cancelOrder/depositCollateral/"
        "withdrawCollateral call, sign it (e.g. with eth-account), and submit "
        "via provider.send_raw_transaction(). Native signing helpers for the "
        "Python SDK are a tracked follow-up; the TypeScript SDK "
        "(MersennetOrders + TxSigner) is the reference implementation."
    )

    def place_order(
        self,
        market: int,
        side: str,
        price: str,
        amount: str,
        tif: str = "gtc",
        owner: Optional[str] = None,
    ) -> dict:
        """Deprecated: use a signed tx to the precompile (see message)."""
        raise NotImplementedError(self._SIGNED_ORDER_MSG)

    def cancel_order(self, order_id: int) -> bool:
        """Deprecated: use a signed cancelOrder tx to the precompile."""
        raise NotImplementedError(self._SIGNED_ORDER_MSG)

    def get_order_book(self, market: int) -> OrderBook:
        """Get order book for a market."""
        result = self.provider._request("mersennet_orders_getOrderBook", [
            hex(market),
        ])
        if result is None:
            return OrderBook(bids=[], asks=[])
        bids = [
            OrderBookLevel(price=str(l.get("price", "0x0")), size=str(l.get("size", "0x0")))
            for l in result.get("bids", [])
        ]
        asks = [
            OrderBookLevel(price=str(l.get("price", "0x0")), size=str(l.get("size", "0x0")))
            for l in result.get("asks", [])
        ]
        return OrderBook(bids=bids, asks=asks)

    def get_trades(self, market: int) -> List[Trade]:
        """Get recent trades for a market (via domain events or RPC if available)."""
        result = self.provider._request("mersennet_getDomainEvents", [{
            "domain": "mersennet_orders",
            "kind": "trade",
        }])
        if not result or not isinstance(result, list):
            return []
        trades = []
        for evt in result:
            data = evt.get("data", {}) if isinstance(evt, dict) else {}
            if str(data.get("market_id", "")) == hex(market):
                trades.append(Trade(
                    taker=str(data.get("taker", "")),
                    maker=str(data.get("maker", "")),
                    market_id=str(data.get("market_id", "")),
                    side=str(data.get("side", "buy")),
                    price=str(data.get("price", "0x0")),
                    size=str(data.get("size", "0x0")),
                ))
        return trades

    def get_positions(self, address: str, market: Optional[int] = None) -> dict:
        """Get positions for address. Uses precompile if available."""
        if market is not None:
            data = "0x" + "0" * 24 + hex(market)[2:].zfill(64)
            result = self.provider.call({
                "from": address,
                "to": "0x0000000000000000000000000000000000000100",
                "data": data,
            })
            if result and result != "0x":
                return {"market": market, "raw": result}
        return {}

    # ------------------------------------------------------------------
    # Protocol parameters, markets, price scale, agents, liquidations
    # ------------------------------------------------------------------

    def get_protocol(self) -> dict:
        """Every CLOB consensus switch and live parameter (`mersennet_orders_getProtocol`):
        margin bps, wei per collateral unit, insurance fund, bad debt, market price scales."""
        return self.provider._request("mersennet_orders_getProtocol", []) or {}

    def collateral_units_per_mrsn(self) -> int:
        """Collateral units per MRSN in the current era: 10**18 before the settlement
        switch (a unit was one wei) and 1 from it (a unit is one MRSN). Read from
        ``get_protocol()['weiPerCollateralUnit']`` so callers never depend on the height."""
        raw = self.get_protocol().get("weiPerCollateralUnit", 1)
        try:
            wei = int(str(raw), 0)
        except (TypeError, ValueError):
            wei = 1
        return 10**18 // (wei if wei > 0 else 1)

    def to_collateral_units(self, mrsn) -> int:
        """Human MRSN amount ("10.5", 10, Decimal) -> integer collateral units for the
        current era (floor). Pass the result to ``depositCollateral``/``withdrawCollateral``."""
        from decimal import Decimal
        wei = int(Decimal(str(mrsn)) * Decimal(10**18))
        if wei <= 0:
            raise ValueError(f"invalid MRSN amount: {mrsn}")
        return wei // (10**18 // self.collateral_units_per_mrsn())

    def get_markets(self) -> List[dict]:
        """Listed markets with tick/lot sizes and ``priceScale``
        (on-chain price = human price × priceScale; 1 = integer prices)."""
        raw = self.provider._request("mersennet_orders_getMarkets", []) or []
        out = []
        for m in raw:
            out.append({
                "id": int(m.get("id", 0)),
                "symbol": str(m.get("symbol", "")),
                "tick_size": int(str(m.get("tickSize", "0x1")), 16) if str(m.get("tickSize", "0x1")).startswith("0x") else int(m.get("tickSize", 1)),
                "lot_size": int(str(m.get("lotSize", "0x1")), 16) if str(m.get("lotSize", "0x1")).startswith("0x") else int(m.get("lotSize", 1)),
                "last_price": int(str(m.get("lastPrice", "0x0")), 16) if str(m.get("lastPrice", "0x0")).startswith("0x") else int(m.get("lastPrice", 0)),
                "price_scale": int(m.get("priceScale", 1) or 1),
                "status": str(m.get("status", "active")),
            })
        return out

    @staticmethod
    def to_chain_price(human: float, price_scale: int) -> int:
        """Human price → on-chain price (rounded to the nearest unit)."""
        return int(round(float(human) * (price_scale or 1)))

    @staticmethod
    def to_human_price(chain: int, price_scale: int) -> float:
        """On-chain price → human price."""
        return int(chain) / (price_scale or 1)

    def get_agents(self, owner: str) -> dict:
        """Agent keys granted by ``owner`` and whether delegation is active (`mersennet_orders_getAgents`)."""
        return self.provider._request("mersennet_orders_getAgents", [owner]) or {}

    def get_liquidatable(self) -> List[str]:
        """Accounts below maintenance margin at the head (keeper feed; empty before the settlement switch)."""
        r = self.provider._request("mersennet_orders_getLiquidatable", []) or {}
        return list(r.get("accounts", []))
