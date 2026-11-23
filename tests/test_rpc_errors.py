"""RPC errors keep the node's code and data: a reverted eth_call is code 3
with the revert bytes in ``data``."""

import types
import unittest

from mersennet import provider as provider_mod
from mersennet.provider import MersennetError, MersennetProvider

REVERT = (
    "0x08c379a0"
    "0000000000000000000000000000000000000000000000000000000000000020"
    "000000000000000000000000000000000000000000000000000000000000000e"
    "756e6b6e6f776e206d61726b6574000000000000000000000000000000000000"
)


def _fake_requests(body):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"jsonrpc": "2.0", "id": 1, **body}

    return types.SimpleNamespace(post=lambda *a, **k: _Resp())


class RpcErrorTests(unittest.TestCase):
    def setUp(self):
        self._saved = (provider_mod._USE_REQUESTS, getattr(provider_mod, "requests", None))

    def tearDown(self):
        provider_mod._USE_REQUESTS, req = self._saved
        if req is not None:
            provider_mod.requests = req

    def _use(self, body):
        provider_mod._USE_REQUESTS = True
        provider_mod.requests = _fake_requests(body)

    def test_revert_keeps_code_and_data(self):
        self._use({"error": {"code": 3, "message": "execution reverted: unknown market", "data": REVERT}})
        p = MersennetProvider("http://node.test.invalid")
        with self.assertRaises(MersennetError) as ctx:
            p.call({"to": "0x0000000000000000000000000000000000000100", "data": "0x"})
        self.assertEqual(ctx.exception.code, 3)
        self.assertEqual(ctx.exception.data, REVERT)
        self.assertEqual(str(ctx.exception), "execution reverted: unknown market")

    def test_error_without_data(self):
        self._use({"error": {"code": -32000, "message": "out of gas"}})
        p = MersennetProvider("http://node.test.invalid")
        with self.assertRaises(MersennetError) as ctx:
            p.call({"to": "0x0000000000000000000000000000000000000100"})
        self.assertEqual(ctx.exception.code, -32000)
        self.assertIsNone(ctx.exception.data)

    def test_success_unchanged(self):
        self._use({"result": "0x2a"})
        p = MersennetProvider("http://node.test.invalid")
        self.assertEqual(p.call({"to": "0x0000000000000000000000000000000000000100"}), "0x2a")


if __name__ == "__main__":
    unittest.main()
