"""MersennetProvider - JSON-RPC client for Mersennet."""

import json
from typing import Any, Dict, Optional

try:
    import requests
    _USE_REQUESTS = True
except ImportError:
    _USE_REQUESTS = False

from .types import (
    Block,
    Log,
    Receipt,
    Transaction,
    ViewNotesEntry,
    ViewNotesResult,
)


class MersennetError(Exception):
    """Mersennet RPC or SDK error."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def _hex_to_number(hex_str: str) -> int:
    s = hex_str[2:] if hex_str.startswith("0x") else hex_str
    return int(s, 16)


def _hex_to_string(hex_str: str) -> str:
    s = hex_str[2:] if hex_str.startswith("0x") else hex_str
    if not s or s == "0":
        return "0x0"
    return "0x" + s.lower()


class MersennetProvider:
    """Mersennet JSON-RPC provider. Connects to the RPC endpoint via HTTP."""

    def __init__(self, rpc_url: str):
        self.url = rpc_url
        self._id = 0

    def _request(self, method: str, params: Optional[list] = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or [],
        }
        try:
            if _USE_REQUESTS:
                resp = requests.post(
                    self.url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            else:
                import urllib.request
                import urllib.error
                body = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
        except Exception as e:
            raise MersennetError(str(e))

        if "error" in data:
            err = data["error"]
            raise MersennetError(
                err.get("message", "Unknown RPC error"),
                code=err.get("code"),
            )
        return data.get("result")

    def get_block(self, number: int | str, include_txs: bool = False) -> Optional[Block]:
        """Get block by number. Use 'latest' for latest block."""
        tag = "latest" if number == "latest" else hex(number)
        result = self._request("eth_getBlockByNumber", [tag, include_txs])
        if result is None:
            return None
        return self._parse_block(result)

    def get_block_by_hash(self, hash: str, include_txs: bool = False) -> Optional[Block]:
        """Get block by hash."""
        result = self._request("eth_getBlockByHash", [hash, include_txs])
        if result is None:
            return None
        return self._parse_block(result)

    def _parse_block(self, obj: Dict) -> Block:
        raw_txs = obj.get("transactions", []) or []
        transactions = [
            self._parse_tx(tx) if isinstance(tx, dict) else tx
            for tx in raw_txs
        ]
        return Block(
            number=obj.get("number", "0x0"),
            hash=obj.get("hash", "0x0"),
            parent_hash=obj.get("parentHash", "0x0"),
            nonce=obj.get("nonce", "0x0"),
            sha3_uncles=obj.get("sha3Uncles", "0x0"),
            logs_bloom=obj.get("logsBloom", "0x0"),
            transactions_root=obj.get("transactionsRoot", "0x0"),
            state_root=obj.get("stateRoot", "0x0"),
            receipts_root=obj.get("receiptsRoot", "0x0"),
            miner=obj.get("miner", "0x0"),
            proposer=obj.get("proposer", "0x0"),
            difficulty=obj.get("difficulty", "0x0"),
            total_difficulty=obj.get("totalDifficulty", "0x0"),
            extra_data=obj.get("extraData", "0x"),
            size=obj.get("size", "0x0"),
            gas_limit=obj.get("gasLimit", "0x0"),
            gas_used=obj.get("gasUsed", "0x0"),
            base_fee=obj.get("baseFeePerGas", "0x0"),
            timestamp=obj.get("timestamp", "0x0"),
            transactions=transactions,
            uncles=obj.get("uncles", []) or [],
            mix_hash=obj.get("mixHash", "0x0"),
            domain_events=obj.get("domainEvents"),
        )

    def _parse_tx(self, obj: Dict) -> Transaction:
        return Transaction(
            hash=obj.get("hash", "0x0"),
            from_=obj.get("from", "0x0"),
            to=obj.get("to"),
            value=obj.get("value", "0x0"),
            nonce=obj.get("nonce", "0x0"),
            gas=obj.get("gas", "0x0"),
            gas_price=obj.get("gasPrice", "0x0"),
            input=obj.get("input", "0x"),
            block_hash=obj.get("blockHash"),
            block_number=obj.get("blockNumber"),
            transaction_index=obj.get("transactionIndex"),
            type=obj.get("type"),
            v=obj.get("v"),
            r=obj.get("r"),
            s=obj.get("s"),
            chain_id=obj.get("chainId"),
        )

    def _parse_log(self, obj: Dict) -> Log:
        return Log(
            address=obj.get("address", "0x0"),
            topics=obj.get("topics", []) or [],
            data=obj.get("data", "0x"),
            block_number=obj.get("blockNumber", "0x0"),
            block_hash=obj.get("blockHash", "0x0"),
            transaction_hash=obj.get("transactionHash", "0x0"),
            transaction_index=obj.get("transactionIndex", "0x0"),
            log_index=obj.get("logIndex", "0x0"),
            removed=obj.get("removed", False),
        )

    def _parse_receipt(self, obj: Dict) -> Receipt:
        logs = [self._parse_log(log) for log in (obj.get("logs", []) or [])]
        return Receipt(
            transaction_hash=obj.get("transactionHash", "0x0"),
            block_hash=obj.get("blockHash", "0x0"),
            block_number=obj.get("blockNumber", "0x0"),
            transaction_index=obj.get("transactionIndex", "0x0"),
            from_=obj.get("from", "0x0"),
            to=obj.get("to"),
            gas_used=obj.get("gasUsed", "0x0"),
            cumulative_gas_used=obj.get("cumulativeGasUsed", "0x0"),
            effective_gas_price=obj.get("effectiveGasPrice", "0x0"),
            status=obj.get("status", "0x0"),
            contract_address=obj.get("contractAddress"),
            logs_bloom=obj.get("logsBloom", "0x0"),
            type=obj.get("type"),
            logs=logs,
        )

    def get_transaction(self, hash: str) -> Optional[Transaction]:
        """Get transaction by hash."""
        result = self._request("eth_getTransactionByHash", [hash])
        if result is None:
            return None
        return self._parse_tx(result)

    def get_transaction_receipt(self, hash: str) -> Optional[Receipt]:
        """Get transaction receipt by hash."""
        result = self._request("eth_getTransactionReceipt", [hash])
        if result is None:
            return None
        return self._parse_receipt(result)

    def get_balance(self, address: str) -> str:
        """Get balance of address (hex string)."""
        result = self._request("eth_getBalance", [address])
        return _hex_to_string(result) if result else "0x0"

    def get_nonce(self, address: str) -> int:
        """Get nonce of address."""
        result = self._request("eth_getTransactionCount", [address])
        return _hex_to_number(result) if result else 0

    def send_raw_transaction(self, raw_tx: str) -> str:
        """Send raw signed transaction. Returns tx hash."""
        return self._request("eth_sendRawTransaction", [raw_tx])

    def call(self, tx_object: Dict) -> str:
        """eth_call - simulate contract call."""
        result = self._request("eth_call", [tx_object])
        return result or "0x"

    def chain_id(self) -> int:
        """Get chain ID."""
        result = self._request("eth_chainId")
        return _hex_to_number(result) if result else 0

    def block_number(self) -> int:
        """Get latest block number."""
        result = self._request("eth_blockNumber")
        return _hex_to_number(result) if result else 0

    def view_notes(
        self,
        grant_id_hex: str,
        limit: Optional[int] = None,
        cursor_hex: Optional[str] = None,
    ) -> ViewNotesResult:
        """Get grant-gated encrypted note exports via mersennet_viewNotes."""
        request: Dict[str, Any] = {"grantIdHex": grant_id_hex}
        if limit is not None:
            request["limit"] = limit
        if cursor_hex is not None:
            request["cursorHex"] = cursor_hex
        result = self._request("mersennet_viewNotes", [request])
        notes = [
            ViewNotesEntry(
                note_commitment=entry.get("noteCommitment", "0x"),
                encrypted_note=entry.get("encryptedNote", "0x"),
            )
            for entry in result.get("notes", [])
        ]
        return ViewNotesResult(
            grant_id=result.get("grantId", "0x"),
            grantor_commitment=result.get("grantorCommitment", "0x"),
            block_number=result.get("blockNumber", 0),
            shielded_state_root=result.get("shieldedStateRoot", "0x"),
            total_encrypted_note_count=result.get("totalEncryptedNoteCount", 0),
            returned_encrypted_note_count=result.get("returnedEncryptedNoteCount", 0),
            next_cursor=result.get("nextCursor"),
            notes=notes,
            signature_verified=result.get("signatureVerified", False),
        )

    def gas_price(self) -> str:
        """Get current gas price (hex)."""
        result = self._request("eth_gasPrice")
        return _hex_to_string(result) if result else "0x0"
