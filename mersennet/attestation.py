"""Compliance / view-key attestation (selective disclosure, ADR-019).

A grantee holding a scoped viewing grant (e.g. an exchange, auditor, or
regulated counterparty) reconstructs a grantor's shielded portfolio locally
and then produces a **portable, tamper-evident attestation**: a compact
document asserting the balances observed as of a specific block and shielded
state root, bound to the grant.

The attestation is the selective-disclosure output: the grantor reveals
exactly the scope the grant permits, to exactly the party the grant names,
and the recipient can hand the signed artifact to a third party (an auditor,
a compliance desk) who can verify integrity without any chain access.

Design goals:
  * **Deterministic digest** - a canonical serialization hashed with SHA-256,
    so the same portfolio always yields the same digest across SDKs.
  * **Cross-checkable** - carries the node's ``mersennet_viewPortfolioDigest``
    when available, and flags whether the locally-reconstructed digest matches.
  * **Dependency-free signing** - signing/verification are injected callbacks,
    so a wallet can plug in secp256k1/ed25519 without the SDK forcing a dep.

This is a faithful cross-language design shared with the TypeScript and Go
SDKs (``attestation.ts`` / ``attestation.go``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import time
from typing import Callable, Dict, Optional, Tuple

from .reconstruction import BalanceReconstructionResult, ReconstructedPortfolio

ATTESTATION_VERSION = "mersennet-attestation-v1"

# Signer: (digest_hex) -> signature_hex.  Verifier: (digest_hex, signature_hex, attester) -> bool.
Signer = Callable[[str], str]
Verifier = Callable[[str, str, Optional[str]], bool]


@dataclass
class ComplianceAttestation:
    version: str
    grant_id: str
    grantor_commitment: str
    block_number: int
    shielded_state_root: str
    per_asset: Dict[int, int]
    unspent_note_count: int
    spent_nullifier_count: int
    portfolio_digest: str
    issued_at: int
    scope: str = "balances:read"
    onchain_portfolio_digest: Optional[str] = None
    digest_matches_onchain: Optional[bool] = None
    attester: Optional[str] = None
    signature: Optional[str] = None

    def to_dict(self) -> Dict:
        """JSON-serializable dict with camelCase keys (wire parity with TS/Go)."""
        return {
            "version": self.version,
            "grantId": self.grant_id,
            "grantorCommitment": self.grantor_commitment,
            "blockNumber": self.block_number,
            "shieldedStateRoot": self.shielded_state_root,
            "perAsset": {str(k): str(v) for k, v in sorted(self.per_asset.items())},
            "unspentNoteCount": self.unspent_note_count,
            "spentNullifierCount": self.spent_nullifier_count,
            "portfolioDigest": self.portfolio_digest,
            "issuedAt": self.issued_at,
            "scope": self.scope,
            "onchainPortfolioDigest": self.onchain_portfolio_digest,
            "digestMatchesOnchain": self.digest_matches_onchain,
            "attester": self.attester,
            "signature": self.signature,
        }

    @staticmethod
    def from_dict(obj: Dict) -> "ComplianceAttestation":
        per_asset = {int(k): int(v) for k, v in (obj.get("perAsset", {}) or {}).items()}
        return ComplianceAttestation(
            version=obj.get("version", ATTESTATION_VERSION),
            grant_id=obj.get("grantId", "0x"),
            grantor_commitment=obj.get("grantorCommitment", "0x"),
            block_number=obj.get("blockNumber", 0),
            shielded_state_root=obj.get("shieldedStateRoot", "0x"),
            per_asset=per_asset,
            unspent_note_count=obj.get("unspentNoteCount", 0),
            spent_nullifier_count=obj.get("spentNullifierCount", 0),
            portfolio_digest=obj.get("portfolioDigest", "0x"),
            issued_at=obj.get("issuedAt", 0),
            scope=obj.get("scope", "balances:read"),
            onchain_portfolio_digest=obj.get("onchainPortfolioDigest"),
            digest_matches_onchain=obj.get("digestMatchesOnchain"),
            attester=obj.get("attester"),
            signature=obj.get("signature"),
        )


def _canonical_preimage(
    grant_id: str,
    grantor_commitment: str,
    block_number: int,
    shielded_state_root: str,
    per_asset: Dict[int, int],
    unspent_note_count: int,
    spent_nullifier_count: int,
) -> str:
    """Deterministic string over the disclosed facts. Asset ids are sorted so
    dict ordering never affects the digest; this string is identical across
    the TS/Python/Go SDKs."""
    assets = "|".join(f"{aid}:{per_asset[aid]}" for aid in sorted(per_asset))
    return "\n".join(
        [
            ATTESTATION_VERSION,
            grant_id.lower(),
            grantor_commitment.lower(),
            str(block_number),
            shielded_state_root.lower(),
            assets,
            str(unspent_note_count),
            str(spent_nullifier_count),
        ]
    )


def compute_portfolio_digest(
    grant_id: str,
    grantor_commitment: str,
    block_number: int,
    shielded_state_root: str,
    per_asset: Dict[int, int],
    unspent_note_count: int,
    spent_nullifier_count: int,
) -> str:
    preimage = _canonical_preimage(
        grant_id,
        grantor_commitment,
        block_number,
        shielded_state_root,
        per_asset,
        unspent_note_count,
        spent_nullifier_count,
    )
    return "0x" + hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def build_portfolio_attestation(
    result: BalanceReconstructionResult,
    *,
    grantor_commitment: str = "0x",
    scope: str = "balances:read",
    onchain_portfolio_digest: Optional[str] = None,
    attester: Optional[str] = None,
    sign: Optional[Signer] = None,
    issued_at: Optional[int] = None,
) -> ComplianceAttestation:
    """Build a compliance attestation from a reconstructed balance result.

    ``result`` typically comes from :func:`scan_and_reconstruct_balances`.
    Pass ``onchain_portfolio_digest`` (from
    ``provider`` ``mersennet_viewPortfolioDigest``) to cross-check the local
    reconstruction against the node's independent digest. Pass a ``sign``
    callback to bind the attester's signature over the portfolio digest.
    """
    digest = compute_portfolio_digest(
        result.grant_id,
        grantor_commitment,
        result.block_number,
        result.shielded_state_root,
        result.per_asset,
        result.unspent_note_count,
        result.spent_nullifier_count,
    )

    digest_matches: Optional[bool] = None
    if onchain_portfolio_digest is not None:
        digest_matches = onchain_portfolio_digest.lower() == digest.lower()

    signature = sign(digest) if sign is not None else None

    return ComplianceAttestation(
        version=ATTESTATION_VERSION,
        grant_id=result.grant_id,
        grantor_commitment=grantor_commitment,
        block_number=result.block_number,
        shielded_state_root=result.shielded_state_root,
        per_asset=dict(result.per_asset),
        unspent_note_count=result.unspent_note_count,
        spent_nullifier_count=result.spent_nullifier_count,
        portfolio_digest=digest,
        issued_at=issued_at if issued_at is not None else int(time.time()),
        scope=scope,
        onchain_portfolio_digest=onchain_portfolio_digest,
        digest_matches_onchain=digest_matches,
        attester=attester,
        signature=signature,
    )


def verify_attestation(
    attestation: ComplianceAttestation,
    *,
    verify_sig: Optional[Verifier] = None,
) -> Tuple[bool, str]:
    """Verify an attestation's integrity (and optionally its signature).

    Returns ``(ok, reason)``. Integrity: recompute the digest from the
    attestation's own disclosed fields and require it to equal the embedded
    ``portfolio_digest``. If ``verify_sig`` is supplied and a signature is
    present, the signature must also verify over the digest.
    """
    recomputed = compute_portfolio_digest(
        attestation.grant_id,
        attestation.grantor_commitment,
        attestation.block_number,
        attestation.shielded_state_root,
        attestation.per_asset,
        attestation.unspent_note_count,
        attestation.spent_nullifier_count,
    )
    if recomputed.lower() != attestation.portfolio_digest.lower():
        return False, "digest mismatch: attestation fields do not hash to the embedded digest"

    if attestation.digest_matches_onchain is False:
        return False, "reconstructed digest did not match the on-chain portfolio digest"

    if verify_sig is not None:
        if not attestation.signature:
            return False, "signature required but missing"
        if not verify_sig(attestation.portfolio_digest, attestation.signature, attestation.attester):
            return False, "signature verification failed"

    return True, "ok"
