"""Focused tests for Python-native strategy rules and warm-up behavior."""

from __future__ import annotations

import unittest

try:
    from .turtle_backtest import Parameters, PriceBar, run_backtest
except ImportError:
    from turtle_backtest import Parameters, PriceBar, run_backtest


def rising_bars(count: int) -> list[PriceBar]:
    return [
        PriceBar(
            date=index + 1,
            open=float(index + 1),
            high=float(index + 2),
            low=float(index + 0.5),
            close=float(index + 1.5),
        )
        for index in range(count)
    ]


class StrategyRuleTest(unittest.TestCase):
    def test_default_warmup_is_derived_from_periods(self) -> None:
        parameters = Parameters(atr_period=7, entry_period=12, exit_period=5)
        self.assertEqual(parameters.required_history, 12)

        rows, _ = run_backtest(rising_bars(20), parameters)
        self.assertTrue(all(row.past_high is None for row in rows[:12]))
        self.assertIsNotNone(rows[12].past_high)
        self.assertIsNotNone(rows[12].past_low)

    def test_channel_uses_completed_bars_only(self) -> None:
        parameters = Parameters(atr_period=3, entry_period=3, exit_period=2)
        rows, _ = run_backtest(rising_bars(6), parameters)

        # On bar 4, the entry channel is made from bars 1-3.  The current
        # bar's high is deliberately not included.
        self.assertEqual(rows[3].past_high, 4.0)
        self.assertEqual(rows[3].past_low, 1.5)
        self.assertEqual(rows[3].signal, 1)

    def test_equal_high_does_not_trigger_strict_breakout(self) -> None:
        bars = rising_bars(3)
        bars.append(
            PriceBar(date=4, open=3.5, high=4.0, low=3.0, close=3.8)
        )
        rows, _ = run_backtest(
            bars, Parameters(atr_period=3, entry_period=3, exit_period=2)
        )
        self.assertEqual(rows[3].past_high, 4.0)
        self.assertEqual(rows[3].signal, 0)
        self.assertEqual(rows[3].trade, "")

    def test_gap_execution_fixed_stop_and_full_exit(self) -> None:
        bars = [
            PriceBar(date=1, open=10, high=11, low=9, close=10),
            PriceBar(date=2, open=10, high=12, low=10, close=11),
            # Gap above the previous two-bar high: buy at the open, not 12.
            PriceBar(date=3, open=13, high=14, low=12, close=13),
            # Gap below the fixed stop: sell at the open, not the stop level.
            PriceBar(date=4, open=10, high=11, low=9, close=10),
        ]
        parameters = Parameters(
            atr_period=2,
            entry_period=2,
            exit_period=2,
            buy_cost_rate=0,
            sell_cost_rate=0,
        )
        rows, _ = run_backtest(bars, parameters)

        self.assertEqual(rows[2].trade, "BUY")
        self.assertEqual(rows[2].trade_price, 13)
        self.assertEqual(rows[2].stop_loss, 11)
        self.assertGreater(rows[2].position, 0)

        self.assertEqual(rows[3].trade, "SELL")
        self.assertEqual(rows[3].trade_price, 10)
        self.assertEqual(rows[3].position, 0)

    def test_custom_warmup_cannot_be_shorter_than_channels(self) -> None:
        with self.assertRaisesRegex(ValueError, "自定义预热期"):
            run_backtest(
                rising_bars(20),
                Parameters(entry_period=10, exit_period=5, warmup_bars=9),
            )

    def test_prefix_results_do_not_change_when_future_bars_are_added(self) -> None:
        bars = rising_bars(30)
        parameters = Parameters(atr_period=5, entry_period=5, exit_period=3)
        prefix_rows, _ = run_backtest(bars[:20], parameters)
        full_rows, _ = run_backtest(bars, parameters)

        for prefix, full in zip(prefix_rows, full_rows):
            self.assertEqual(prefix, full)


if __name__ == "__main__":
    unittest.main()
