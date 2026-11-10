# Data Cleaning Report: Olist E-commerce Dataset

> Exported from `Notebooks/2_data_cleaning.ipynb` (final report section). The notebook holds the code and outputs behind every number below.

## 1. Objective and Scope

This report summarizes the cleaning and preparation of the eight Olist tables: `orders`, `customers`, `products`, `order_items`, `geolocation`, `sellers`, `payments`, and `reviews`. The goal was to produce reliable, analysis-ready tables, document every data quality issue found, and make sure tables can be joined without distorting row counts or totals.

The `product_category_name_translation` table was used only as a lookup to translate product categories.

Raw files are in `Data/Raw/`. Cleaned tables are saved to `Data/Processed/` as **Parquet** files (`<table>_clean.parquet`), plus one extra table, `geolocation_prefix.parquet`. Parquet stores the column types inside the file, so ZIP prefixes stay zero-padded strings, timestamps stay `datetime`, and flags stay boolean when the files are reloaded. A round-trip check at the end of the notebook confirms this.

## 2. Cleaning Principles

Each table went through the same workflow: **missing values → duplicates → data types → invalid/suspicious values → preparation → validation → save**. Decisions followed these rules:

1. **Preserve data by default.** Rows were deleted only when they were exact duplicates carrying no extra information, or coordinates outside Brazil.
2. **Fix only what is provably wrong.** Values that were impossible (e.g., a customer delivery before the carrier handover) were set to missing rather than guessed.
3. **Flag, don't alter, when the cause is unclear.** Ambiguous cases were kept unchanged and documented (zero payments, total mismatches, zero freight, timestamps that look like recording artefacts, and similar). Timestamp anomalies have their own `flag_*` columns.
4. **No imputation.** No missing value was filled with an estimate, because no reliable basis for one existed. (Missing product categories were labeled `"unknown"`, which is a label, not an estimate.)
5. **Every step has a recorded investigation, decision, action, and validation.**

## 3. Overview

| Table | Rows before | Rows after | Columns (before → after) | Main actions |
|---|---:|---:|---|---|
| `orders` | 99,441 | 99,441 | 8 → 21 | Datetime conversion, 2 malformed dates fixed, 84 impossible timestamps set to `NaT`, 4 anomaly flags and 9 derived features added |
| `customers` | 99,441 | 99,441 | 5 → 5 | ZIP prefix converted to 5-character string |
| `products` | 32,951 | 32,951 | 9 → 9 | Category names translated to English (2 manually), missing categories set to `"unknown"`, 2 misspelled columns renamed |
| `order_items` | 112,650 | 112,650 | 7 → 7 | `shipping_limit_date` converted to datetime |
| `geolocation` | 1,000,163 | 720,461 | 5 → 5 | ZIP prefix to string, city standardization, 279,669 exact duplicates and 33 out-of-Brazil points removed |
| `geolocation_prefix` (new) | — | 19,010 | 7 | One row per ZIP prefix with median coordinates |
| `sellers` | 3,095 | 3,095 | 4 → 4 | ZIP prefix to string, city standardization |
| `payments` | 103,886 | 103,886 | 5 → 5 | 2 invalid zero installment values set to missing (`Int64`) |
| `reviews` | 99,224 | 99,224 | 7 → 7 | Date columns converted to datetime |

Only `geolocation` lost rows. Everything else was preserved.

## 4. Results by Table

### 4.1 Orders

- **Missing values:** `order_approved_at` (160), `order_delivered_carrier_date` (1,783), and `order_delivered_customer_date` (2,965). Most belong to orders that never reached that stage (`shipped`, `canceled`, `unavailable`, `invoiced`, `processing`), so they are expected. A few are inconsistent with the status: 8 `delivered` orders had no customer delivery date, 2 had no carrier date, and 14 had no approval date. These were kept and documented.
- **Duplicates:** none. `order_id` is a valid primary key.
- **Data types:** all five timestamp columns were strings and were converted to `datetime`. Two malformed values were corrected first (`2018-02-22 007:55` and `2018-06-18:0 23:07:33`).
- **Order status:** eight valid statuses, no unexpected values. `delivered` accounts for 96,478 orders.
- **Chronological anomalies:** each case has its own flag column:

| Issue | Count | Action | Flag column |
|---|---:|---|---|
| Carrier date before purchase | 166 | Kept (median gap 0.6 hours, likely a recording artefact) | `flag_carrier_before_purchase` |
| Customer delivery before carrier date | 23 | `order_delivered_carrier_date` → `NaT` | `flag_customer_before_carrier` |
| Approval after customer delivery | 61 | `order_approved_at` → `NaT` | `flag_approval_after_customer` |
| Approval after carrier date | 1,298 | Kept (possible recording delay) | `flag_approval_after_carrier` |

- **New features:** `order_year`, `order_month`, `order_day`, `order_weekday`, `delivery_duration_days` (purchase to customer delivery), `delivery_delay_days` (calendar days between the delivery date and the estimated date; positive means late), `is_late`, `approval_hours`, and `carrier_to_customer_days`. Delivery metrics are missing for the 2,965 orders without a customer delivery date.
- **Late deliveries:** 6,534 delivered orders are late. The delay is measured in calendar days, because the estimated date has no time part. A timestamp comparison would have counted 7,826, wrongly including 1,292 orders delivered on the promised day.
- **After cleaning:** missing counts are 221 (`order_approved_at`), 1,806 (`order_delivered_carrier_date`), and 2,965 (`order_delivered_customer_date`). Among `delivered` orders, 8 lack a customer delivery date, 25 lack a carrier date, and 75 lack an approval date (the increase comes from the timestamps set to `NaT`).
- **Date coverage:** purchases from 2016-09-04 to 2018-10-17. Delivery duration ranges from 0.53 to 209.63 days, with no negative values.

### 4.2 Customers

- No missing values, no duplicate rows, and no duplicate `customer_id` (valid primary key).
- `customer_unique_id` repeats (3,345 repeated values), which is expected: one real customer gets a new `customer_id` per order. There are **99,441 `customer_id` values but 96,096 unique customers**.
- `customer_zip_code_prefix` was converted from integer to a zero-padded 5-character string so leading zeros are preserved.
- 4,119 distinct cities, already lowercase and accent-free (this format was used as the reference for the other tables). 27 states, matching the 27 Brazilian federative units.
- Every order has a matching customer.
- **Geolocation coverage:** 279 customer records (about 0.28%) have a ZIP prefix that does not exist in the cleaned `geolocation` table. They were kept, and will have missing coordinates after joining to `geolocation_prefix`.

### 4.3 Products

- **Missing values:** 610 products (1.85%) lack category, name length, description length, and photo count, always in the same rows. 2 products also lack all four physical measurements, and one of them has no information except its ID and is referenced by 17 rows in `order_items`. Since these products are tied to orders and there is no basis for imputation, they were kept.
- No duplicates (`product_id` is a valid primary key). Data types were appropriate. All numeric ranges are plausible with no negatives, except **4 products with weight 0**, which is physically implausible; they were kept and flagged.
- **Category translation:** Portuguese names were translated to English via the translation table. `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos` (13 products) were missing from that table and were translated manually. The 610 products without a category were assigned to `"unknown"`, giving 74 categories (73 real ones plus `"unknown"`). The row count is unchanged.
- The misspelled source columns `product_name_lenght` and `product_description_lenght` were renamed to `product_name_length` and `product_description_length`.

### 4.4 Order Items

- No missing values, no exact duplicates. An item is identified by (`order_id`, `order_item_id`), which has no duplicates. Repeated `order_id`, `product_id`, and `seller_id` are expected foreign keys.
- `shipping_limit_date` was converted to `datetime` with no new missing values.
- `price` ranges from 0.85 to 6,735.00 (no zero or negative prices). `freight_value` ranges from 0.00 to 409.68.
- **Zero freight:** 383 items (339 orders, 10 products, 9 sellers). The concentration in a few sellers and products points to specific shipping arrangements (e.g., free shipping) rather than random errors, so they were kept.
- **Date range caveat:** `shipping_limit_date` runs from 2016-09-19 to 2020-04-09. 4 values fall more than 90 days after the last order. They were not modified and should be used with caution.
- All `order_id`, `product_id`, and `seller_id` values exist in their parent tables (no orphans).

