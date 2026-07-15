"""Tests for client-side portfolio / order / position reconstruction and the
compliance attestation - parity with the TypeScript SDK test suite."""

import unittest

from mersennet.shielded import ShieldedNote, viewing_key_from_seed, create_owner_viewing_material
from mersennet.reconstruction import (
    BalanceReconstructionResult,
    default_nullifier_deriver,
    reconstruct_portfolio,
)
from mersennet.positions import (
    FillRecord,
    OrderRecord,
    reconstruct_open_orders,
    reconstruct_positions,
)
from mersennet.attestation import (
    build_portfolio_attestation,
    compute_portfolio_digest,
    verify_attestation,
)


def note(value: int, asset_id: int, tag: str) -> ShieldedNote:
    return ShieldedNote(
        value=value,
        asset_id=asset_id,
        owner_pk="0x" + "11" * 32,
        rho="0x" + tag * 32,
        psi="0x" + "99" * 32,
    )


class PortfolioTests(unittest.TestCase):
    def test_sums_unspent_notes_per_asset(self) -> None:
        notes = [note(100, 0, "aa"), note(50, 0, "bb"), note(7, 1, "cc")]
        p = reconstruct_portfolio(notes)
        self.assertEqual(p.per_asset[0], 150)
        self.assertEqual(p.per_asset[1], 7)
        self.assertEqual(p.unspent_note_count, 3)
        self.assertEqual(p.spent_note_count, 0)

    def test_excludes_spent_notes(self) -> None:
        n_spent = note(100, 0, "aa")
        n_live = note(50, 0, "bb")
        spent_nullifier = default_nullifier_deriver(n_spent)
        p = reconstruct_portfolio([n_spent, n_live], spent_nullifiers=[spent_nullifier])
        self.assertEqual(p.per_asset[0], 50)
        self.assertEqual(p.spent_note_count, 1)
        self.assertEqual(p.unspent_note_count, 1)

    def test_dedupes_by_nullifier(self) -> None:
        n = note(100, 0, "aa")
        p = reconstruct_portfolio([n, n, n])
        self.assertEqual(p.total_note_count, 1)
        self.assertEqual(p.per_asset[0], 100)

    def test_default_nullifier_is_deterministic(self) -> None:
        n = note(1, 0, "aa")
        self.assertEqual(default_nullifier_deriver(n), default_nullifier_deriver(n))
        self.assertTrue(default_nullifier_deriver(n).startswith("0x"))
        self.assertEqual(len(default_nullifier_deriver(n)), 66)


class OpenOrderTests(unittest.TestCase):
    def test_reports_remaining_unfilled_size(self) -> None:
        orders = [
            OrderRecord(order_id="o1", market_id=1, side="buy", price=100, size=10),
            OrderRecord(order_id="o2", market_id=1, side="sell", price=200, size=5, status="cancelled"),
        ]
        fills = [FillRecord(order_id="o1", market_id=1, side="buy", price=100, size=4)]
        open_orders = reconstruct_open_orders(orders, fills)
        self.assertEqual(len(open_orders), 1)
        self.assertEqual(open_orders[0].order_id, "o1")
        self.assertEqual(open_orders[0].remaining, 6)

    def test_fully_filled_order_is_not_open(self) -> None:
        orders = [OrderRecord(order_id="o1", market_id=1, side="buy", price=100, size=10)]
        fills = [FillRecord(order_id="o1", market_id=1, side="buy", price=100, size=10)]
        self.assertEqual(reconstruct_open_orders(orders, fills), [])


class PositionTests(unittest.TestCase):
    def test_average_cost_and_realized_pnl(self) -> None:
        fills = [
            FillRecord(order_id="a", market_id=1, side="buy", price=100, size=10),
            FillRecord(order_id="b", market_id=1, side="buy", price=120, size=10),
            FillRecord(order_id="c", market_id=1, side="sell", price=150, size=5),
        ]
        positions = reconstruct_positions(fills)
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos.net_size, 15)
        self.assertEqual(pos.entry_price, 110)  # (100*10 + 120*10)/20
        self.assertEqual(pos.realized_pnl, (150 - 110) * 5)  # 200

    def test_flip_long_to_short(self) -> None:
        fills = [
            FillRecord(order_id="a", market_id=2, side="buy", price=100, size=5),
            FillRecord(order_id="b", market_id=2, side="sell", price=120, size=8),
        ]
        pos = reconstruct_positions(fills)[0]
        self.assertEqual(pos.net_size, -3)
        self.assertEqual(pos.entry_price, 120)  # remainder opens short at fill price
        self.assertEqual(pos.realized_pnl, (120 - 100) * 5)  # 100


