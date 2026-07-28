"""Regression tests for the Raw_data multi-instrument workflow."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

try:
    from .turtle_backtest import Parameters, load_raw_data_xlsx, run_backtest
except ImportError:
    from turtle_backtest import Parameters, load_raw_data_xlsx, run_backtest

ROOT = Path(__file__).resolve().parent
RAW_DATA = ROOT / "data" / "market_data.xlsx"


class MultiSymbolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.instruments = load_raw_data_xlsx(RAW_DATA)

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

    def test_51_bar_compatibility_warmup_reproduces_legacy_result(self) -> None:
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
                self.assertGreater(len(rows), 50)
                self.assertEqual(summary.nav_check, "PASS")


if __name__ == "__main__":
    unittest.main()