### 4.5 Geolocation

- No missing values. ZIP prefix converted to a zero-padded 5-character string.
- **Duplicates, first pass:** 261,831 exact duplicate rows removed (1,000,163 → 738,332). Repeated ZIP prefixes were kept, because one prefix can map to several coordinates.
- **City standardization:** trimmed whitespace, lowercased, removed accents, replaced special characters, and collapsed repeated spaces (e.g., `são paulo` and `sao paulo` merged). This reduced unique cities from 8,011 to 5,962 and matches the format of `customers` and `sellers`.
- **Duplicates, second pass:** standardization created 17,838 new exact duplicates, which were removed (738,332 → 720,494).
- **Coordinate outliers:** 33 points outside Brazil's approximate bounds were removed (720,494 → 720,461).
- 27 valid state codes. 5 city values still do not match the standard pattern (likely typos or unusual entries) and were not corrected.
- **`geolocation_prefix`:** one row per ZIP prefix (19,010 rows) with the **median** latitude and longitude, the most frequent city and state, `n_points`, and `n_states`. The median is used because in 85 prefixes the mean is more than 0.5° (about 55 km) away from it. 8 prefixes map to more than one state.

### 4.6 Sellers

- No missing values or duplicates (`seller_id` is a valid primary key).
- ZIP prefix converted to string. City names standardized (611 → 605 unique cities), creating no new duplicates. 23 of the 27 states are represented.
- Every seller appears in `order_items`. 7 seller ZIP prefixes are not found in `geolocation`, and 4 city values are still not fully standardized (informational).

### 4.7 Payments

- No missing values at load, no exact duplicates, no duplicate (`order_id`, `payment_sequential`) pairs. Repeated `order_id` values are expected (one order can have several payments).
- **Payment types:** `credit_card` (76,795), `boleto` (19,784), `voucher` (5,775), `debit_card` (1,529), and `not_defined` (3). The 3 `not_defined` records all have value 0 and belong to canceled orders, so they were kept.
- **Zero installments:** 2 credit card records had `payment_installments = 0`, which is not valid. Both have `payment_sequential = 2` with no sequence 1, so their first payment record is missing. The zeros were set to missing, and the column uses the nullable `Int64` type.
- **Zero payment values:** 6 voucher records (5 orders) have value 0. Those orders have other payment records, so the zeros may be part of multi-payment transactions. They were kept.
- **Payment vs. item totals:** after rounding to cents, 303 orders differ by more than 0.01 (264 with higher payments, 39 with lower). The absolute difference has a median of 5.90, a mean of 10.79, and a maximum of 182.81. 88.8% of these orders used more than one installment, compared with 51.5% of all orders (94.3% among orders paying more than the items), so **installment interest** is the likely cause. Nothing was changed.
- The table should be aggregated to one row per order before joining.

### 4.8 Reviews

- `review_comment_title` (88.34%) and `review_comment_message` (58.70%) are mostly missing. These fields are optional, so they were kept as `NaN`.
- No exact duplicates, but **`review_id` is not unique**: 789 IDs appear 2 to 3 times (1,603 records), identical except for `order_id`. Also, 543 orders have two review IDs and 4 have three. In **100%** of the shared review IDs, all linked orders belong to the same customer: one review was attached to several of that customer's orders. All records were kept.
- `review_creation_date` and `review_answer_timestamp` were converted to `datetime`. `review_creation_date` is the date the survey was **sent** to the customer. `review_score` is within 1 to 5, and no answer timestamp precedes its creation date.
- 768 orders have no review. Review dates end on 2018-08-31.

## 5. Join Validation

The main joins were tested for row multiplication, unmatched keys, and distortion of totals.

