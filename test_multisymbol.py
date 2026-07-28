"""Regression tests for the Raw_data multi-instrument workflow."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from .turtle_backtest import load_raw_data_xlsx, run_backtest

ROOT = Path(__file__).resolve().parents[1]
RAW_DATA = ROOT / "Excel_version" / "海龟法则_stock_data_2026.xlsx"


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

    def test_hs300_still_matches_reference_result(self) -> None:
        instrument = next(
            item for item in self.instruments if item.symbol == "000300.SH"
        )
        _, summary = run_backtest(instrument.bars)
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
