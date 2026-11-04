# Olist Data Analysis: Project Review

**Review date:** 2026-11-04
**Branch reviewed:** `Issue-4-—-Order-Status-&-Time-Trend-Analysis` (HEAD `c494094`), plus a comparison with `main` and `shirkavand`
**Scope:** every notebook, the processed data, the DuckDB file, repo setup and git history. Where a claim could be tested, I re-ran it against the raw and processed CSVs. Those checks are marked **[verified]**, and the numbers are listed in the appendix.

---

## 1. Overall Assessment

The project is in good shape for this stage. Cleaning is the strongest part. Each table follows the same workflow (missing → duplicates → types → invalid values → validation → save), decisions are written down, nothing was deleted without a reason, and the join-validation step (`check_merge`, with row counts and `price` totals) is better than most student or junior projects. The first analysis notebook (order status and monthly trend) is clear, picks a sensible valid time window, and avoids an unfair year-over-year comparison by only comparing Jan to Aug.

The main weaknesses are:

1. **Reproducibility and data-handoff bugs.** Processed CSVs lose their types when reloaded, `requirements.txt` is empty, one validation runs on the wrong object, and the DuckDB view has a hardcoded path.
2. **Team or branch inconsistency.** Two different cleaning versions write to the same output files, and `changelog.md` on `main` describes the version that is *not* in the processed data.
3. **A few analytical conclusions are more cautious than the data requires**, and some are slightly wrong. The Black Friday effect, the reasons behind the payment mismatches and the duplicate `review_id` values can all be explained with the data already available.
4. **One metric bug:** `delivery_delay_days` counts about 1,300 orders delivered *on* the estimated day as late.

Severity legend: 🔴 affects results or correctness · 🟠 methodology or interpretation · 🟡 quality, style or maintainability

---

## 2. Inventory: What Has Been Done

| Item | Status | Notes |
|---|---|---|
| `1_understanding_data.ipynb` | Done | Structural inspection of the 9 tables (shape, dtypes, duplicates, missing values) and a written data dictionary |
| `2_data_cleaning.ipynb` | Done | 8 tables cleaned, validated and saved. Join validation and a full cleaning report are inside the notebook |
| `3_Order Status & Time Trend Analysis.ipynb` | Done (Issue 4) | Order status distribution, monthly trend, 2017 vs 2018 comparison, using DuckDB views |
| `Data/Processed/*.csv` | 8 files | 3 are tracked in git, 5 are not (see R2) |
| `Data/duckdb/olist.duckdb` | Committed on this branch | Holds only a persistent view definition, not data |
| `shirkavand.ipynb` (branch `shirkavand`) | Parallel work | A separate cleaning of sellers, payments and reviews with **different decisions** |
| `README.md`, `requirements.txt`, `changelog.md`, `Reports/` | Mostly empty | `requirements.txt` and `changelog.md` are 0 bytes on this branch, and `Reports/` only holds `.gitkeep` |

---

## 3. Critical Issues (🔴)

### C1. Processed CSVs lose types on reload, so the cleaning is partly undone
The cleaning converts ZIP prefixes to zero-padded strings and timestamps to `datetime`, then saves to **CSV**. CSV stores no types. **[verified]**
- `pd.read_csv("sellers_clean.csv")["seller_zip_code_prefix"]` comes back as `int64` (`13023, 13844, ...`), so the leading zeros are gone again.
- `orders_clean.csv` timestamps come back as `object`.

The cleaning report mentions this (rule 8: "read ZIP prefix columns as strings"), but nothing enforces it. The first person to join `customers` to `geolocation` without passing `dtype=` will either get no matches or match on the wrong keys.

**Fix:** save to **Parquet** (`df.to_parquet(...)`), which keeps `string`, `datetime64`, `bool` and nullable ints, and is also about 5–10x smaller than the current 108 MB of CSVs. DuckDB reads Parquet natively (`read_parquet`). If CSV has to stay, write a single `load_clean(table)` helper that sets dtypes and `parse_dates`, and use it everywhere.

