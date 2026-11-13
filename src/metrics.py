"""Shared metric definitions, so every section of the analysis uses the same numbers.

Definitions
-----------
* Orders ................ unique ``order_id`` in ``orders`` (99,441). Payment *records* are never counted as orders.
* Unique customers ...... ``nunique(customer_unique_id)``. ``customer_id`` is one id per order, not per person.
* Product sales ......... ``SUM(price)`` over ``order_items`` (freight excluded). Used to rank categories and sellers.
* Revenue (GMV) ......... ``SUM(price + freight_value)`` over ``order_items``: what customers were charged for
                          items and shipping. Built per order first, so it never passes through ``payments``.
* Average order value ... Revenue / number of orders that have items  (= mean of per-order revenue).
* Amount paid ........... ``SUM(payment_value)`` from ``payments`` (includes installment interest). Reported
                          separately from revenue and never added to it.
* Review score .......... one score per order: the latest answered review of that order.
* Delivered orders ...... ``order_status == 'delivered'`` with a customer delivery date.
* Delivery time ......... ``order_delivered_customer_date - order_purchase_timestamp`` (days).
* Late .................. delivery *date* after ``order_estimated_delivery_date`` (calendar days).
"""
import pandas as pd

from .config import FAILED_STATUSES, REGION_OF_STATE

METRIC_DEFINITIONS = pd.DataFrame(
    [
        ("Orders", "nunique(order_id) in orders", "orders"),
        ("Unique customers", "nunique(customer_unique_id)", "customers"),
        ("Product sales", "SUM(price)", "order_items"),
        ("Revenue (GMV)", "SUM(price + freight_value), aggregated per order", "order_items"),
        ("Average order value (AOV)", "Revenue / orders with items", "order_items"),
        ("Amount paid", "SUM(payment_value), aggregated per order (includes installment interest)", "payments"),
        ("Review score", "latest review per order (1-5)", "reviews"),
        ("Negative review", "review score 1 or 2", "reviews"),
        ("Delivered order", "status 'delivered' and customer delivery date present", "orders"),
        ("Delivery time", "delivered_customer_date - purchase_timestamp (days)", "orders"),
        ("Late order", "delivery date > estimated delivery date (calendar days)", "orders"),
    ],
    columns=["metric", "definition", "source table"],
)


def latest_review_per_order(reviews: pd.DataFrame) -> pd.DataFrame:
    """One row per order: the review answered last (the customer's final opinion)."""
    return (
        reviews.sort_values(["order_id", "review_answer_timestamp"])
        .drop_duplicates("order_id", keep="last")[
            ["order_id", "review_id", "review_score", "review_creation_date", "review_answer_timestamp"]
        ]
        .reset_index(drop=True)
    )


def items_per_order(order_items: pd.DataFrame) -> pd.DataFrame:
    """One row per order with item count, sellers, product sales, freight and revenue."""
    out = order_items.groupby("order_id").agg(
        n_items=("order_item_id", "size"),
        n_sellers=("seller_id", "nunique"),
        product_sales=("price", "sum"),
        freight=("freight_value", "sum"),
        shipping_limit_date=("shipping_limit_date", "max"),
    )
    out["revenue"] = out["product_sales"] + out["freight"]
    return out.reset_index()


def payments_per_order(payments: pd.DataFrame) -> pd.DataFrame:
    """One row per order: amount paid, number of payment records, methods and installments."""
    main_type = (
        payments.sort_values(["order_id", "payment_value"], ascending=[True, False])
        .drop_duplicates("order_id")[["order_id", "payment_type"]]
        .rename(columns={"payment_type": "main_payment_type"})
    )
    agg = payments.groupby("order_id").agg(
        amount_paid=("payment_value", "sum"),
        n_payment_records=("payment_sequential", "size"),
        n_payment_methods=("payment_type", "nunique"),
        max_installments=("payment_installments", "max"),
    ).reset_index()
    return agg.merge(main_type, on="order_id", how="left")


def build_order_table(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Order-level fact table (one row per order) joining six cleaned tables safely.

    payments, reviews and items are aggregated to one row per order *before* joining, so the
    row count must stay equal to the number of orders.
    """
    orders = t["orders_clean"]
    customers = t["customers_clean"][["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                                      "customer_city", "customer_state"]]
    reviews = latest_review_per_order(t["reviews_clean"])[["order_id", "review_score"]]
    df = (
        orders.merge(customers, on="customer_id", how="left", validate="one_to_one")
        .merge(items_per_order(t["order_items_clean"]), on="order_id", how="left", validate="one_to_one")
        .merge(payments_per_order(t["payments_clean"]), on="order_id", how="left", validate="one_to_one")
        .merge(reviews, on="order_id", how="left", validate="one_to_one")
    )
    assert len(df) == len(orders), "order table must keep one row per order"
    df["customer_region"] = df["customer_state"].map(REGION_OF_STATE)
    df["is_failed"] = df["order_status"].isin(FAILED_STATUSES)
    df["is_delivered"] = (df["order_status"] == "delivered") & df["order_delivered_customer_date"].notna()
    df["is_negative_review"] = df["review_score"].le(2).where(df["review_score"].notna())
    df["purchase_month"] = df["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    return df


def revenue_summary(order_table: pd.DataFrame) -> dict:
    """Revenue, product sales, freight and AOV from the order table (orders with items only)."""
    with_items = order_table[order_table["n_items"].notna()]
    revenue = with_items["revenue"].sum()
    n = len(with_items)
    return {
        "orders_with_items": n,
        "product_sales": float(with_items["product_sales"].sum()),
        "freight": float(with_items["freight"].sum()),
        "revenue": float(revenue),
        "aov": float(revenue / n),
        "aov_check_mean": float(with_items["revenue"].mean()),
    }


def delivered(order_table: pd.DataFrame) -> pd.DataFrame:
    """Orders used for every delivery metric."""
    return order_table[order_table["is_delivered"]].copy()


def delivery_summary(order_table: pd.DataFrame) -> dict:
    d = delivered(order_table)
    late = d["is_late"].astype(bool)
    return {
        "delivered_orders": len(d),
        "mean_days": float(d["delivery_duration_days"].mean()),
        "median_days": float(d["delivery_duration_days"].median()),
        "p90_days": float(d["delivery_duration_days"].quantile(0.9)),
        "late_orders": int(late.sum()),
        "late_rate_%": float(late.mean() * 100),
        "on_estimated_day": int((d["delivery_delay_days"] == 0).sum()),
        "early_orders": int((d["delivery_delay_days"] < 0).sum()),
        "late_over_7_days": int((d["delivery_delay_days"] > 7).sum()),
    }
