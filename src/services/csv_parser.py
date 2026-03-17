import csv
import io

from src.api.schemas.enrollment import ImportError_

HEADER_MAP: dict[str, str] = {
    "isic_identifier": "isic_identifier",
    "isic": "isic_identifier",
    "id": "isic_identifier",
    "first_name": "first_name",
    "meno": "first_name",
    "last_name": "last_name",
    "priezvisko": "last_name",
}


def _decode_content(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1250")


def _detect_delimiter(first_line: str) -> str:
    if ";" in first_line:
        return ";"
    return ","


def _normalize_headers(headers: list[str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for idx, header in enumerate(headers):
        key = header.strip().lower()
        if key in HEADER_MAP:
            mapping[idx] = HEADER_MAP[key]
    return mapping


def parse_csv(
    file_content: bytes,
) -> tuple[list[dict[str, str]], list[ImportError_]]:
    text = _decode_content(file_content)
    lines = text.strip().splitlines()
    if not lines:
        return [], []

    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO(text.strip()), delimiter=delimiter)

    header_row = next(reader)
    col_map = _normalize_headers(header_row)

    rows: list[dict[str, str]] = []
    errors: list[ImportError_] = []

    for row_idx, row in enumerate(reader, start=1):
        record: dict[str, str] = {}
        for col_idx, field_name in col_map.items():
            if col_idx < len(row):
                record[field_name] = row[col_idx].strip()

        isic_val = record.get("isic_identifier", "").strip()
        if not isic_val:
            errors.append(
                ImportError_(row=row_idx, reason="Missing ISIC identifier")
            )
            continue

        rows.append(record)

    return rows, errors
