<p align="center"><a href="https://mersennet.com"><img src="https://raw.githubusercontent.com/mersennet/.github/main/profile/mark.svg" width="72" alt="Mersennet"></a></p>
<h1 align="center">Mersennet Python SDK</h1>
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-7dff9b?style=flat-square" alt="MIT license"></a>
  <a href="https://github.com/mersennet/sdk-python/actions/workflows/ci.yml"><img src="https://github.com/mersennet/sdk-python/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://docs.mersennet.com/developers/sdks/python/"><img src="https://img.shields.io/badge/docs-mersennet-1c1c1c?style=flat-square" alt="Docs"></a>
  <a href="https://t.me/Mersennet"><img src="https://img.shields.io/badge/telegram-%40Mersennet-26A5E4?style=flat-square" alt="Telegram"></a>
</p>

Python client for Mersennet - JSON-RPC, CLOB (order book), and WebSocket subscriptions.

## Installation

```bash
pip install "git+https://github.com/mersennet/sdk-python.git@v0.1.0"   # PyPI publication pending
```

Or from source:

```bash
cd sdk-python
pip install -e .
```

## Quick Start

```python
from mersennet import MersennetProvider, MersennetOrders

provider = MersennetProvider("http://localhost:8545")

# Chain info
print("Chain ID:", provider.chain_id())
print("Block:", provider.block_number())
print("Gas price:", provider.gas_price())

# Account
balance = provider.get_balance("0xYourAddress")
print("Balance:", balance)

# Order book
orders = MersennetOrders(provider)
book = orders.get_order_book(1)
print("Bids:", book.bids)
print("Asks:", book.asks)
```

## API Reference

### MersennetProvider

| Method | Description |
|--------|-------------|
| `get_block(number, include_txs)` | Get block by number or "latest" |
| `get_block_by_hash(hash, include_txs)` | Get block by hash |
| `get_transaction(hash)` | Get transaction by hash |
| `get_balance(address)` | Get balance (hex string) |
| `get_nonce(address)` | Get nonce |
| `send_raw_transaction(raw_tx)` | Send signed transaction |
| `call(tx_object)` | Simulate call (eth_call) |
| `chain_id()` | Chain ID |
| `block_number()` | Latest block number |
| `view_notes(grant_id_hex, limit, cursor_hex)` | Grant-gated encrypted note export |
| `gas_price()` | Current gas price |

### MersennetOrders

| Method | Description |
|--------|-------------|
| `add_market(base, quote, lot, tick)` | Add market (admin) |
| `place_order(market, side, price, amount, tif, owner)` | Place order |
| `cancel_order(order_id)` | Cancel order |
| `get_order_book(market)` | Get order book |
| `get_trades(market)` | Get recent trades |
| `get_positions(address, market)` | Get positions |

### MersennetSubscriber (WebSocket)

| Method | Description |
|--------|-------------|
| `connect()` | Connect to WebSocket |
| `disconnect()` | Disconnect |
| `subscribe_blocks(callback)` | Subscribe to new blocks |
| `subscribe_trades(market, callback)` | Subscribe to trades |
| `subscribe_logs(callback, topics, address)` | Subscribe to logs |
| `unsubscribe(id)` | Unsubscribe |

### Shielded Notes

Use `view_notes` to fetch encrypted note envelopes, then call
`scan_granted_notes` with a decrypt function that applies your granted
viewing material locally.

```python
from mersennet import GrantedViewingMaterial, MersennetProvider, make_mock_note_decryptor, scan_granted_notes

provider = MersennetProvider("http://localhost:8545")

material = GrantedViewingMaterial(
    grant_id_hex="0x...",
    recipient_public_key="0x...",
    decrypt_note_ciphertext=make_mock_note_decryptor("0x..."),
)

result = scan_granted_notes(provider, material, limit=64)
print("Decrypted notes:", len(result.notes))
```

See the runnable end-to-end example in [examples/view_notes_end_to_end.py](examples/view_notes_end_to_end.py).

## WebSocket Example

```python
from mersennet import MersennetSubscriber

sub = MersennetSubscriber("ws://localhost:8545")
sub.connect()

def on_block(block):
    print("New block:", block)

sub_id = sub.subscribe_blocks(on_block)
# ...
sub.unsubscribe(sub_id)
sub.disconnect()
```

## Error Handling

```python
from mersennet.provider import MersennetError

try:
    balance = provider.get_balance("0x...")
except MersennetError as e:
    print(f"Error {e.code}: {e}")
```

---

<p align="center">
  Part of the <a href="https://github.com/mersennet">Mersennet</a> ecosystem —
  <a href="https://trade.mersennet.com">trade</a> ·
  <a href="https://explorer.mersennet.com">explorer</a> ·
  <a href="https://docs.mersennet.com">docs</a> ·
  <a href="https://mersennet.com/downloads/">run a node</a> ·
  <a href="https://t.me/Mersennet">Telegram</a><br>
  <sub>© 2026 Mersennet Foundation · MIT License · security@mersennet.com</sub>
</p>