### C2. Products validation checks the wrong DataFrame
In the products section:
```python
df = products_clean
df = df.merge(product_name_translation, ...)   # df is now a NEW object
...
df.to_csv(".../products_clean.csv")            # translated version saved (correct)
...
df = products_clean                            # validation cell: back to the UNTRANSLATED object
```
The saved file is correct **[verified: categories in the CSV are English]**. However, the validation cell and the later join validation (`check_merge(order_items_clean, products_clean, ...)`) both run on the **Portuguese, untranslated** `products_clean`. The validation passes because it checks counts, not content, so the bug goes unnoticed.

The cause is the `df = some_table` alias pattern used throughout the notebook. It works for in-place column assignment but silently breaks as soon as an operation returns a new object (`merge`, `drop_duplicates`, `reset_index`). The same thing happens in sellers (`df = df.drop_duplicates()...` does not update `sellers_clean`). There it is harmless only because 0 duplicates were found. Geolocation does it correctly by reassigning `geolocation_clean = ...` explicitly.

**Fix:** write each table's cleaning as a function, `def clean_products(raw, translation) -> pd.DataFrame`, and assign the result explicitly. At minimum, always write `products_clean = df` after a non-in-place step.

### C3. A misleading validation output in the customers section
The customers validation prints:
> `Customer ZIP prefixes not found in geolocation (informational): 99441`

This says *every* customer is missing from geolocation. The cause is that `geolocation_zip_code_prefix` was still `int64` at that point (it is converted later in the notebook), so string-to-int matching always fails. The correct number, 278, shows up later in the geolocation section, and the final report uses 278. The cell output is still wrong and would confuse a reader. Move cross-table checks to the end, after every table has been cleaned, or re-run them there.

### C4. `delivery_delay_days` counts on-time deliveries as late
`order_estimated_delivery_date` is a **date** stored at `00:00:00`, while `order_delivered_customer_date` is a full timestamp. An order delivered at 14:00 on the estimated day gets `delay = +0.58 days`, so it is "late". **[verified]** Among delivered orders:

| Definition | Late orders |
|---|---:|
| `delivered_ts > estimated_date` (current logic) | 7,826 |
| `delivered_date > estimated_date` (correct) | 6,534 |
| **Delivered on the promised day but counted late** | **1,292 (16.5% of "late")** |

This will directly bias the upcoming delivery-performance and review-score analyses.
**Fix:** `(df["order_delivered_customer_date"].dt.normalize() - df["order_estimated_delivery_date"]).dt.days`, and define `is_late = delay_days > 0`.

### C5. Two conflicting cleaning versions, and a changelog that describes the wrong one
- `shirkavand.ipynb` (branch `shirkavand`) **drops** the 3 `not_defined` payments and the 2 zero-installment payments, and runs `drop_duplicates()` on reviews.
- `2_data_cleaning.ipynb` **keeps** them (and sets the installments to `NaN`).
- Both notebooks write to the **same** `Data/Processed/payments_clean.csv` and `sellers_clean.csv`. Whichever runs last wins.
- `changelog.md` on `main` says *"Removed 3 undefined payment records and 2 credit-card records"*. That is the shirkavand version. The processed file actually in use has all 103,886 rows.
- `changelog.md` also says the full report was written to `data_cleaning_report.md`. That file does not exist. The report is only inside the notebook.

`shirkavand.ipynb` also cannot run on its own: it uses `sellers_clean` and `payments` without importing or loading anything, and its execution counts are all empty.

**Fix:** agree on one source of truth (I recommend `2_data_cleaning.ipynb`, which is the more conservative and better documented of the two). Close or archive the other notebook, and correct the changelog. If the team disagrees on a decision such as drop vs keep, record the decision and the reason once.

