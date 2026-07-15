"""Client-side portfolio reconstruction (ADR-019 ``balances:read``).

The privacy fork deliberately keeps the node from ever returning a decrypted
per-account balance. Instead the owner - or a grantee holding a scoped viewing
grant - decrypts the notes addressed to them (:func:`scan_granted_notes` in
``shielded``) and reconstructs spendable balances locally, here.

Reconstruction rule: a note contributes to the balance only if its nullifier
has *not* been published on chain. The caller supplies the set of spent
nullifiers (e.g. derived from the public nullifier stream) and a deriver that
maps an owned note to its nullifier. A deterministic default deriver is
provided for tests and for wallets that use the matching chain-side mock
scheme; production wallets pass their real ``nvk``-based deriver.

This is a faithful port of ``sdk-ts/src/reconstruction.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Callable, Dict, Iterable, List, Optional

from .provider import MersennetProvider
from .shielded import (
    GrantedViewingMaterial,
    GrantedNoteDecryptInput,
    ShieldedNote,
    parse_encrypted_note_payload,
    parse_shielded_note_plaintext,
)

# Maps an owned note to its on-chain nullifier (hex, 0x-prefixed).
NullifierDeriver = Callable[[ShieldedNote], str]


@dataclass
class PortfolioNote:
    note: ShieldedNote
    nullifier: str
    spent: bool


@dataclass
class ReconstructedPortfolio:
    """Spendable balance per asset id (unspent notes only)."""

    per_asset: Dict[int, int] = field(default_factory=dict)
    unspent_note_count: int = 0
    spent_note_count: int = 0
    total_note_count: int = 0
    notes: List[PortfolioNote] = field(default_factory=list)


@dataclass
class BalanceReconstructionResult(ReconstructedPortfolio):
    """Spendable portfolio reconstructed from a grant-gated ``balances:read``."""

    grant_id: str = "0x"
    block_number: int = 0
    shielded_state_root: str = "0x"
    total_encrypted_note_count: int = 0
    fetched_encrypted_note_count: int = 0
    skipped_malformed_count: int = 0
    spent_nullifier_count: int = 0


def _normalize_hex(value: str) -> str:
    body = value[2:] if value.lower().startswith("0x") else value
    return "0x" + body.lower()


def _hex_to_bytes(value: str) -> bytes:
    body = value[2:] if value.startswith("0x") else value
    if len(body) % 2 != 0:
        raise ValueError("hex string must have an even number of characters")
    return bytes.fromhex(body)


def default_nullifier_deriver(note: ShieldedNote) -> str:
    """Deterministic nullifier derivation used by tests and by wallets that
    mirror the chain's mock scheme: ``sha256(owner_pk || rho || psi)``.

    Production wallets override this with their real nullifier-viewing-key
    derivation (the chain scheme is ``Poseidon(spend_sk, rho)``).
    """
    h = hashlib.sha256()
    h.update(_hex_to_bytes(note.owner_pk))
    h.update(_hex_to_bytes(note.rho))
    h.update(_hex_to_bytes(note.psi))
    return "0x" + h.hexdigest()


def reconstruct_portfolio(
    notes: Iterable[ShieldedNote],
    *,
    derive_nullifier: Optional[NullifierDeriver] = None,
    spent_nullifiers: Optional[Iterable[str]] = None,
    is_spent: Optional[Callable[[str], bool]] = None,
) -> ReconstructedPortfolio:
    """Reconstruct spendable balances from a set of decrypted notes.

    Notes are de-duplicated by nullifier so a note seen twice during scanning
    is never double-counted. Only unspent notes contribute to ``per_asset``.
    """
    deriver = derive_nullifier or default_nullifier_deriver

    if is_spent is not None:
        spent_predicate = is_spent
    elif spent_nullifiers is not None:
        spent_set = {_normalize_hex(n) for n in spent_nullifiers}
        spent_predicate = lambda nh: _normalize_hex(nh) in spent_set  # noqa: E731
    else:
        spent_predicate = lambda _nh: False  # noqa: E731

    per_asset: Dict[int, int] = {}
    portfolio_notes: List[PortfolioNote] = []
    seen = set()
    unspent = 0
    spent = 0

    for note in notes:
        nullifier = _normalize_hex(deriver(note))
        if nullifier in seen:
            continue
        seen.add(nullifier)

        is_spent_note = spent_predicate(nullifier)
        portfolio_notes.append(PortfolioNote(note=note, nullifier=nullifier, spent=is_spent_note))
        if is_spent_note:
            spent += 1
            continue
        unspent += 1
        per_asset[note.asset_id] = per_asset.get(note.asset_id, 0) + note.value

    return ReconstructedPortfolio(
        per_asset=per_asset,
        unspent_note_count=unspent,
        spent_note_count=spent,
        total_note_count=len(portfolio_notes),
        notes=portfolio_notes,
    )


def scan_and_reconstruct_balances(
    provider: MersennetProvider,
    granted_viewing_material: GrantedViewingMaterial,
    *,
    derive_nullifier: Optional[NullifierDeriver] = None,
    limit: Optional[int] = None,
    cursor_hex: Optional[str] = None,
    max_pages: Optional[int] = None,
    ignore_malformed: bool = True,
) -> BalanceReconstructionResult:
    """End-to-end balance read (Workstream F2 + F5).

    Pages through the grant-gated ``mersennet_viewBalances`` RPC, decrypts the
    notes addressed to the grantor via the supplied viewing material, collects
    the on-chain spent-nullifier set, and reconstructs spendable per-asset
    balances locally. The node never sees a decrypted balance.
    """
    page_count = 0
    block_number = 0
    shielded_state_root = "0x"
    total_encrypted_note_count = 0
    fetched_encrypted_note_count = 0
    skipped_malformed_count = 0
    owned_notes: List[ShieldedNote] = []
    spent_nullifiers = set()
    next_cursor = cursor_hex

    while max_pages is None or page_count < max_pages:
        page = provider.view_balances(
            granted_viewing_material.grant_id_hex,
            limit=limit,
            cursor_hex=next_cursor,
        )
        block_number = page.block_number
        shielded_state_root = page.shielded_state_root
        total_encrypted_note_count = page.total_encrypted_note_count
        fetched_encrypted_note_count += page.returned_encrypted_note_count
        for nullifier in page.spent_nullifiers:
            spent_nullifiers.add(_normalize_hex(nullifier))

        for entry in page.notes:
            try:
                envelope = parse_encrypted_note_payload(entry.encrypted_note)
            except ValueError:
                if ignore_malformed:
                    skipped_malformed_count += 1
                    continue
                raise

            if (
                granted_viewing_material.recipient_public_key
                and not _hex_equal(envelope.recipient, granted_viewing_material.recipient_public_key)
            ):
                continue

            plaintext = granted_viewing_material.decrypt_note_ciphertext(
                GrantedNoteDecryptInput(
                    note_commitment=entry.note_commitment,
                    encrypted_note_hex=entry.encrypted_note,
                    envelope=envelope,
                )
            )
            if not plaintext:
                continue
            try:
                owned_notes.append(parse_shielded_note_plaintext(plaintext))
            except ValueError:
                if ignore_malformed:
                    skipped_malformed_count += 1
                    continue
                raise

        page_count += 1
        next_cursor = page.next_cursor
        if not page.next_cursor:
            break

    portfolio = reconstruct_portfolio(
        owned_notes,
        derive_nullifier=derive_nullifier,
        spent_nullifiers=spent_nullifiers,
    )

    return BalanceReconstructionResult(
        per_asset=portfolio.per_asset,
        unspent_note_count=portfolio.unspent_note_count,
        spent_note_count=portfolio.spent_note_count,
        total_note_count=portfolio.total_note_count,
        notes=portfolio.notes,
        grant_id=granted_viewing_material.grant_id_hex,
        block_number=block_number,
        shielded_state_root=shielded_state_root,
        total_encrypted_note_count=total_encrypted_note_count,
        fetched_encrypted_note_count=fetched_encrypted_note_count,
        skipped_malformed_count=skipped_malformed_count,
        spent_nullifier_count=len(spent_nullifiers),
    )


def _hex_equal(left: str, right: str) -> bool:
    return left.removeprefix("0x").lower() == right.removeprefix("0x").lower()
