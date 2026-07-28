"""Formula-level and full-data tests for the Turtle backtest."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from data_loader import load_csv, load_raw_data_xlsx
from turtle_backtest import Parameters, PriceBar, run_backtest

ROOT = Path(__file__).resolve().parents[1]
RAW_DATA = ROOT / "data" / "market_data.xlsx"


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


class StrategyFormulaTests(unittest.TestCase):
    """Small synthetic cases that isolate individual strategy rules."""

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
            PriceBar(date=3, open=13, high=14, low=12, close=13),
            PriceBar(date=4, open=10, high=11, low=9, close=10),
        ]
        rows, _ = run_backtest(
            bars,
            Parameters(
                atr_period=2,
                entry_period=2,
                exit_period=2,
                buy_cost_rate=0,
                sell_cost_rate=0,
            ),
        )

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

    def test_future_bars_do_not_change_prefix_results(self) -> None:
        bars = rising_bars(30)
        parameters = Parameters(atr_period=5, entry_period=5, exit_period=3)
        prefix_rows, _ = run_backtest(bars[:20], parameters)
        full_rows, _ = run_backtest(bars, parameters)
        self.assertEqual(prefix_rows, full_rows[:20])


class FullBacktestTests(unittest.TestCase):
    """Raw-data loading and full-history regression checks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.instruments = load_raw_data_xlsx(RAW_DATA)

    def test_csv_loader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text(
                "Date,open,high,low,close\n"
                "2026-01-02,10,12,9,11\n",
                encoding="utf-8",
            )
            bars = load_csv(path)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].close, 11.0)

    def test_discovers_all_nine_instruments(self) -> None:
        self.assertEqual(len(self.instruments), 9)
        self.assertEqual(
            {item.symbol for item in self.instruments},
            {
                "000300.SH",
                "8841431.WI",
                "000905.SH",
                "000852.SH",
                "932000.CSI",
                "MSFT.O",
                "NVDA.O",
                "GOOGL.O",
                "AAPL.O",
            },
        )

    def test_hs300_default_result_is_stable(self) -> None:
        instrument = next(
            item for item in self.instruments if item.symbol == "000300.SH"
        )
        rows, summary = run_backtest(instrument.bars)
        self.assertTrue(
            math.isclose(
                summary.ending_nav,
                11_817_238.802793043,
                rel_tol=2e-12,
                abs_tol=2e-8,
            )
        )
        self.assertEqual((summary.buys, summary.sells), (120, 120))
        self.assertTrue(all(row.past_high is None for row in rows[:20]))
        self.assertIsNotNone(rows[20].past_high)

    def test_51_bar_warmup_reproduces_legacy_result(self) -> None:
        instrument = next(
            item for item in self.instruments if item.symbol == "000300.SH"
        )
        _, summary = run_backtest(
            instrument.bars, Parameters(warmup_bars=51)
        )
        self.assertTrue(
            math.isclose(
                summary.ending_nav,
                11_815_916.811301032,
                rel_tol=2e-12,
                abs_tol=2e-8,
            )
        )
        self.assertEqual((summary.buys, summary.sells), (119, 119))

    def test_every_instrument_completes_and_balances(self) -> None:
        for instrument in self.instruments:
            with self.subTest(symbol=instrument.symbol):
                rows, summary = run_backtest(instrument.bars)
                self.assertGreater(len(rows), 20)
                self.assertEqual(summary.nav_check, "PASS")


if __name__ == "__main__":
    unittest.main()
