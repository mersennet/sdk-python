"""Type definitions for Mersennet SDK."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Log:
    """Event log entry from a receipt or eth_getLogs."""

    address: str
    topics: List[str]
    data: str
    block_number: str
    block_hash: str
    transaction_hash: str
    transaction_index: str
    log_index: str
    removed: bool = False


@dataclass
class Transaction:
    """Transaction data."""

    hash: str
    from_: str
    to: Optional[str]
    value: str
    nonce: str
    gas: str
    gas_price: str
    input: str
    block_hash: Optional[str] = None
    block_number: Optional[str] = None
    transaction_index: Optional[str] = None
    type: Optional[str] = None
    v: Optional[str] = None
    r: Optional[str] = None
    s: Optional[str] = None
    chain_id: Optional[str] = None


@dataclass
class Receipt:
    """Transaction receipt."""

    transaction_hash: str
    block_hash: str
    block_number: str
    transaction_index: str
    from_: str
    to: Optional[str]
    gas_used: str
    cumulative_gas_used: str
    effective_gas_price: str
    status: str
    contract_address: Optional[str]
    logs_bloom: str
    type: Optional[str]
    logs: List[Log] = field(default_factory=list)


@dataclass
class Block:
    """Block data from eth_getBlockByNumber / eth_getBlockByHash."""

    number: str
    hash: str
    parent_hash: str
    nonce: str
    sha3_uncles: str
    logs_bloom: str
    transactions_root: str
    state_root: str
    receipts_root: str
    miner: str
    proposer: str
    difficulty: str
    total_difficulty: str
    extra_data: str
    size: str
    gas_limit: str
    gas_used: str
    base_fee: str
    timestamp: str
    transactions: List = field(default_factory=list)
    uncles: List = field(default_factory=list)
    mix_hash: str = "0x0"
    domain_events: Optional[List] = None


@dataclass
class Order:
    """Order in the order book or open orders list."""

    id: str
    owner: str
    market_id: str
    side: str  # 'buy' | 'sell'
    price: str
    size: str
    tif: str  # 'gtc' | 'ioc' | 'fok'


@dataclass
class OrderBookLevel:
    """Order book level."""

    price: str
    size: str


@dataclass
class OrderBook:
    """Full order book snapshot."""

    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]


@dataclass
class Trade:
    """Trade execution record."""

    taker: str
    maker: str
    market_id: str
    side: str
    price: str
    size: str


@dataclass
class ViewNotesEntry:
    """Single encrypted note entry returned by mersennet_viewNotes."""

    note_commitment: str
    encrypted_note: str


@dataclass
class ViewNotesResult:
    """Grant-gated encrypted note export returned by mersennet_viewNotes."""

    grant_id: str
    grantor_commitment: str
    block_number: int
    shielded_state_root: str
    total_encrypted_note_count: int
    returned_encrypted_note_count: int
    next_cursor: Optional[str]
    notes: List[ViewNotesEntry]
    signature_verified: bool


@dataclass
class ViewBalancesResult:
    """Grant-gated (``balances:read``) balance-reconstruction page returned by
    mersennet_viewBalances. Pair with ``reconstruct_portfolio``."""

    grant_id: str
    grantor_commitment: str
    block_number: int
    shielded_state_root: str
    total_encrypted_note_count: int
    returned_encrypted_note_count: int
    next_cursor: Optional[str]
    notes: List[ViewNotesEntry]
    spent_nullifiers: List[str]
    spent_nullifier_count: int
    reconstruction: str
    signature_verified: bool


@dataclass
class ViewMarketAggregate:
    """Public per-market aggregate returned in trading view reads."""

    market_id: int
    mark_price: str = "0x0"
    long_open_interest: str = "0x0"
    short_open_interest: str = "0x0"
    last_clearing_price: str = "0x0"
    last_volume: str = "0x0"
    liquidatable_count: int = 0


@dataclass
class ViewTradingResult:
    """Grant-gated (``orders:read`` / ``positions:read``) read. Returns the
    public market context + grant binding only - order/position rows are
    reconstructed client-side."""

    grant_id: str
    grantor_commitment: str
    block_number: int
    shielded_state_root: str
    market_aggregates: List[ViewMarketAggregate]
    reconstruction: str
    signature_verified: bool


@dataclass
class ViewGrantStatus:
    """Status of a viewing grant (mersennet_viewGrantStatus)."""

    exists: bool
    status: str
    active_now: bool
    signature_verified: bool
    revoked: bool
    revoked_at_block: Optional[int] = None
    grant_token: Optional[dict] = None
