"""Cleaning and feature engineering for the eight Olist tables.

This module reproduces, as functions, the decisions documented in the team's cleaning notebook
(Notebooks/2_data_cleaning.ipynb). The principles are:
  * preserve rows by default (only exact geolocation duplicates and out-of-Brazil points are removed),
  * set provably impossible values to missing instead of guessing,
  * keep and flag ambiguous cases (flag_* columns),
  * no imputation.
"""
import numpy as np
import pandas as pd

from .config import PROCESSED_DIR

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
CITY_PATTERN = r"[a-z0-9]+(?:[ '\-][a-z0-9]+)*"


def _zip_to_str(s: pd.Series) -> pd.Series:
    """ZIP prefixes are identifiers: keep them as 5-character strings with leading zeros."""
    return s.astype("string").str.zfill(5)


def _standardize_city(s: pd.Series) -> pd.Series:
    """Lowercase, remove accents and odd symbols, collapse spaces (the format used by customers)."""
    return (
        s.str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("ascii")
        .str.replace(r"[^a-z0-9\s'\-]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


# ----------------------------------------------------------------------------------------------
# orders
# ----------------------------------------------------------------------------------------------
def clean_orders(orders: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Datetime conversion, timestamp anomaly flags and delivery features."""
    df = orders.copy()
    log = {}

    # two malformed delivery timestamps in the source file
    df["order_delivered_customer_date"] = df["order_delivered_customer_date"].replace({
        "2018-02-22 007:55": "2018-02-22 00:07:55",
        "2018-06-18:0 23:07:33": "2018-06-18 23:07:33",
    })
    for col in ORDER_DATE_COLS:
        df[col] = pd.to_datetime(df[col], format=TS_FORMAT)

    # chronological anomalies: impossible ones are set to NaT, ambiguous ones are kept and flagged
    df["flag_carrier_before_purchase"] = (
        df["order_delivered_carrier_date"].notna()
        & (df["order_delivered_carrier_date"] < df["order_purchase_timestamp"])
    )
    df["flag_customer_before_carrier"] = (
        df["order_delivered_customer_date"].notna()
        & df["order_delivered_carrier_date"].notna()
        & (df["order_delivered_customer_date"] < df["order_delivered_carrier_date"])
    )
    df["flag_approval_after_customer"] = (
        df["order_approved_at"].notna()
        & df["order_delivered_customer_date"].notna()
        & (df["order_approved_at"] > df["order_delivered_customer_date"])
    )
    df.loc[df["flag_customer_before_carrier"], "order_delivered_carrier_date"] = pd.NaT
    df.loc[df["flag_approval_after_customer"], "order_approved_at"] = pd.NaT
    df["flag_approval_after_carrier"] = (
        df["order_approved_at"].notna()
        & df["order_delivered_carrier_date"].notna()
        & (df["order_approved_at"] > df["order_delivered_carrier_date"])
    )
    log["timestamps_set_to_NaT"] = int(df["flag_customer_before_carrier"].sum() + df["flag_approval_after_customer"].sum())
    for c in [c for c in df.columns if c.startswith("flag_")]:
        log[c] = int(df[c].sum())

    # date features
    ts = df["order_purchase_timestamp"]
    df["order_year"] = ts.dt.year
    df["order_month"] = ts.dt.month
    df["order_day"] = ts.dt.day
    df["order_weekday"] = ts.dt.day_name()

    # delivery features
    df["delivery_duration_days"] = (
        df["order_delivered_customer_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    # the estimated date has no time part (00:00), so compare calendar dates:
    # an order delivered at 14:00 on the promised day is on time, not 0.58 days late
    df["delivery_delay_days"] = (
        df["order_delivered_customer_date"].dt.normalize() - df["order_estimated_delivery_date"]
    ).dt.days.astype("Int64")
    df["is_late"] = (df["delivery_delay_days"] > 0).astype("boolean")
    df["approval_hours"] = (df["order_approved_at"] - df["order_purchase_timestamp"]).dt.total_seconds() / 3600
    df["carrier_to_customer_days"] = (
        df["order_delivered_customer_date"] - df["order_delivered_carrier_date"]
    ).dt.total_seconds() / 86400
    return df, log


# ----------------------------------------------------------------------------------------------
# customers, products, order_items
# ----------------------------------------------------------------------------------------------
def clean_customers(customers: pd.DataFrame) -> pd.DataFrame:
    df = customers.copy()
    df["customer_zip_code_prefix"] = _zip_to_str(df["customer_zip_code_prefix"])
    return df


def clean_products(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """Translate categories to English, label missing categories 'unknown', fix column names."""
    df = products.merge(translation, on="product_category_name", how="left")
    manual = {  # two categories missing from the translation table
        "pc_gamer": "pc_gamer",
        "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
    }
    df["product_category_name"] = df["product_category_name_english"].fillna(
        df["product_category_name"].map(manual)
    )
    df = df.drop(columns="product_category_name_english")
    df["product_category_name"] = df["product_category_name"].fillna("unknown")
    df = df.rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })
    assert len(df) == len(products), "translation join changed the row count"
    return df


def clean_order_items(order_items: pd.DataFrame) -> pd.DataFrame:
    df = order_items.copy()
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], format=TS_FORMAT)
    return df


# ----------------------------------------------------------------------------------------------
# geolocation, sellers
# ----------------------------------------------------------------------------------------------
def clean_geolocation(geolocation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Remove exact duplicates and out-of-Brazil points, standardize cities, build one row per prefix."""
    df = geolocation.copy()
    log = {"rows_raw": len(df)}
    df["geolocation_zip_code_prefix"] = _zip_to_str(df["geolocation_zip_code_prefix"])
    df = df.drop_duplicates()
    log["rows_after_first_dedup"] = len(df)
    df["geolocation_city"] = _standardize_city(df["geolocation_city"])
    df = df.drop_duplicates().reset_index(drop=True)          # standardization creates new duplicates
    log["rows_after_city_dedup"] = len(df)
    in_brazil = df["geolocation_lat"].between(-33.75, 5.27) & df["geolocation_lng"].between(-73.99, -34.79)
    log["out_of_brazil_removed"] = int((~in_brazil).sum())
    df = df.loc[in_brazil].reset_index(drop=True)
    log["rows_clean"] = len(df)

    # one row per ZIP prefix (median coordinates are robust to a few distant points)
    prefix = (
        df.groupby("geolocation_zip_code_prefix")
        .agg(
            lat=("geolocation_lat", "median"),
            lng=("geolocation_lng", "median"),
            city=("geolocation_city", lambda s: s.mode().iloc[0]),
            state=("geolocation_state", lambda s: s.mode().iloc[0]),
            n_points=("geolocation_lat", "size"),
            n_states=("geolocation_state", "nunique"),
        )
        .reset_index()
    )
    log["prefixes"] = len(prefix)
    return df, prefix, log


def clean_sellers(sellers: pd.DataFrame) -> pd.DataFrame:
    df = sellers.copy()
    df["seller_zip_code_prefix"] = _zip_to_str(df["seller_zip_code_prefix"])
    df["seller_city"] = _standardize_city(df["seller_city"])
    return df.drop_duplicates().reset_index(drop=True)


# ----------------------------------------------------------------------------------------------
# payments, reviews
# ----------------------------------------------------------------------------------------------
def clean_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """Two credit-card records with 0 installments are invalid: set to missing (nullable Int64)."""
    df = payments.copy()
    df["payment_installments"] = df["payment_installments"].astype("Int64")
    df.loc[df["payment_installments"] == 0, "payment_installments"] = pd.NA
    return df


def clean_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    """Convert dates. Shared review_id values (one review attached to several orders) are kept."""
    df = reviews.copy()
    for col in ["review_creation_date", "review_answer_timestamp"]:
        df[col] = pd.to_datetime(df[col], format=TS_FORMAT)
    return df


# ----------------------------------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------------------------------
def run_cleaning(raw: dict[str, pd.DataFrame], save: bool = True) -> tuple[dict[str, pd.DataFrame], dict]:
    """Clean every table, optionally save them as Parquet, and return (tables, log)."""
    log = {}
    orders, log["orders"] = clean_orders(raw["orders"])
    geolocation, geolocation_prefix, log["geolocation"] = clean_geolocation(raw["geolocation"])
    tables = {
        "orders_clean": orders,
        "customers_clean": clean_customers(raw["customers"]),
        "products_clean": clean_products(raw["products"], raw["category_translation"]),
        "order_items_clean": clean_order_items(raw["order_items"]),
        "geolocation_clean": geolocation,
        "geolocation_prefix": geolocation_prefix,
        "sellers_clean": clean_sellers(raw["sellers"]),
        "payments_clean": clean_payments(raw["payments"]),
        "reviews_clean": clean_reviews(raw["reviews"]),
    }
    if save:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            df.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
    return tables, log


def load_processed() -> dict[str, pd.DataFrame]:
    """Load the cleaned Parquet tables (types are stored in the files)."""
    names = ["orders_clean", "customers_clean", "products_clean", "order_items_clean", "geolocation_clean",
             "geolocation_prefix", "sellers_clean", "payments_clean", "reviews_clean"]
    return {n: pd.read_parquet(PROCESSED_DIR / f"{n}.parquet") for n in names}


def check_merge(left: pd.DataFrame, right: pd.DataFrame, on, name: str, sum_col: str | None = None,
                how: str = "left") -> dict:
    """Merge and report row counts before/after, unmatched rows and (optionally) a preserved total."""
    merged = left.merge(right, on=on, how=how, indicator=True)
    row = {
        "join": name,
        "rows_before": len(left),
        "rows_after": len(merged),
        "row_change": len(merged) - len(left),
        "unmatched_left_rows": int((merged["_merge"] == "left_only").sum()),
    }
    if sum_col:
        row[f"{sum_col}_change"] = round(float(merged[sum_col].sum() - left[sum_col].sum()), 2)
    return row


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    """Great-circle distance in km between two sets of coordinates (vectorized)."""
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))