### C6. Branches have diverged on how the DuckDB file is handled
- `main`: adds `Data/duckdb` to `.gitignore` and **deletes** the duckdb folder (`6a42a33 drop duckdb folder`).
- This branch: **commits** `Data/duckdb/olist.duckdb` (`3f7e8c9`).

Merging Issue-4 into `main` will either cause a conflict or bring back a file the team chose to ignore. Rebase onto `main` before opening the PR and remove the file from this branch (`git rm --cached Data/duckdb/olist.duckdb`).

---

## 4. Methodology and Interpretation (🟠)

### 4.1 Notebook 1: Understanding the Data
Good: there is a clear "purpose / grain / keys" write-up for every table, and the `customer_id` vs `customer_unique_id` distinction is explained well.

Issues:
- **Factual slip:** the general report says *"the `orders` table ... connecting customers through `customer_id` and `customer_unique_id`"*. `customer_unique_id` lives only in `customers`, not in `orders`.
- **`review_creation_date` is misdescribed.** In the Olist data dictionary it is *the date the satisfaction survey was sent to the customer*, not the date the customer wrote the review. This matters later when measuring "time to review".
- **ZIP prefix called a "foreign key".** It is not a real FK: geolocation has many rows per prefix and 278 customer prefixes are missing from it. "Join key (many-to-many, aggregate first)" is more accurate.
- **The notebook looks only at structure, not at the data's content.** There are no value distributions (price, freight, review score, payment value), no outlier view, no date coverage, and no ER diagram. A single histogram grid and a relationships diagram would make the "understanding" stage complete. Right now most of the exploratory understanding is pushed into the cleaning notebook.

### 4.2 Notebook 2: Cleaning

**Orders: timestamp anomalies**
- *"Carrier before purchase" is labeled "impossible", but the gaps are tiny.* **[verified]** Of the 166 cases, the median gap is **0.6 hours** and 75% are under about 1 hour. Only a few are large (max ≈ 171 days). That pattern fits clock, timezone or batch-recording artefacts better than wrong events. Setting all 166 to `NaT` is defensible, but the treatment is **inconsistent**: "approval after carrier" (1,359 cases, the same kind of recording issue) is *kept and flagged*, while these are *deleted*. Choose one policy. My preference: keep the original values, add flag columns, and leave it to each analysis to filter.
- **The nulled values are not traceable.** The processed file has no record of which 250 timestamps were changed. Add boolean flags (e.g. `fix_carrier_before_purchase`) or keep the raw columns with a `_raw` suffix.
- **Status-based feature gaps:** the new columns `order_year`, `order_month` and so on are fine. It would also help to add `is_late` (see C4), `approval_hours` and `carrier_to_customer_days` now, so they are defined once.

**Products**
- 4 zero-weight products are flagged ✔. The column-name typos `product_name_lenght` and `product_description_lenght` are carried forward on purpose. I would rename them during cleaning, because every later query will otherwise inherit the typo.
- The markdown says *"The 610 products with no category ... will be handled in the cleaning stage"*, but this *is* the cleaning stage. Either fill them with `"unknown"` now or reword the sentence.

**Geolocation**
- Spending effort on city-name standardization (8,011 → 5,962 names) is of limited value, because joins should go through the ZIP prefix, not city names. It is not wrong, but the time would be better spent on the coordinates themselves.
- **Out-of-Brazil points are flagged (33) but not removed, and then averaged.** The join-validation section uses the **mean** lat/lng per prefix. **[verified]** In 89 prefixes the mean and median differ by more than 0.5° (about 55 km), which means a few bad points are dragging the centroids. **Fix:** drop out-of-bounds points, then take the **median** per prefix.
- **[verified]** 8 ZIP prefixes map to more than one state. Worth a note.

