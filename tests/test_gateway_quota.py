"""Credit pricing, usage windows, and atomic admission decisions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import quota


class QuotaTests(unittest.TestCase):
    def test_credit_cost_applies_input_and_output_weights(self):
        self.assertEqual(quota.credit_cost(12, 3), 18)
        self.assertEqual(quota.credit_cost(12, 3, input_weight=2.0, output_weight=1.0), 27)
        self.assertEqual(quota.credit_cost(0, 0), 0)

    def test_usage_in_window_uses_half_open_interval(self):
        settled = [(100, 5), (200, 3)]
        self.assertEqual(quota.usage_in_window(settled, now=250, seconds=100), 3)
        self.assertEqual(quota.usage_in_window(settled, now=1000, seconds=1000), 8)
        self.assertEqual(quota.usage_in_window([(100, 5)], now=200, seconds=100), 0)
        self.assertEqual(quota.usage_in_window([(100, 5)], now=102, seconds=100), 5)

    def test_evaluate_admission_rejects_when_reservation_exceeds_limit(self):
        decision = quota.evaluate_admission(
            reserved_credits=3,
            windows=[quota.WindowUsage(kind="rolling", seconds=quota.ROLLING_WINDOW_SECONDS, credits=8)],
            limits=quota.Limits(rolling_credits=10),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reasons, ("rolling_credits_exceeded",))
        self.assertEqual(decision.remaining_by_window["rolling"], -1)

    def test_evaluate_admission_allows_when_reservation_fits(self):
        decision = quota.evaluate_admission(
            reserved_credits=2,
            windows=[quota.WindowUsage(kind="rolling", seconds=quota.ROLLING_WINDOW_SECONDS, credits=8)],
            limits=quota.Limits(rolling_credits=10),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.remaining_by_window["rolling"], 0)

    def test_evaluate_admission_ignores_unlimited_windows(self):
        decision = quota.evaluate_admission(reserved_credits=999, windows=[quota.WindowUsage(kind="rolling", seconds=quota.ROLLING_WINDOW_SECONDS, credits=999)], limits=quota.Limits())
        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.remaining_by_window["rolling"])

    def test_quota_ledger_reserve_settle_and_release(self):
        ledger = quota.QuotaLedger(now=1000)
        decision = ledger.reserve(4, quota.Limits(rolling_credits=10))
        self.assertTrue(decision.allowed)
        self.assertEqual(ledger._reserved_credits, 4)
        ledger.settle(4, now=1100)
        self.assertEqual(ledger._reserved_credits, 0)
        self.assertEqual(quota.usage_in_window(ledger._settled["rolling"], now=1200, seconds=quota.ROLLING_WINDOW_SECONDS), 4)

        ledger2 = quota.QuotaLedger(now=1000)
        ledger2.reserve(11, quota.Limits(rolling_credits=10))
        self.assertFalse(ledger2._reserved_credits > 0)


if __name__ == "__main__":
    unittest.main()
