"""File parser para CSV/XLSX con auto-detección de columnas."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Patrones para detectar columna de ID
_ID_PATTERNS = {
    "asin": re.compile(r"(?i)\basin\b"),
    "upc": re.compile(r"(?i)\b(upc|barcode|gtin)\b"),
    "ean": re.compile(r"(?i)\bean\b"),
    "isbn": re.compile(r"(?i)\bisbn\b"),
    "generic": re.compile(r"(?i)\b(id|sku|code|product.?id|item.?id)\b"),
}

# Patrones para detectar columna de costo
_COST_PATTERN = re.compile(r"(?i)\b(cost|price|wholesale|unit.?cost|buy.?price|net.?cost|sale.?price|my.?cost)\b")

# Regex para detectar tipo de ID por valor
_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
_UPC_RE = re.compile(r"^\d{11,12}$")
_EAN_RE = re.compile(r"^\d{13}$")
_ISBN10_RE = re.compile(r"^\d{9}[0-9X]$")
_ISBN13_RE = re.compile(r"^97[89]\d{10}$")


@dataclass
class ParsedRow:
    row_number: int
    product_id: str
    id_type: str  # asin, upc, ean, isbn, unknown
    cost_price: float | None = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class ParsedFile:
    rows: list[ParsedRow]
    id_column: str
    cost_column: str | None
    detected_id_type: str  # tipo mayoritario
    total_rows: int
    warnings: list[str] = field(default_factory=list)


def detect_id_type(value: str) -> str:
    """Detecta el tipo de ID de un valor individual."""
    v = str(value).strip()
    if _ASIN_RE.match(v):
        return "asin"
    if _ISBN13_RE.match(v):
        return "isbn"
    if _EAN_RE.match(v):
        return "ean"
    if _UPC_RE.match(v):
        return "upc"
    if _ISBN10_RE.match(v):
        return "isbn"
    return "unknown"


def _detect_id_column(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Detecta columna de ID por nombre y luego por contenido."""
    columns = list(df.columns)

    # Paso 1: Match por nombre de columna (prioridad: asin > upc > ean > isbn > generic)
    for id_type in ["asin", "upc", "ean", "isbn", "generic"]:
        pattern = _ID_PATTERNS[id_type]
        for col in columns:
            if pattern.search(str(col)):
                return col, id_type if id_type != "generic" else None

    # Paso 2: Match por contenido (primeras 20 filas)
    sample = df.head(20)
    for col in columns:
        values = sample[col].dropna().astype(str)
        if len(values) == 0:
            continue
        types = [detect_id_type(v) for v in values]
        known = [t for t in types if t != "unknown"]
        if len(known) >= len(values) * 0.5:
            return col, None  # tipo se detectará por valor

    return None, None


def _detect_cost_column(df: pd.DataFrame) -> str | None:
    """Detecta columna de costo por nombre."""
    for col in df.columns:
        if _COST_PATTERN.search(str(col)):
            return col
    return None


def _detect_majority_type(rows: list[ParsedRow]) -> str:
    """Determina el tipo de ID mayoritario."""
    type_counts: dict[str, int] = {}
    for row in rows:
        t = row.id_type
        if t != "unknown":
            type_counts[t] = type_counts.get(t, 0) + 1
    if not type_counts:
        return "unknown"
    return max(type_counts, key=type_counts.get)


def _clean_numeric(val) -> float | None:
    """Limpia un valor numérico: quita símbolos de moneda, espacios."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    # Quitar símbolos de moneda de un char
    s = re.sub(r"^[£$€¥₹]", "", s).strip()
    # Quitar comas de miles
    s = s.replace(",", "")
    try:
        v = float(s)
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


def _clean_product_id(val) -> str:
    """Limpia un product ID: strip, quitar espacios internos, pad zeros."""
    s = str(val).strip().replace(" ", "")
    # Pad UPC a 12 dígitos si es numérico y tiene 11
    if s.isdigit() and len(s) == 11:
        s = "0" + s
    return s


def parse_file(file_path: str | Path) -> ParsedFile:
    """Parsea un archivo CSV/XLSX y auto-detecta columnas."""
    path = Path(file_path)
    warnings: list[str] = []

    # Leer archivo según extensión
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif ext in (".xlsx", ".xls"):
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        df = pd.read_excel(path, dtype=str, keep_default_na=False, engine=engine)
    elif ext in (".tsv", ".tab"):
        df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Formato no soportado: {ext}")

    # Eliminar filas completamente vacías
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        return ParsedFile(rows=[], id_column="", cost_column=None,
                          detected_id_type="unknown", total_rows=0,
                          warnings=["Archivo vacío"])

    # Detectar columnas
    id_col, hinted_type = _detect_id_column(df)
    if id_col is None:
        # Fallback: usar primera columna
        id_col = df.columns[0]
        warnings.append(f"No se detectó columna de ID, usando '{id_col}'")

    cost_col = _detect_cost_column(df)

    # Parsear filas
    rows: list[ParsedRow] = []
    for idx, row in df.iterrows():
        raw_id = _clean_product_id(row.get(id_col, ""))
        if not raw_id:
            warnings.append(f"Fila {idx + 2}: ID vacío, saltando")
            continue

        id_type = hinted_type or detect_id_type(raw_id)

        cost = None
        if cost_col:
            cost = _clean_numeric(row.get(cost_col))

        rows.append(ParsedRow(
            row_number=int(idx) + 2,  # +2 por header + 0-index
            product_id=raw_id,
            id_type=id_type,
            cost_price=cost,
            raw_data=row.to_dict(),
        ))

    detected_type = _detect_majority_type(rows)

    logger.info(
        "Parsed %s: %d rows, id_col='%s', cost_col='%s', type='%s'",
        path.name, len(rows), id_col, cost_col, detected_type,
    )

    return ParsedFile(
        rows=rows,
        id_column=id_col,
        cost_column=cost_col,
        detected_id_type=detected_type,
        total_rows=len(rows),
        warnings=warnings,
    )
