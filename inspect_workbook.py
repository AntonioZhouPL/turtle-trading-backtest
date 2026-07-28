"""Dependency-free inspector for the reference OOXML workbook.

This is intentionally small and read-only.  It is also used by the parity tests
to read Excel's cached formula results without requiring Microsoft Excel.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL_RE = re.compile(r"([A-Z]+)(\d+)")


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{MAIN}t"))
        for item in root.findall(f"{MAIN}si")
    ]


def cell_value(cell: ET.Element, strings: list[str]) -> object:
    value = cell.find(f"{MAIN}v")
    if value is None:
        inline = cell.find(f"{MAIN}is")
        if inline is not None:
            return "".join(node.text or "" for node in inline.iter(f"{MAIN}t"))
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


def sheet_cells(
    book: zipfile.ZipFile, sheet_path: str, strings: list[str]
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    with book.open(sheet_path) as source:
        for _, cell in ET.iterparse(source, events=("end",)):
            if cell.tag != f"{MAIN}c":
                continue
            ref = cell.get("r")
            formula = cell.find(f"{MAIN}f")
            result[ref] = {
                "value": cell_value(cell, strings),
                "formula": None if formula is None else formula.text,
                "formula_type": None if formula is None else formula.get("t"),
                "formula_index": None if formula is None else formula.get("si"),
            }
            cell.clear()
    return result


def column(ref: str) -> str:
    match = CELL_RE.fullmatch(ref)
    if match is None:
        raise ValueError(ref)
    return match.group(1)


def row(ref: str) -> int:
    match = CELL_RE.fullmatch(ref)
    if match is None:
        raise ValueError(ref)
    return int(match.group(2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with zipfile.ZipFile(args.workbook) as book:
        strings = shared_strings(book)
        sheets = {
            "回测": sheet_cells(book, "xl/worksheets/sheet1.xml", strings),
            "参数清单": sheet_cells(book, "xl/worksheets/sheet2.xml", strings),
            "公式逻辑": sheet_cells(book, "xl/worksheets/sheet3.xml", strings),
        }

    if args.json:
        print(json.dumps(sheets, ensure_ascii=False, indent=2))
        return

    for name, cells in sheets.items():
        print(f"[{name}] cells={len(cells):,}")
        print("rows", min(map(row, cells)), max(map(row, cells)))
        print("columns", Counter(column(ref) for ref in cells))
        formulas = [item["formula"] for item in cells.values() if item["formula"]]
        print("formula cells", f"{len(formulas):,}")
        print()

    for name in ("参数清单", "公式逻辑"):
        print(f"[{name}: populated cells]")
        for ref, item in sorted(
            sheets[name].items(), key=lambda pair: (row(pair[0]), column(pair[0]))
        ):
            print(ref, repr(item["value"]), repr(item["formula"]))
        print()

    backtest = sheets["回测"]
    print("[回测: first three rows]")
    for ref, item in sorted(
        backtest.items(), key=lambda pair: (row(pair[0]), column(pair[0]))
    ):
        if row(ref) <= 3:
            print(ref, repr(item["value"]), repr(item["formula"]))
    print()

    print("[回测: first explicit formula by column]")
    seen: set[str] = set()
    for ref, item in sorted(
        backtest.items(), key=lambda pair: (row(pair[0]), column(pair[0]))
    ):
        col = column(ref)
        if item["formula"] and col not in seen:
            print(ref, repr(item["value"]), repr(item["formula"]))
            seen.add(col)


if __name__ == "__main__":
    main()
