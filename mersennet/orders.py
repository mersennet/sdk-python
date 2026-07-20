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