**Payments**
- *"The cause of the 378 payment vs item mismatches cannot be determined"* is too pessimistic. **[verified]** 82.5% of the mismatching orders have `installments > 1`, compared with 51.5% of all orders. Among orders where payment is *higher* than items, the figure is 89%. Credit-card **installment interest** explains most of it. This matters for revenue analysis: use `order_items` (`price + freight`) for GMV or seller revenue, and use `payments` for "what the customer actually paid".
- Zero installments → `NaN` changes the column from `int` to `float`. That is fine, but `Int64` (nullable int) keeps the semantics. Note also that both of these orders have `payment_sequential = 2` with no sequence 1, so payment records are *missing*, not only mislabeled. That deserves a line in the report.

**Reviews**
- **Duplicate `review_id` values are explained, not mysterious.** **[verified]** In 100% of the 789 duplicated `review_id` values, all linked orders belong to the **same `customer_unique_id`**. One customer wrote one review that Olist attached to several of their orders (often orders placed at the same moment, split by seller). That is a property of the data, not an error. Document it this way.
- **Aggregation rule:** for orders with 2–3 reviews, the join step uses `mean(review_score)`. The **latest** review (max `review_answer_timestamp`) is usually more meaningful, because a later review reflects the final experience. For review-level statistics such as the score distribution, deduplicate on `review_id` first, or the shared reviews are counted 2–3 times.
- `review_creation_date` ends on 2018-08-31 while orders go to 2018-10-17. Worth stating as a coverage limit.

**General cleaning-notebook points**
- **Unfilled placeholders:** the customers summary says *"(X)"*, the products summary says *"(count: X)"*, and the geolocation summary says *"from 8,011 to X ... leaving Y rows"*. The final report has the real numbers (96,096; 4; 5,962; 720,494), but the per-table summaries still contain the placeholders.
- **Inconsistent report:** section 6 of the final report says shipping limit dates beyond the order period are *"not quantified"*, but the validation cell quantified them as **4**.
- **No numeric outlier analysis** for `price`, `freight_value`, `payment_value` or product dimensions. Min/max checks show the values are *possible*, not that they are *typical*. An IQR or log-scale boxplot per category would catch anything extreme.
- `agg([min, max])` passes Python builtins. That is deprecated in pandas, so use `agg(["min", "max"])` (the validation cells already do).
- In payments, `df = payments.copy()` (the **raw** table) is used in the investigation cells, while `payments_clean` is used for the fix. It is not wrong here, but mixing raw and clean objects in one section is fragile.

### 4.3 Notebook 3: Order Status and Time Trend

**Order status**
- *"Only 0.63% were canceled, indicating a relatively low cancellation rate."* The non-fulfilment rate should combine **canceled + unavailable** (625 + 609 = **1.24%**). "Unavailable" means the order failed because the product was out of stock, which is also a failure.
- **Statuses are a snapshot taken at extraction time.** `shipped`, `invoiced` and `processing` orders are mostly *in progress* at the data cutoff, not failures. A status-by-purchase-month view would show this and would make the "97% fulfilment" claim more honest.
- The chart is dominated by the 97% bar, so every other status is a sliver. Better options: show a "delivered vs not delivered" split, then a separate bar chart of the non-delivered statuses only. Also use 1–2 decimals, not 3.

**Monthly trend**
- The valid window (Jan 2017 to Aug 2018) is the right choice. Strengthen it with the evidence: **[verified]** Nov 2016 has 0 orders and Dec 2016 has 1 (a gap in collection), and Sep/Oct 2018 contain **only canceled orders, plus 1 shipped** (15 + 1 and 4), so those are artefacts of the cutoff.
- **Black Friday *can* be confirmed with the data.** **[verified]** At daily granularity, **2017-11-24 (Black Friday) had 1,176 orders**, compared with 499 the next day and roughly 150–250 on a typical day. The notebook says *"can't be confirmed with a single year of data"*. That is true for *seasonality*, but the Black Friday spike itself is clearly visible. Add a daily plot around November 2017.
- **The counts include every status** (canceled and unavailable too). That is fine for "demand", but say so explicitly. "Orders placed" and "orders fulfilled" are different metrics, and later notebooks (revenue, delivery) will need the filtered version.
- **Month length:** raw month-over-month % mixes demand with calendar length (Feb has 28 days and Jan has 31). For growth comparisons, use **orders per day** (`orders / days_in_month`).
- The interpretation *"step-up in volume after Nov 2017 followed by a plateau with slight downward drift"* is reasonable and well put.

