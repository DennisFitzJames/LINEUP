from __future__ import annotations

import csv
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def normalise_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def pick_value(row: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    normalised = {normalise_header(key): value for key, value in row.items()}
    for alias in aliases:
        key = normalise_header(alias)
        if key in normalised:
            return normalised[key]
    return default


def _column_number(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref or "")
    if not letters:
        return 0

    result = 0
    for character in letters.group(1):
        result = result * 26 + ord(character) - 64
    return result


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        values.append(
            "".join(
                element.text or ""
                for element in item.iter(f"{{{MAIN_NS}}}t")
            )
        )
    return values


def _worksheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    relationship_map = {
        relation.attrib["Id"]: relation.attrib["Target"].lstrip("/")
        for relation in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }

    result = []
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        return result

    for sheet in sheets:
        relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        target = relationship_map.get(relationship_id, "")
        if target and not target.startswith("xl/"):
            target = f"xl/{target}"
        result.append((sheet.attrib.get("name", ""), target))

    return result


def read_xlsx_rows(path: Path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        worksheets = _worksheet_paths(archive)
        if not worksheets:
            return []

        selected_path = ""
        if sheet_name:
            for name, target in worksheets:
                if name.strip().lower() == sheet_name.strip().lower():
                    selected_path = target
                    break
        if not selected_path:
            selected_path = worksheets[0][1]

        root = ET.fromstring(archive.read(selected_path))
        matrix: list[list[Any]] = []

        for row in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
            values: dict[int, Any] = {}
            for cell in row.findall(f"{{{MAIN_NS}}}c"):
                column = _column_number(cell.attrib.get("r", ""))
                cell_type = cell.attrib.get("t", "")
                value_element = cell.find(f"{{{MAIN_NS}}}v")
                value: Any = ""

                if cell_type == "inlineStr":
                    inline = cell.find(f"{{{MAIN_NS}}}is")
                    if inline is not None:
                        value = "".join(
                            element.text or ""
                            for element in inline.iter(f"{{{MAIN_NS}}}t")
                        )
                elif value_element is not None:
                    value = value_element.text or ""
                    if cell_type == "s" and value != "":
                        value = shared[int(value)]
                    elif cell_type == "b":
                        value = value == "1"

                if column > 0:
                    values[column] = value

            if values:
                matrix.append([
                    values.get(column, "")
                    for column in range(1, max(values) + 1)
                ])

    return matrix_to_dicts(matrix)


def matrix_to_dicts(matrix: list[list[Any]]) -> list[dict[str, Any]]:
    header_index = None
    for index, row in enumerate(matrix):
        if any(str(value or "").strip() for value in row):
            header_index = index
            break

    if header_index is None:
        return []

    headers = [str(value or "").strip() for value in matrix[header_index]]
    rows: list[dict[str, Any]] = []

    for raw_row in matrix[header_index + 1:]:
        if not any(str(value or "").strip() for value in raw_row):
            continue

        padded = raw_row + [""] * max(0, len(headers) - len(raw_row))
        rows.append({
            headers[index] or f"column_{index + 1}": padded[index]
            for index in range(len(headers))
        })

    return rows


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as infile:
        return list(csv.DictReader(infile))


def _read_text_lines(path: Path) -> list[str]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as infile:
                return infile.readlines()
        except UnicodeDecodeError:
            continue

    with open(path, "r", encoding="utf-8", errors="replace") as infile:
        return infile.readlines()


def read_pipe_rows(path: Path) -> list[dict[str, Any]]:
    matrix: list[list[str]] = []

    for line in _read_text_lines(path):
        line = line.strip()
        if not line.startswith("|"):
            continue
        values = [part.strip() for part in line.split("|")[1:-1]]
        if values:
            matrix.append(values)

    return matrix_to_dicts(matrix)


def read_rows(path: Path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()

    if suffix == ".xlsx":
        return read_xlsx_rows(path, sheet_name=sheet_name)
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix in {".txt", ".dat"}:
        return read_pipe_rows(path)

    raise ValueError(f"Unsupported table format: {path.suffix}")
