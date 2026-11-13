"""Project paths and shared constants.

All paths are built from the location of this file, so the project works from any
working directory and on any operating system.
"""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "Data" / "Raw"
PROCESSED_DIR = PROJECT_ROOT / "Data" / "Processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TABLES_DIR = OUTPUTS_DIR / "tables"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}
# Not part of the Kaggle dataset: IBGE population estimates (1 July 2017), used for per-capita metrics
POPULATION_FILE = "brazil_states_population.csv"

# Valid analysis window for time trends. Months before / after it are incomplete (data collection
# started in Sep 2016 with a gap in Nov 2016, and Sep-Oct 2018 only contain 20 leftover orders).
VALID_START = pd.Timestamp("2017-01-01")
VALID_END = pd.Timestamp("2018-08-31 23:59:59")

FAILED_STATUSES = ["canceled", "unavailable"]
IN_PROGRESS_STATUSES = ["shipped", "invoiced", "processing", "approved", "created"]

# Brazilian macro-regions (IBGE)
REGION_OF_STATE = {
    "AC": "North", "AP": "North", "AM": "North", "PA": "North", "RO": "North", "RR": "North", "TO": "North",
    "AL": "Northeast", "BA": "Northeast", "CE": "Northeast", "MA": "Northeast", "PB": "Northeast",
    "PE": "Northeast", "PI": "Northeast", "RN": "Northeast", "SE": "Northeast",
    "DF": "Center-West", "GO": "Center-West", "MT": "Center-West", "MS": "Center-West",
    "ES": "Southeast", "MG": "Southeast", "RJ": "Southeast", "SP": "Southeast",
    "PR": "South", "RS": "South", "SC": "South",
}


def ensure_output_dirs() -> None:
    """Create the output folders if they do not exist yet."""
    for d in (PROCESSED_DIR, CHARTS_DIR, TABLES_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
