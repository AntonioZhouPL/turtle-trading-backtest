"""Read raw OHLC data and write backtest results."""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

from turtle_backtest import BacktestRow, PriceBar

OOXML_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class Instrument:
    name: str
    symbol: str
    bars: tuple[PriceBar, ...]


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        payload = book.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    return [
        "".join(node.text or "" for node in item.iter(f"{OOXML_MAIN}t"))
        for item in root.findall(f"{OOXML_MAIN}si")
    ]


def _cell_value(cell: ET.Element, strings: list[str]) -> object:
    value = cell.find(f"{OOXML_MAIN}v")
    if value is None:
        inline = cell.find(f"{OOXML_MAIN}is")
        if inline is not None:
            return "".join(
                node.text or "" for node in inline.iter(f"{OOXML_MAIN}t")
            )
        return None

    raw = value.text or ""
    kind = cell.get("t")
    if kind == "s":
        return strings[int(raw)]
    if kind == "b":
        return raw == "1"
    if kind in {"str", "e"}:
        return raw
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw


def _sheet_cells(
    book: zipfile.ZipFile, sheet_path: str, strings: list[str]
) -> dict[str, object]:
    result: dict[str, object] = {}
    with book.open(sheet_path) as source:
        for _, cell in ET.iterparse(source, events=("end",)):
            if cell.tag != f"{OOXML_MAIN}c":
                continue
            ref = cell.get("r")
            if ref is not None:
                result[ref] = _cell_value(cell, strings)
            cell.clear()
    return result


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def load_raw_data_xlsx(path: str | Path) -> list[Instrument]:
    """Load every Date/open/high/low/close block from a Raw Data workbook."""
    with zipfile.ZipFile(path) as book:
        cells = _sheet_cells(
            book, "xl/worksheets/sheet1.xml", _shared_strings(book)
        )

    instruments: list[Instrument] = []
    start_column = 1
    while start_column <= 16_384:
        columns = [_column_name(start_column + offset) for offset in range(5)]
        headers = [
            str(cells.get(f"{column}5") or "").strip().lower()
            for column in columns
        ]
        if headers != ["date", "open", "high", "low", "close"]:
            start_column += 1
            continue

        name = str(cells.get(f"{columns[1]}2") or "").strip()
        symbol = str(cells.get(f"{columns[1]}3") or "").strip()
        raw_bars: list[PriceBar] = []
        row_number = 6
        while f"{columns[0]}{row_number}" in cells:
            raw_bars.append(
                PriceBar(
                    date=cells[f"{columns[0]}{row_number}"],
                    open=cells.get(f"{columns[1]}{row_number}"),
                    high=cells.get(f"{columns[2]}{row_number}"),
                    low=cells.get(f"{columns[3]}{row_number}"),
                    close=cells.get(f"{columns[4]}{row_number}"),
                )
            )
            row_number += 1

        first_valid = next(
            (
                index
                for index, bar in enumerate(raw_bars)
                if all(
                    _positive_number(value) is not None
                    for value in (bar.open, bar.high, bar.low, bar.close)
                )
            ),
            None,
        )
        if first_valid is not None:
            instruments.append(
                Instrument(name, symbol, tuple(raw_bars[first_valid:]))
            )
        start_column += 5

    if not instruments:
        raise ValueError(
            "没有在 Raw Data 中找到 Date/open/high/low/close 数据块"
        )
    return instruments


def load_csv(path: str | Path) -> list[PriceBar]:
    """Load Date/open/high/low/close rows from a CSV file."""
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
    """Write daily backtest rows as an Excel-friendly UTF-8 CSV."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.writer(destination)
        writer.writerow(OUTPUT_COLUMNS)
        for row in rows:
            values = list(asdict(row).values())
            writer.writerow(["" if value is None else value for value in values])