**2017 vs 2018**
- Comparing only Jan to Aug is correct ✔. The 2.35x figure and the narrowing gap (9.1x → 1.5x) check out.
- The bullet *"2018 was higher in every month"* is true, but it is expected given that 2017 was a ramp-up year. A better question is whether 2018 is still growing, and the MoM table answers it: no, 2018 is flat to slightly down. That is the more useful business insight, so state it first.

**Notebook mechanics**
- **Execution is out of order:** the execution counts are 90, 100, 98, 102, 93. Run *Restart & Run All* before committing, so the outputs match the code order.
- **Redundant cells:** `con.close()` → reconnect → `order_status` re-displayed from memory. Remove them.
- **Persistent DuckDB view with a frozen definition.** **[verified]** The `.duckdb` file contains:
  ```sql
  CREATE VIEW orders AS SELECT * FROM read_csv('../Data/Processed/orders_clean.csv',
      new_line := '\r\n', auto_detect := false, columns := struct_pack(...))
  ```
  This view breaks if the notebook runs from another working directory, if the CSV is regenerated on macOS or Linux (`\n` line endings), or if a column is added. **Fix:** use an in-memory connection (`duckdb.connect()`) and recreate views at the top of the notebook with `CREATE OR REPLACE VIEW ... AS SELECT * FROM read_parquet(...)`. Then there is no `.duckdb` file to commit at all.
- **Color meaning:** red is used both for "excluded data" and for the "peak" marker. Use a different accent for the peak.
- Nested same-type quotes inside f-strings (`f"{year_2017["orders_count"].max()}"`) only work on **Python ≥ 3.12**. That is fine, but it must be pinned (see R1).

---

## 5. Repository and Process (🟡)