| Join | Cardinality | Rows before → after | Result |
|---|---|---|---|
| orders → customers | many-to-one | 99,441 → 99,441 | Safe |
| order_items → orders | many-to-one | 112,650 → 112,650 | Safe |
| order_items → products | many-to-one | 112,650 → 112,650 | Safe |
| order_items → sellers | many-to-one | 112,650 → 112,650 | Safe |
| orders → payments (raw) | one-to-many | 99,441 → 103,887 | Multiplies rows (+4,446) |
| orders → reviews (raw) | one-to-many | 99,441 → 99,992 | Multiplies rows (+551) |
| order_items → payments (raw) | many-to-many | 112,650 → 117,604 | Inflates `price` total by 617,606.61 (about 4.5%) |
| orders → payments (aggregated) | one-to-one | 99,441 → 99,441 | Safe |
| orders → reviews (latest review) | one-to-one | 99,441 → 99,441 | Safe |
| customers → geolocation_prefix | many-to-one | 99,441 → 99,441 | Safe |
| customers → geolocation (raw) | many-to-many | 99,441 → about 10,075,969 (estimated) | Never use raw |

The four many-to-one joins preserve both row counts and the `price` total (13,591,643.70). Unmatched keys are expected: 1 order without a payment, 768 orders without a review, 775 orders without items, and 279 customer records without coordinates.

## 6. Retained Data Quality Issues

These were deliberately left in the data and must be considered during analysis.

| Table | Issue | Count |
|---|---|---:|
| orders | Carrier timestamp before purchase (flagged) | 166 |
| orders | Approval timestamp after carrier timestamp (flagged) | 1,298 |
| orders | `delivered` orders missing customer delivery / carrier / approval date | 8 / 25 / 75 |
| orders | Orders without any item | 775 |
| customers | Customer records with ZIP prefix not found in `geolocation` | 279 |
| sellers | Seller records with ZIP prefix not found in `geolocation` | 7 |
| products | Products in the `"unknown"` category (no descriptive attributes) | 610 |
| products | Products without physical measurements | 2 |
| products | Products with zero weight | 4 |
| order_items | Zero freight values | 383 |
| order_items | `shipping_limit_date` far beyond the order period (up to 2020-04-09) | 4 |
| payments | `not_defined` payment type | 3 |
| payments | Zero-value voucher payments | 6 |
| payments | Missing installments (set from invalid 0) | 2 |
| payments | Orders where payment total differs from item total | 303 |
| reviews | Duplicated `review_id` values (extra rows) | 814 |
| reviews | Orders with more than one review | 547 |
| reviews | Missing comment title / message | 87,656 / 58,247 |
| geolocation | City values not fully standardized | 5 |
| geolocation | ZIP prefixes mapped to more than one state | 8 |

## 7. Rules for the Analysis Stage

1. Join `orders`, `customers`, `order_items`, `products`, and `sellers` directly. These joins are safe.
2. Aggregate `payments` (sum per order) and `reviews` (latest review per order) before joining them to `orders`. For review-level statistics, deduplicate on `review_id`.
3. Join `customers` and `sellers` to `geolocation_prefix`, never to `geolocation_clean`. Expect missing coordinates for 279 customer records and 7 sellers.
4. Never join `order_items` directly to `payments`. Use `order_items` (`price` + `freight_value`) for GMV and seller revenue, and aggregated `payments` for the amount customers paid. Do not mix the two.
5. Use `customer_unique_id`, not `customer_id`, for any customer-level analysis (repeat purchases, lifetime value).
6. Delivery-performance analysis should use only orders with a customer delivery date, and `is_late` / `delivery_delay_days` for lateness. Exclude rows flagged for a step (`flag_*`) from durations of that step.
7. Treat `"unknown"` as its own category, and exclude zero-weight products from weight-based metrics.
8. Load the processed tables with `pd.read_parquet(...)` or DuckDB's `read_parquet(...)`. No type arguments are needed.

## 8. Conclusion

All eight tables were inspected, cleaned, validated, and saved to `Data/Processed/` as Parquet. Cleaning was conservative: only exact duplicates and out-of-Brazil points in `geolocation` were removed, impossible timestamps were set to missing, and ambiguous cases were kept, flagged, and documented. Join behavior is understood, and the aggregation rules above prevent row multiplication and inflated revenue. The data is ready for exploratory analysis.
