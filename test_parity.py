"""Full-row parity test against the cached results in the source workbook."""

from __future__ import annotations

import math
import unittest
import zipfile
from pathlib import Path

try:
    from .inspect_workbook import shared_strings, sheet_cells
    from .turtle_backtest import load_reference_xlsx, run_backtest
except ImportError:
    from inspect_workbook import shared_strings, sheet_cells
    from turtle_backtest import load_reference_xlsx, run_backtest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "Excel_version" / "海龟回测_沪深300_周淞铭.xlsx"

FIELD_TO_COLUMN = {
    "clean_open": "G",
    "clean_high": "H",
    "clean_low": "I",
    "clean_close": "J",
    "tr": "K",
    "atr": "L",
    "past_high": "M",
    "past_low": "N",
    "signal": "O",
    "trade_price": "P",
    "stop_loss": "Q",
    "position": "R",
    "cash": "S",
    "stock_value": "T",
    "trading_cost": "U",
    "daily_pnl": "V",
    "nav": "W",
    "daily_return": "X",
    "drawdown": "Y",
    "nav_index": "Z",
    "close_index": "AA",
    "trade": "AB",
}


class WorkbookParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.summary = run_backtest(load_reference_xlsx(REFERENCE))
        with zipfile.ZipFile(REFERENCE) as book:
            cls.cached = sheet_cells(
                book, "xl/worksheets/sheet1.xml", shared_strings(book)
            )
        if "AD4" not in cls.cached or "L6" not in cls.cached:
            raise unittest.SkipTest(
                "当前源工作簿没有保存公式缓存；完整对账需使用原计算版工作簿"
            )

    def test_every_cached_backtest_cell(self) -> None:
        mismatches: list[str] = []
        for index, result in enumerate(self.rows):
            excel_row = index + 6
            for field, column in FIELD_TO_COLUMN.items():
                actual = getattr(result, field)
                expected = self.cached[f"{column}{excel_row}"]["value"]
                if expected == "":
                    expected = None
                if actual == "":
                    actual = None
                if isinstance(expected, (int, float)) and isinstance(
                    actual, (int, float)
                ):
                    equal = math.isclose(
                        float(actual), float(expected), rel_tol=2e-12, abs_tol=2e-8
                    )
                else:
                    equal = actual == expected
                if not equal:
                    mismatches.append(
                        f"{column}{excel_row}/{field}: "
                        f"Python={actual!r}, Excel={expected!r}"
                    )
                    if len(mismatches) >= 20:
                        break
            if len(mismatches) >= 20:
                break
        self.assertFalse(mismatches, "\n" + "\n".join(mismatches))

    def test_summary(self) -> None:
        expected = {
            "ending_nav": "AD4",
            "total_return": "AD5",
            "annualized_return": "AD6",
            "max_drawdown": "AD7",
            "annualized_volatility": "AD8",
            "sharpe_ratio": "AD9",
            "buys": "AD10",
            "sells": "AD11",
            "time_in_market": "AD12",
            "ending_position": "AD13",
            "total_trading_cost": "AD14",
            "nav_check": "AD15",
            "minimum_cash": "AD16",
            "current_signal": "AD17",
        }
        for field, cell in expected.items():
            actual = getattr(self.summary, field)
            cached = self.cached[cell]["value"]
            if isinstance(cached, (int, float)):
                self.assertTrue(
                    math.isclose(
                        float(actual), float(cached), rel_tol=2e-12, abs_tol=2e-8
                    ),
                    f"{field}: Python={actual!r}, Excel={cached!r}",
                )
            else:
                self.assertEqual(actual, cached, field)


if __name__ == "__main__":
    unittest.main()