| # | Issue | Recommendation |
|---|---|---|
| R1 | `requirements.txt` is **empty** (commit `6127443` "add requirements.txt" added an empty file). The outputs show the `str` dtype, which suggests pandas 3.x. My local pandas 2.3 shows `object` instead. | Pin `python>=3.12`, `pandas`, `numpy`, `matplotlib`, `duckdb` and `pyarrow` (for Parquet) with exact versions |
| R2 | `Data/Processed/` is in `.gitignore`, but `customers_clean.csv`, `orders_clean.csv` and `products_clean.csv` are **still tracked** (committed before the ignore rule). They will go stale. | `git rm --cached Data/Processed/*.csv`, then regenerate them from the notebook |
| R3 | 122 MB of raw CSVs are committed (`olist_geolocation_dataset.csv` alone is 62 MB, over GitHub's 50 MB warning threshold) | Either keep them and document why, or use Git LFS / a download script (Kaggle API) and ignore `Data/Raw/` |
| R4 | Branch name `Issue-4-—-Order-Status-&-Time-Trend-Analysis` and notebook name `3_Order Status & Time Trend Analysis.ipynb` contain an em-dash, `&` and spaces, which break shell commands and URLs | Use `issue-4-order-status-trends` and `3_order_status_time_trends.ipynb` |
| R5 | `README.md` is a single line. `Reports/` is empty, although the changelog refers to a report file | Add a README with the project goal, how to run it, the notebook order and the folder layout. Export the cleaning report to `Reports/data_cleaning_report.md` |
| R6 | The cleaning notebook has 190+ cells. Nothing can be rerun selectively or tested | Move the cleaning logic into `src/cleaning.py` (one function per table) and keep the notebook for narrative and validation output |
| R7 | Commit messages such as `update`, `correct the previous commit` | Use descriptive messages, e.g. `orders: fix malformed delivery timestamps` |
| R8 | No shared constants. The valid window `START/END`, file paths and so on are redefined in several cells | Put them in a `config.py` or a single top cell |

---

## 6. What Was Done Well

- **Consistent cleaning template.** Investigation → decision → action → validation for every table makes the notebook easy to audit.
- **A conservative philosophy**, stated explicitly: preserve rows, fix only what is provably wrong, flag what is ambiguous, don't impute. That is the right default for EDA.
- **Join validation with totals.** Measuring the 4.5% `price` inflation from the many-to-many `order_items → payments` join is exactly the kind of check that prevents the most common Olist mistake.
- **Explicit "rules for the analysis stage."** Later work has clear guardrails: aggregate payments and reviews, use `customer_unique_id`, and so on.
- **Malformed timestamps found** (`2018-02-22 007:55`, `2018-06-18:0 23:07:33`) by comparing nulls before and after coercion. That is a good technique.
- **A sensible valid window and a fair year-over-year comparison** in notebook 3, with clear charts (excluded periods shown in a different color, comparable months shown as solid lines).

---

## 7. Recommended Next Steps (Priority Order)

1. **Fix `delivery_delay_days`** (C4) before any delivery or review analysis starts.
2. **Switch the processed output to Parquet** and load it through a single helper (C1). This also removes the need for the committed `.duckdb` file (C6).
3. **Resolve the two cleaning versions** and correct `changelog.md` (C5). Rebase Issue-4 onto `main`.
4. **Fix the validation-object bug** in products (C2), re-run the cross-table checks at the end (C3), fill the `X`/`Y` placeholders, and re-run the notebooks top to bottom.
5. **Geolocation:** drop out-of-bounds points and use the median per prefix.
6. **Write down the explanations already found:** installment interest (payments), one review covering several orders (reviews), and the Black Friday spike (trend).
7. **Fill in `requirements.txt` and `README.md`**, untrack the processed CSVs, and rename the branch and notebook.
8. **Next analyses to consider**, building on the cleaned base: delivery performance vs review score (the strongest driver in this dataset), revenue by category and state, repeat-customer rate using `customer_unique_id` (expect it to be very low, about 3%), seller concentration, and freight as a share of price by distance (using the cleaned geolocation).

---

## Appendix: Verification Results

These were computed independently from `Data/Raw/` and `Data/Processed/` during this review.

| Check | Result |
|---|---|
| Overlap between "carrier before purchase" and "customer before carrier" | 0 (the 250 fixes are distinct rows) |
| "Carrier before purchase" gap, in hours | median 0.60, 75th percentile 1.02, max 4,109 |
| Delivered orders late by timestamp vs by date | 7,826 vs 6,534 → **1,292 misclassified** |
| Statuses in Sep 2018 / Oct 2018 | 15 canceled + 1 shipped / 4 canceled |
| Statuses in Aug 2018 | 6,351 delivered, 84 canceled, 47 shipped, 23 invoiced, 7 unavailable |
| Orders in Nov 2016 / Dec 2016 | 0 / 1 |
| Busiest days | 2017-11-24: **1,176**; 2017-11-25: 499; 2017-11-27: 403 |
| Duplicated `review_id` linked to a single `customer_unique_id` | **100%** |
| Payment–item mismatches with installments > 1 | 82.5% (89% for payment > items), vs 51.5% overall |
| `sellers_clean.csv` ZIP dtype after `read_csv` | `int64` (leading zeros lost) |
| `orders_clean.csv` timestamp dtype after `read_csv` | `object` |
| Geolocation prefixes where mean and median coordinates differ by more than 0.5° | 89 |
| Geolocation prefixes mapped to more than one state | 8 |
| DuckDB file contents | 1 persistent view `orders` → `read_csv('../Data/Processed/orders_clean.csv', new_line '\r\n', auto_detect false, ...)` |
