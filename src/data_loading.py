"""Loading the raw Kaggle CSV files and profiling them."""
import pandas as pd

from .config import POPULATION_FILE, RAW_DIR, RAW_FILES


def check_raw_files() -> list[str]:
    """Return the names of raw files that are missing from Data/Raw (empty list = all present)."""
    names = list(RAW_FILES.values()) + [POPULATION_FILE]
    return [n for n in names if not (RAW_DIR / n).exists()]


def load_raw() -> dict[str, pd.DataFrame]:
    """Read the nine raw Olist CSV files into a dict of DataFrames (no type changes)."""
    missing = check_raw_files()
    if missing:
        raise FileNotFoundError(
            f"Missing raw files in {RAW_DIR}: {missing}. "
            "Download the dataset from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
            "and unzip the CSV files into Data/Raw/ (see README.md)."
        )
    return {name: pd.read_csv(RAW_DIR / file) for name, file in RAW_FILES.items()}


def load_population() -> pd.DataFrame:
    """State population (IBGE estimate, 1 July 2017). Columns: states, state_population."""
    return pd.read_csv(RAW_DIR / POPULATION_FILE)


def profile_table(name: str, df: pd.DataFrame, key: list[str] | None = None) -> dict:
    """One-row profile of a table: size, duplicates, key uniqueness and missing values."""
    missing = df.isna().sum()
    return {
        "table": name,
        "rows": len(df),
        "columns": df.shape[1],
        "exact_duplicates": int(df.duplicated().sum()),
        "key": ", ".join(key) if key else "(none)",
        "duplicate_keys": int(df.duplicated(subset=key).sum()) if key else None,
        "columns_with_missing": int((missing > 0).sum()),
        "missing_cells_%": round(missing.sum() / df.size * 100, 2),
    }


def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    """Missing count and percent for the columns that have missing values."""
    out = pd.DataFrame({"missing_count": df.isna().sum(), "missing_%": (df.isna().mean() * 100).round(2)})
    return out[out["missing_count"] > 0].sort_values("missing_count", ascending=False)
