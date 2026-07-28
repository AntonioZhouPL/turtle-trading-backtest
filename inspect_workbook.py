"""Small, read-only OOXML helpers used by the Raw Data loader."""

from __future__ import annotations

import zipfile
from xml.etree import ElementTree as ET

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    """Return the workbook shared-string table, or an empty list if absent."""
    try:
        payload = book.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    return [
        "".join(node.text or "" for node in item.iter(f"{MAIN}t"))
        for item in root.findall(f"{MAIN}si")
    ]


def cell_value(cell: ET.Element, strings: list[str]) -> object:
    """Decode one OOXML cell value into a basic Python value."""
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
    """Read cell values from one worksheet XML member."""
    result: dict[str, dict[str, object]] = {}
    with book.open(sheet_path) as source:
        for _, cell in ET.iterparse(source, events=("end",)):
            if cell.tag != f"{MAIN}c":
                continue
            ref = cell.get("r")
            if ref is not None:
                result[ref] = {"value": cell_value(cell, strings)}
            cell.clear()
    return result