class AttestationTests(unittest.TestCase):
    def _result(self) -> BalanceReconstructionResult:
        return BalanceReconstructionResult(
            per_asset={0: 150, 1: 7},
            unspent_note_count=3,
            spent_note_count=1,
            total_note_count=4,
            notes=[],
            grant_id="0xGRANT",
            block_number=4242,
            shielded_state_root="0xROOT",
            spent_nullifier_count=1,
        )

    def test_build_and_verify_roundtrip(self) -> None:
        att = build_portfolio_attestation(self._result(), grantor_commitment="0xC", issued_at=1000)
        ok, reason = verify_attestation(att)
        self.assertTrue(ok, reason)
        self.assertEqual(att.version, "mersennet-attestation-v1")
        self.assertEqual(att.per_asset[0], 150)

    def test_digest_is_deterministic_and_order_independent(self) -> None:
        d1 = compute_portfolio_digest("0xg", "0xc", 1, "0xr", {1: 5, 0: 9}, 2, 0)
        d2 = compute_portfolio_digest("0xg", "0xc", 1, "0xr", {0: 9, 1: 5}, 2, 0)
        self.assertEqual(d1, d2)

    def test_cross_language_digest_vector(self) -> None:
        # MUST equal the vector pinned in the TS (attestation.test.js) and Go
        # (reconstruction_test.go) suites - proves byte-identical digests.
        cross_lang = "0x574bebc386931031d68b18ccb0af7ac37b14278217badf0a73fc85146816c1f5"
        self.assertEqual(
            compute_portfolio_digest("0xg", "0xc", 1, "0xr", {0: 9, 1: 5}, 2, 0),
            cross_lang,
        )

    def test_tampering_breaks_verification(self) -> None:
        att = build_portfolio_attestation(self._result(), grantor_commitment="0xC", issued_at=1000)
        att.per_asset[0] = 999999  # tamper after signing/building
        ok, _ = verify_attestation(att)
        self.assertFalse(ok)

    def test_onchain_digest_mismatch_flagged(self) -> None:
        att = build_portfolio_attestation(
            self._result(), grantor_commitment="0xC", onchain_portfolio_digest="0xdeadbeef", issued_at=1
        )
        self.assertFalse(att.digest_matches_onchain)
        ok, _ = verify_attestation(att)
        self.assertFalse(ok)

    def test_signature_hook(self) -> None:
        signed = {}

        def sign(digest: str) -> str:
            signed["digest"] = digest
            return "0xSIG:" + digest[-8:]

        def verify(digest: str, sig: str, attester) -> bool:
            return sig == "0xSIG:" + digest[-8:]

        att = build_portfolio_attestation(
            self._result(), grantor_commitment="0xC", attester="auditor-1", sign=sign, issued_at=1
        )
        self.assertTrue(att.signature.startswith("0xSIG:"))
        ok, reason = verify_attestation(att, verify_sig=verify)
        self.assertTrue(ok, reason)

    def test_dict_roundtrip(self) -> None:
        att = build_portfolio_attestation(self._result(), grantor_commitment="0xC", issued_at=1)
        from mersennet.attestation import ComplianceAttestation

        restored = ComplianceAttestation.from_dict(att.to_dict())
        ok, reason = verify_attestation(restored)
        self.assertTrue(ok, reason)
        self.assertEqual(restored.per_asset, att.per_asset)


class ViewingKeyTests(unittest.TestCase):
    def test_from_seed_is_deterministic(self) -> None:
        a = viewing_key_from_seed("recovery phrase")
        b = viewing_key_from_seed("recovery phrase")
        self.assertEqual(a.view_pk, b.view_pk)
        self.assertNotEqual(a.spend_sk, a.view_sk)

    def test_owner_viewing_material_filters_to_view_pk(self) -> None:
        vk = viewing_key_from_seed("seed")
        material = create_owner_viewing_material(vk, "0xgrant")
        self.assertEqual(material.recipient_public_key, vk.view_pk)
        self.assertEqual(material.grant_id_hex, "0xgrant")


if __name__ == "__main__":
    unittest.main()
