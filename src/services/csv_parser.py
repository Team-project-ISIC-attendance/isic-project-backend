import csv
import io

from src.api.schemas.enrollment import ImportError_

HEADER_MAP: dict[str, str] = {
    "isic_identifier": "isic_identifier",
    "isic": "isic_identifier",
    "identifikator": "isic_identifier",
    "identifikátor": "isic_identifier",
    "cislo": "isic_identifier",
    "číslo": "isic_identifier",
    "cislo karty": "isic_identifier",
    "číslo karty": "isic_identifier",
    "karta - cip": "isic_identifier",
    "karta - čip": "isic_identifier",
    "chip": "isic_identifier",
    "čip": "isic_identifier",
    "student_id": "student_identifier",
    "student id": "student_identifier",
    "id": "student_identifier",
    "cele meno s titulmi": "full_name",
    "celé meno s titulmi": "full_name",
    "first_name": "first_name",
    "meno": "first_name",
    "krstne meno": "first_name",
    "krstné meno": "first_name",
    "last_name": "last_name",
    "priezvisko": "last_name",
    "identifikacia studia": "study_identification",
    "identifikácia štúdia": "study_identification",
    "e-mail is": "email_is",
    "email is": "email_is",
    "e-mail": "email_is",
    "email": "email_is",
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


def _normalize_header(value: str) -> str:
    return value.strip().removeprefix("\ufeff").lower()


def _normalize_headers(headers: list[str]) -> dict[int, str]:
    normalized_headers = [_normalize_header(header) for header in headers]
    has_card_column = any(
        header in {"karta - cip", "karta - čip", "cislo karty", "číslo karty"}
        for header in normalized_headers
    )
    mapping: dict[int, str] = {}
    for idx, key in enumerate(normalized_headers):
        if key == "id" and not has_card_column:
            mapping[idx] = "isic_identifier"
            continue
        if key in HEADER_MAP:
            mapping[idx] = HEADER_MAP[key]
    return mapping


def _parse_name_parts(full_name: str) -> tuple[str, str, str]:
    cleaned = full_name.strip()
    if not cleaned:
        return "", "", ""
    cleaned = cleaned.split(",", maxsplit=1)[0].strip()
    parts = cleaned.split()
    if len(parts) < 2:
        return cleaned, "", cleaned
    last_name = parts[0]
    first_name = " ".join(parts[1:])
    return cleaned, first_name, last_name


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

    for row_idx, row in enumerate(reader, start=2):
        record: dict[str, str] = {}
        for col_idx, field_name in col_map.items():
            if col_idx < len(row):
                record[field_name] = row[col_idx].strip()

        full_name_val = record.get("full_name", "").strip()
        if full_name_val:
            cleaned_name, first_name, last_name = _parse_name_parts(full_name_val)
            record["full_name"] = cleaned_name
            if not record.get("first_name"):
                record["first_name"] = first_name
            if not record.get("last_name"):
                record["last_name"] = last_name

        isic_val = record.get("isic_identifier", "").strip()
        student_id_val = record.get("student_identifier", "").strip()
        if not isic_val:
            errors.append(
                ImportError_(row=row_idx, reason="Missing card chip identifier")
            )
            continue
        if not student_id_val:
            errors.append(
                ImportError_(row=row_idx, reason="Missing student ID")
            )
            continue

        rows.append(record)

    return rows, errors
