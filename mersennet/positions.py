"""Client-side open-order and position reconstruction (Workstream F5,
``orders:read`` / ``positions:read``).

On a fully shielded chain the node never sees order/position plaintext, so a
wallet reconstructs its own trading state locally from material it already
holds:

  - ``OrderRecord`` s it created when it submitted each shielded order (it
    knows side/price/size/market because it authored the intent), and
  - ``FillRecord`` s it derived by matching its orders against the public
    frequent-batch-auction clearing events.

These helpers are pure and deterministic. Faithful port of
``sdk-ts/src/positions.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

OrderSide = str  # 'buy' | 'sell'


@dataclass
class OrderRecord:
    """An order the wallet submitted, as it recorded it at submit time."""

    order_id: str
    market_id: int
    side: OrderSide
    price: int
    size: int
    status: Optional[str] = None  # 'open' | 'cancelled'


@dataclass
class FillRecord:
    """A fill the wallet attributed to one of its orders from public clearing."""

    order_id: str
    market_id: int
    side: OrderSide
    price: int
    size: int


@dataclass
class OpenOrder:
    order_id: str
    market_id: int
    side: OrderSide
    price: int
    remaining: int


@dataclass
class ReconstructedPosition:
    market_id: int
    net_size: int  # signed: positive = long, negative = short, 0 = flat
    entry_price: int  # size-weighted average entry of open exposure
    realized_pnl: int


def _sum_filled_by_order(fills: List[FillRecord]) -> Dict[str, int]:
    filled: Dict[str, int] = {}
    for f in fills:
        if f.size < 0:
            raise ValueError(f"fill size must be non-negative (order {f.order_id})")
        filled[f.order_id] = filled.get(f.order_id, 0) + f.size
    return filled


def reconstruct_open_orders(
    orders: List[OrderRecord],
    fills: Optional[List[FillRecord]] = None,
) -> List[OpenOrder]:
    """Reconstruct the wallet's still-open orders: every non-cancelled order
    whose filled size is below its original size, with the unfilled remainder
    reported."""
    fills = fills or []
    filled = _sum_filled_by_order(fills)

    open_orders: List[OpenOrder] = []
    for order in orders:
        if order.status == "cancelled":
            continue
        if order.size < 0:
            raise ValueError(f"order size must be non-negative (order {order.order_id})")
        done = filled.get(order.order_id, 0)
        remaining = order.size - done
        if remaining > 0:
            open_orders.append(
                OpenOrder(
                    order_id=order.order_id,
                    market_id=order.market_id,
                    side=order.side,
                    price=order.price,
                    remaining=remaining,
                )
            )
    return open_orders


class _MutablePosition:
    __slots__ = ("net_size", "entry_price", "realized_pnl")

    def __init__(self) -> None:
        self.net_size = 0
        self.entry_price = 0
        self.realized_pnl = 0


def _apply_fill(pos: _MutablePosition, signed_size: int, price: int) -> None:
    """Apply one signed fill using average-cost accounting. Increasing
    exposure updates the weighted entry price; reducing or flipping realizes
    PnL on the closed portion."""
    same_direction = pos.net_size == 0 or (pos.net_size > 0) == (signed_size > 0)

    if same_direction:
        new_net = pos.net_size + signed_size
        prev_abs = abs(pos.net_size)
        add_abs = abs(signed_size)
        total_abs = prev_abs + add_abs
        pos.entry_price = (
            0
            if total_abs == 0
            else (pos.entry_price * prev_abs + price * add_abs) // total_abs
        )
        pos.net_size = new_net
        return

    # Opposite direction: close against existing exposure first.
    closing_abs = abs(signed_size)
    open_abs = abs(pos.net_size)
    matched = min(closing_abs, open_abs)

    was_long = pos.net_size > 0
    pnl = (price - pos.entry_price) * matched if was_long else (pos.entry_price - price) * matched
    pos.realized_pnl += pnl

    remainder_abs = closing_abs - matched
    pos.net_size = pos.net_size + signed_size

    if pos.net_size == 0:
        pos.entry_price = 0
    elif remainder_abs > 0:
        # Position flipped; leftover opens new exposure at the fill price.
        pos.entry_price = price
    # If it only reduced (remainder_abs == 0 and net_size != 0), the entry
    # price of the remaining open exposure is unchanged.


def reconstruct_positions(fills: Optional[List[FillRecord]] = None) -> List[ReconstructedPosition]:
    """Reconstruct per-market positions from fills using average-cost
    accounting. Fills are applied in list order, so pass them chronologically
    for correct realized-PnL attribution."""
    fills = fills or []
    by_market: Dict[int, _MutablePosition] = {}

    for f in fills:
        if f.size < 0:
            raise ValueError(f"fill size must be non-negative (order {f.order_id})")
        pos = by_market.get(f.market_id)
        if pos is None:
            pos = _MutablePosition()
            by_market[f.market_id] = pos
        signed = f.size if f.side == "buy" else -f.size
        _apply_fill(pos, signed, f.price)

    return [
        ReconstructedPosition(
            market_id=market_id,
            net_size=pos.net_size,
            entry_price=pos.entry_price,
            realized_pnl=pos.realized_pnl,
        )
        for market_id, pos in sorted(by_market.items())
    ]
