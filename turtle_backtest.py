"""One-for-one Python port of 海龟回测_沪深300_周淞铭.xlsx.

The calculation order, strict inequalities, previous-day references, Excel
ROUNDDOWN behaviour and performance statistics intentionally mirror the source
workbook.  The implementation uses only Python's standard library.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from .inspect_workbook import shared_strings, sheet_cells
except ImportError:  # Direct execution from the Py_version directory.
    from inspect_workbook import shared_strings, sheet_cells


@dataclass(frozen=True)
class Parameters:
    atr_period: int = 20
    entry_period: int = 20
    exit_period: int = 10
    risk_fraction: float = 0.02
    buy_cost_rate: float = 0.0002
    sell_cost_rate: float = 0.0007
    initial_cash: float = 1_000_000.0
    lot_size: int = 100
    first_signal_excel_row: int = 57


@dataclass(frozen=True)
class PriceBar:
    date: object
    open: float | None
    high: float | None
    low: float | None
    close: float | None


@dataclass(frozen=True)
class Instrument:
    name: str
    symbol: str
    bars: tuple[PriceBar, ...]


@dataclass
class BacktestRow:
    date: object
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    clean_open: float | None
    clean_high: float | None
    clean_low: float | None
    clean_close: float | None
    tr: float | None
    atr: float | None
    past_high: float | None
    past_low: float | None
    signal: int
    trade_price: float | None
    stop_loss: float | None
    position: int
    cash: float
    stock_value: float
    trading_cost: float
    daily_pnl: float
    nav: float
    daily_return: float
    drawdown: float
    nav_index: float
    close_index: float | None
    trade: str


@dataclass(frozen=True)
class Summary:
    start: object
    end: object
    ending_nav: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    annualized_volatility: float
    sharpe_ratio: float
    buys: int
    sells: int
    time_in_market: float
    ending_position: int
    total_trading_cost: float
    nav_check: str
    minimum_cash: float
    current_signal: str


def _positive(value: object) -> float | None:
    try:
        number = float(value)  # Excel comparison treats the intended inputs as numeric.
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _excel_serial(value: object) -> float:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        # Excel's 1900 date system includes its fictitious 1900-02-29.
        return float((value - date(1899, 12, 30)).days)
    return float(value)


def excel_serial_to_date(value: float | int) -> date:
    return date(1899, 12, 30) + timedelta(days=float(value))


def run_backtest(
    bars: Iterable[PriceBar], parameters: Parameters = Parameters()
) -> tuple[list[BacktestRow], Summary]:
    source = list(bars)
    if not source:
        raise ValueError("至少需要一行 OHLC 数据")
    if parameters.atr_period <= 0 or parameters.entry_period <= 0:
        raise ValueError("ATR周期和入场周期必须大于0")
    if parameters.exit_period <= 0 or parameters.lot_size <= 0:
        raise ValueError("退出周期和最小交易单位必须大于0")

    rows: list[BacktestRow] = []
    running_nav_high = parameters.initial_cash

    for index, bar in enumerate(source):
        previous = rows[-1] if rows else None
        clean_open = _positive(bar.open)
        clean_high = _positive(bar.high)
        clean_low = _positive(bar.low)
        clean_close = _positive(bar.close)
        if previous is not None:
            clean_open = clean_open if clean_open is not None else previous.clean_open
            clean_high = clean_high if clean_high is not None else previous.clean_high
            clean_low = clean_low if clean_low is not None else previous.clean_low
            clean_close = clean_close if clean_close is not None else previous.clean_close

        if clean_high is None or clean_low is None:
            tr = None
        elif previous is None:
            tr = clean_high - clean_low
        else:
            if previous.clean_close is None:
                raise ValueError(f"第 {index + 1} 行缺少可用的前收盘价")
            tr = max(
                clean_high - clean_low,
                abs(clean_high - previous.clean_close),
                abs(previous.clean_close - clean_low),
            )

        if previous is None:
            atr = tr
        elif tr is None or previous.atr is None:
            atr = None
        else:
            n = parameters.atr_period
            atr = 2 / (n + 1) * tr + (n - 1) / (n + 1) * previous.atr

        excel_row = index + 6
        warmed_up = excel_row >= parameters.first_signal_excel_row
        if warmed_up:
            high_window = [
                row.clean_high for row in rows[-parameters.entry_period :]
            ]
            low_window = [row.clean_low for row in rows[-parameters.exit_period :]]
            if len(high_window) < parameters.entry_period or any(
                value is None for value in high_window
            ):
                raise ValueError(f"第 {excel_row} 行无法形成入场通道")
            if len(low_window) < parameters.exit_period or any(
                value is None for value in low_window
            ):
                raise ValueError(f"第 {excel_row} 行无法形成退出通道")
            past_high = max(high_window)  # type: ignore[arg-type]
            past_low = min(low_window)  # type: ignore[arg-type]
        else:
            past_high = None
            past_low = None

        previous_signal = previous.signal if previous else 0
        previous_stop = previous.stop_loss if previous else None
        if not warmed_up:
            signal = 0
        elif previous_signal == 0:
            signal = int(clean_high is not None and clean_high > past_high)
        else:
            exit_level = max(past_low, previous_stop)  # type: ignore[type-var]
            signal = int(not (clean_low is not None and clean_low < exit_level))

        is_buy = previous_signal == 0 and signal == 1
        is_sell = previous_signal == 1 and signal == 0
        if is_buy:
            trade_price = max(clean_open, past_high)  # type: ignore[type-var]
        elif is_sell:
            exit_level = max(past_low, previous_stop)  # type: ignore[type-var]
            trade_price = min(clean_open, exit_level)  # type: ignore[type-var]
        else:
            trade_price = None

        if not warmed_up:
            stop_loss = None
        elif is_buy:
            if previous is None or previous.atr is None:
                raise ValueError(f"第 {excel_row} 行缺少前一日 ATR")
            stop_loss = trade_price - previous.atr  # type: ignore[operator]
        elif signal == 1:
            stop_loss = previous_stop
        else:
            stop_loss = None

        if previous is None:
            position = 0
            cash = parameters.initial_cash
        else:
            if not warmed_up:
                position = 0
            elif is_buy:
                if previous.atr and previous.atr > 0 and trade_price and trade_price > 0:
                    risk_position = (
                        previous.nav * parameters.risk_fraction / previous.atr
                    )
                    cash_position = previous.cash / (
                        trade_price * (1 + parameters.buy_cost_rate)
                    )
                    raw_position = min(risk_position, cash_position)
                    # Excel ROUNDDOWN(x/lot, 0)*lot; all quantities are positive.
                    position = (
                        math.floor(raw_position / parameters.lot_size)
                        * parameters.lot_size
                    )
                else:
                    position = 0
            elif signal == 1:
                position = previous.position
            else:
                position = 0

            delta = position - previous.position
            if delta == 0:
                cash = previous.cash
            else:
                cost_rate = (
                    parameters.buy_cost_rate
                    if position > previous.position
                    else parameters.sell_cost_rate
                )
                cash = (
                    previous.cash
                    - delta * trade_price  # type: ignore[operator]
                    - abs(delta) * trade_price * cost_rate  # type: ignore[operator]
                )

        stock_value = position * clean_close if clean_close is not None else 0.0
        if previous is None or position == previous.position:
            trading_cost = 0.0
        else:
            rate = (
                parameters.buy_cost_rate
                if position > previous.position
                else parameters.sell_cost_rate
            )
            trading_cost = (
                abs(position - previous.position) * trade_price * rate  # type: ignore[operator]
            )
        nav = cash + stock_value
        daily_pnl = 0.0 if previous is None else nav - previous.nav
        daily_return = (
            0.0
            if previous is None or previous.nav == 0
            else nav / previous.nav - 1
        )
        running_nav_high = max(running_nav_high, nav)
        drawdown = 0.0 if nav == 0 else nav / running_nav_high - 1
        nav_index = nav / parameters.initial_cash * 100
        initial_close = (
            clean_close if previous is None else rows[0].clean_close
        )
        close_index = (
            clean_close / initial_close * 100
            if clean_close is not None and initial_close not in (None, 0)
            else None
        )
        trade = "BUY" if is_buy and position > 0 else "SELL" if is_sell else ""

        rows.append(
            BacktestRow(
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                clean_open=clean_open,
                clean_high=clean_high,
                clean_low=clean_low,
                clean_close=clean_close,
                tr=tr,
                atr=atr,
                past_high=past_high,
                past_low=past_low,
                signal=signal,
                trade_price=trade_price,
                stop_loss=stop_loss,
                position=position,
                cash=cash,
                stock_value=stock_value,
                trading_cost=trading_cost,
                daily_pnl=daily_pnl,
                nav=nav,
                daily_return=daily_return,
                drawdown=drawdown,
                nav_index=nav_index,
                close_index=close_index,
                trade=trade,
            )
        )

    returns = [row.daily_return for row in rows[1:]]
    annualized_volatility = (
        statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 2 else 0.0
    )
    average_return = statistics.mean(returns) if returns else 0.0
    elapsed_days = _excel_serial(rows[-1].date) - _excel_serial(rows[0].date)
    annualized_return = (
        (rows[-1].nav / rows[0].nav) ** (365 / elapsed_days) - 1
        if elapsed_days
        else 0.0
    )
    summary = Summary(
        start=rows[0].date,
        end=rows[-1].date,
        ending_nav=rows[-1].nav,
        total_return=rows[-1].nav / rows[0].nav - 1,
        annualized_return=annualized_return,
        max_drawdown=min(row.drawdown for row in rows),
        annualized_volatility=annualized_volatility,
        sharpe_ratio=(
            average_return * 252 / annualized_volatility
            if annualized_volatility
            else 0.0
        ),
        buys=sum(row.trade == "BUY" for row in rows),
        sells=sum(row.trade == "SELL" for row in rows),
        time_in_market=statistics.mean(row.signal for row in rows),
        ending_position=rows[-1].position,
        total_trading_cost=sum(row.trading_cost for row in rows),
        nav_check=(
            "PASS"
            if abs(rows[-1].nav - (rows[-1].cash + rows[-1].stock_value)) < 0.01
            else "FAIL"
        ),
        minimum_cash=min(row.cash for row in rows),
        current_signal="持仓" if rows[-1].signal == 1 else "空仓",
    )
    return rows, summary


def load_reference_xlsx(path: str | Path) -> list[PriceBar]:
    """Load the raw A:E price area from the reference-style workbook."""
    with zipfile.ZipFile(path) as book:
        cells = sheet_cells(
            book, "xl/worksheets/sheet1.xml", shared_strings(book)
        )
    bars: list[PriceBar] = []
    row_number = 6
    while f"A{row_number}" in cells:
        bars.append(
            PriceBar(
                date=cells[f"A{row_number}"]["value"],
                open=cells.get(f"B{row_number}", {}).get("value"),
                high=cells.get(f"C{row_number}", {}).get("value"),
                low=cells.get(f"D{row_number}", {}).get("value"),
                close=cells.get(f"E{row_number}", {}).get("value"),
            )
        )
        row_number += 1
    return bars


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def load_raw_data_xlsx(path: str | Path) -> list[Instrument]:
    """Load every Date/open/high/low/close block from the Raw_data workbook."""
    with zipfile.ZipFile(path) as book:
        cells = sheet_cells(
            book, "xl/worksheets/sheet1.xml", shared_strings(book)
        )

    instruments: list[Instrument] = []
    start_column = 1
    while start_column <= 16384:
        columns = [_column_name(start_column + offset) for offset in range(5)]
        headers = [
            str(cells.get(f"{column}5", {}).get("value") or "").strip().lower()
            for column in columns
        ]
        if headers != ["date", "open", "high", "low", "close"]:
            start_column += 1
            continue

        name = str(cells.get(f"{columns[1]}2", {}).get("value") or "").strip()
        symbol = str(cells.get(f"{columns[1]}3", {}).get("value") or "").strip()
        raw_bars: list[PriceBar] = []
        row_number = 6
        while f"{columns[0]}{row_number}" in cells:
            raw_bars.append(
                PriceBar(
                    date=cells[f"{columns[0]}{row_number}"]["value"],
                    open=cells.get(f"{columns[1]}{row_number}", {}).get("value"),
                    high=cells.get(f"{columns[2]}{row_number}", {}).get("value"),
                    low=cells.get(f"{columns[3]}{row_number}", {}).get("value"),
                    close=cells.get(f"{columns[4]}{row_number}", {}).get("value"),
                )
            )
            row_number += 1

        first_valid = next(
            (
                index
                for index, bar in enumerate(raw_bars)
                if all(
                    _positive(value) is not None
                    for value in (bar.open, bar.high, bar.low, bar.close)
                )
            ),
            None,
        )
        if first_valid is not None:
            instruments.append(
                Instrument(name=name, symbol=symbol, bars=tuple(raw_bars[first_valid:]))
            )
        start_column += 5
    if not instruments:
        raise ValueError("没有在 Raw_data 中找到 Date/open/high/low/close 数据块")
    return instruments


def select_instrument(
    instruments: Sequence[Instrument], query: str
) -> Instrument:
    normalized = query.strip().casefold()
    exact = [
        item
        for item in instruments
        if normalized in {item.name.casefold(), item.symbol.casefold()}
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        item
        for item in instruments
        if normalized in item.name.casefold() or normalized in item.symbol.casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    choices = "、".join(f"{item.name} ({item.symbol})" for item in instruments)
    raise ValueError(f"无法唯一识别 {query!r}；可选标的：{choices}")


def safe_filename(instrument: Instrument) -> str:
    stem = f"{instrument.symbol}_{instrument.name}"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")


def load_csv(path: str | Path) -> list[PriceBar]:
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError("CSV 没有表头")
        lowered = {name.strip().lower(): name for name in reader.fieldnames}
        required = {"date", "open", "high", "low", "close"}
        if not required.issubset(lowered):
            raise ValueError("CSV 表头必须包含 Date, open, high, low, close")

        result = []
        for record in reader:
            raw_date = record[lowered["date"]].strip()
            try:
                parsed_date: object = datetime.fromisoformat(raw_date).date()
            except ValueError:
                parsed_date = float(raw_date)
            result.append(
                PriceBar(
                    date=parsed_date,
                    open=_csv_number(record[lowered["open"]]),
                    high=_csv_number(record[lowered["high"]]),
                    low=_csv_number(record[lowered["low"]]),
                    close=_csv_number(record[lowered["close"]]),
                )
            )
    return result


def _csv_number(value: str) -> float | None:
    value = value.strip()
    return None if value == "" else float(value)


OUTPUT_COLUMNS = [
    "Date",
    "open",
    "high",
    "low",
    "close",
    "Clean Open",
    "Clean High",
    "Clean Low",
    "Clean Close",
    "TR",
    "ATR",
    "Past High",
    "Past Low",
    "Signal",
    "Trade Price",
    "Stop Loss",
    "Position",
    "Cash",
    "Stock Value",
    "Trading Cost",
    "Daily P&L",
    "NAV",
    "Daily Return",
    "Drawdown",
    "NAV Index",
    "Close Index",
    "Trade",
]


def write_results_csv(rows: Sequence[BacktestRow], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.writer(destination)
        writer.writerow(OUTPUT_COLUMNS)
        for row in rows:
            values = list(asdict(row).values())
            writer.writerow(["" if value is None else value for value in values])


def summary_dict(summary: Summary) -> Mapping[str, object]:
    return asdict(summary)
