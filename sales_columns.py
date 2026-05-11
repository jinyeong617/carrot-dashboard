"""Normalize Excel column names and map common aliases to expected Korean headers."""

from __future__ import annotations

import pandas as pd

# Canonical names used across dailygraph / graph / sales_stats
STREAMLIT_REQUIRED_COLUMNS = ("상품", "매출", "분류", "날짜")
GRAPH_REQUIRED_COLUMNS = ("상품", "매출", "분류")

# If the sheet uses English (or variants), rename when the Korean name is absent.
# (src, dst) — only applied when `src` exists and `dst` is not already a column.
_COLUMN_ALIASES: tuple[tuple[str, str], ...] = (
    ("Product", "상품"),
    ("product", "상품"),
    ("item", "상품"),
    ("Item", "상품"),
    ("상품명", "상품"),
    ("Sales", "매출"),
    ("sales", "매출"),
    ("revenue", "매출"),
    ("Revenue", "매출"),
    ("Amount", "매출"),
    ("amount", "매출"),
    ("Category", "분류"),
    ("category", "분류"),
    ("cat", "분류"),
    ("분류명", "분류"),
    ("Date", "날짜"),
    ("date", "날짜"),
    ("일자", "날짜"),
    ("거래일", "날짜"),
)


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).replace("\ufeff", "").strip() for c in out.columns]
    return out


def apply_column_aliases(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for src, dst in _COLUMN_ALIASES:
        if src in out.columns and dst not in out.columns:
            out = out.rename(columns={src: dst})
    return out


def missing_required_columns(
    df: pd.DataFrame,
    required: tuple[str, ...] = STREAMLIT_REQUIRED_COLUMNS,
) -> list[str]:
    return [c for c in required if c not in df.columns]


def format_column_help(actual: list[str]) -> str:
    return "파일에 있는 컬럼 이름:\n" + "\n".join(f"  - {repr(a)}" for a in actual)
