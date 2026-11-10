# Improvement Roadmap

**Status:** Implemented on 2026-11-04 with every recommended decision. Not committed yet. Differences from the plan:
- **0.1:** `main` was **merged** into the branch instead of rebasing it. That gives the same result without rewriting commits already pushed to `origin`.
- **0-A:** pinned `pandas==3.1.1`, because the exact version used by the team could not be confirmed. Change it if the team uses another 3.x release.
- **6.1** (moving the cleaning code into `src/`) and **6.6** (archiving the `shirkavand` notebook on its own branch) were **not done**. 6.1 is a large optional refactor, and 6.6 needs the team's agreement.
- Numbers that changed during implementation: payment mismatches are **303** after rounding to cents (the old 378 included 1-cent rounding noise). Customer records without coordinates are **279** (one ZIP prefix had only out-of-Brazil points).
**Based on:** [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md). Issue IDs (C1, R2, …) refer to that review.
**Decision already made:** processed data will be stored as **Parquet** (option C).

The work is grouped into phases. Each phase can be approved, changed or skipped on its own. Items marked **❓ Decision** need your choice before implementation. My recommended choice is listed first.

---

## Phase 0: Setup and Branch Hygiene

The other phases depend on this one, so it should be done first.

| # | Task | Files | Done when |
|---|---|---|---|
| 0.1 | Rebase the Issue-4 branch onto `main` so it picks up `main`'s `.gitignore` and changelog (fixes C6) | git | Branch contains `6a42a33` and `01b23a4`. No conflicts |
| 0.2 | Fill in `requirements.txt` with pinned versions: `pandas`, `numpy`, `matplotlib`, `duckdb`, **`pyarrow`** (needed for Parquet), `ipykernel`. Note `python>=3.12` in the README | `requirements.txt` | `pip install -r requirements.txt` in a fresh venv runs all notebooks |
| 0.3 | Stop tracking generated files: `git rm --cached Data/Processed/*.csv Data/duckdb/olist.duckdb`. Make sure `.gitignore` covers `Data/Processed/` and `Data/duckdb/` | `.gitignore`, git index | `git ls-files Data/Processed Data/duckdb` is empty |

**❓ Decision 0-A:** Which pandas version should be pinned? The notebook outputs suggest **pandas 3.x** (the `str` dtype). My local machine has 2.3. **Recommended:** pin the version the team actually used to produce the outputs. Run `pip show pandas` to check.

---

## Phase 1: Switch to Parquet (C1)

**Goal:** cleaned tables keep their types (ZIP codes as `string`, timestamps as `datetime64`, flags as `bool`, installments as nullable `Int64`) when reloaded, with no extra code when reading.

### 1.1 Cleaning notebook: write Parquet
In `2_data_cleaning.ipynb`, replace each of the 8 save cells:
```python
# before
df.to_csv("../Data/Processed/orders_clean.csv", index=False)
# after
orders_clean.to_parquet("../Data/Processed/orders_clean.parquet", index=False)
```
- Save the **named** table (`orders_clean`, `products_clean`, …) rather than `df`. This also removes part of the risk behind C2.
- Convert `payment_installments` to `Int64` (nullable integer) before saving, so the 2 `NaN` values don't turn the whole column into `float`.

### 1.2 Round-trip check (new cell at the end of the cleaning notebook)
Reload every Parquet file and assert that its dtypes equal those of the in-memory DataFrame, with specific checks such as:
```python
assert pd.read_parquet(".../sellers_clean.parquet")["seller_zip_code_prefix"].str.len().eq(5).all()
```
This makes the "types survive" guarantee testable instead of assumed.

### 1.3 Notebook 3: read Parquet through in-memory DuckDB (also fixes C6)
```python
con = duckdb.connect()   # in-memory, no file
con.sql("CREATE OR REPLACE VIEW orders AS SELECT * FROM read_parquet('../Data/Processed/orders_clean.parquet')")
```
- Delete `Data/duckdb/olist.duckdb` and the `Data/duckdb/` folder.
- Remove the redundant `con.close()` / reconnect cells.
- The column type changes from `DATE` to `TIMESTAMP` for `order_estimated_delivery_date`, so check that the queries still behave the same. They only use `order_year` and `order_month` today, so no change is expected.

### 1.4 Remove the old CSVs
**❓ Decision 1-A:** Should the cleaning notebook also keep writing CSV copies?
- **Recommended: no.** Parquet only, so there is one format and no chance of someone loading the lossy CSV.
- Alternative: also write CSV for people who want to open the files in Excel, named `*_clean.export.csv` so nobody uses them by mistake.

---

## Phase 2: Correctness Fixes

These change results, so they should go in before any new analysis.

| # | Issue | Fix | Location | Done when |
|---|---|---|---|---|
| 2.1 | **C4: on-time deliveries counted as late** | `delivery_delay_days = (delivered.dt.normalize() - estimated).dt.days`. Add `is_late = delivery_delay_days > 0` | Orders → preparation cell | Late delivered orders = **6,534** (not 7,826) |
| 2.2 | **C2: products validation runs on the untranslated table** | Assign `products_clean = df` after the merge, or have the merge write to `products_clean` directly | Products → preparation cell | Validation shows English category names. The join check uses the translated table |
| 2.3 | Same `df = …` risk in sellers (`df = df.drop_duplicates()`) | Assign back to `sellers_clean` | Sellers → standardization cell | — |
| 2.4 | **C3: customers validation reports 99,441 ZIP codes missing** | Remove the geolocation check from the customers section. Re-run all cross-table checks in a new **"Final cross-table checks"** section after every table is cleaned | Customers validation + new section | Reports 278 customer / 7 seller prefixes not in geolocation |
| 2.5 | Raw and clean objects mixed in payments (`df = payments.copy()`) | Use `payments_clean` throughout | Payments section | — |
| 2.6 | `agg([min, max])` with Python builtins (deprecated) | Use `agg(["min", "max"])` | Products, order_items, payments, reviews | No FutureWarnings |

---

## Phase 3: Methodology Improvements

### 3.1 Orders: consistent anomaly policy and traceability
**❓ Decision 3-A:** How should "carrier before purchase" be handled? (166 rows, median gap 0.6 hours)
- **Recommended: keep the values and flag them**, the same way "approval after carrier" is handled. A gap of less than an hour looks like a clock or recording artefact, not a wrong event.
- Alternative: keep setting them to `NaT` (the current behavior), but add flag columns.

Either way, add boolean flag columns so the processed file records exactly which rows were affected:
`flag_carrier_before_purchase`, `flag_customer_before_carrier`, `flag_approval_after_customer`, `flag_approval_after_carrier` (rename the existing `anomaly_approval_after_carrier` to match).

Also add derived durations once, so later notebooks share the same definitions: `approval_hours`, `carrier_to_customer_days`.

### 3.2 Geolocation: clean the coordinates, not only city names
- Drop the 33 points outside Brazil's bounds.
- Create a **one-row-per-prefix** table using the **median** lat/lng (89 prefixes currently have their mean pulled more than 0.5° by outliers). Save it as `geolocation_prefix.parquet` so every later notebook joins against the same table.
- Document the 8 prefixes that map to more than one state.

### 3.3 Reviews: record the explanation and define the aggregation
- Rewrite the duplicate-`review_id` conclusion: **one review written by one customer, attached to several of that customer's orders** (verified for 100% of cases). It is not a data error.
- **❓ Decision 3-B:** How should an order with 2–3 reviews be aggregated?
  - **Recommended: the latest review** (max `review_answer_timestamp`), which reflects the final experience.
  - Alternative: the mean score (the current join-validation approach).
- Add a note: score distributions must be computed on reviews deduplicated by `review_id`.
- Correct the meaning of `review_creation_date` to "date the survey was sent" (also in notebook 1).

### 3.4 Payments: record the explanation
- Replace "cause cannot be determined" with the evidence: 82.5% of mismatching orders have more than 1 installment (51.5% overall), so installment interest is the most likely cause.
- Add the analysis rule: **GMV and seller revenue come from `order_items`; "amount the customer paid" comes from `payments`.**
- Note that the 2 zero-installment rows have `payment_sequential = 2` with no sequence 1, which means records are missing.

### 3.5 Products
**❓ Decision 3-C:** Should the misspelled columns `product_name_lenght` and `product_description_lenght` be renamed to `..._length` during cleaning? **Recommended: yes.** Nothing downstream uses them yet, so this is the cheapest moment.
- **❓ Decision 3-D:** Should the 610 missing categories be filled with `"unknown"` in the cleaned file? **Recommended: yes.** It is the rule the report already gives, so applying it once avoids repeating it in every analysis. Keep the other 3 descriptive columns as `NaN`.

### 3.6 Numeric outlier review (new subsection per table)
Add an IQR or log-scale boxplot check for `price`, `freight_value`, `payment_value` and product weight and dimensions. This is a **flag-only** step, in keeping with the conservative policy. Report the counts in the summary.

---

## Phase 4: Documentation Accuracy

| # | Task | Location |
|---|---|---|
| 4.1 | Fill the placeholders: customers "(X)" → 96,096; products "(count: X)" → 4; geolocation "X … Y" → 5,962 / 720,494 | Per-table summaries in notebook 2 |
| 4.2 | Fix "shipping limit date beyond period: *not quantified*" → **4** | Final report §6 |
| 4.3 | Reword "610 products … will be handled in the cleaning stage" | Products result cell |
| 4.4 | Notebook 1: `customer_unique_id` is not in `orders`; ZIP prefix is a "join key, aggregate first", not an FK; `review_creation_date` meaning | Notebook 1 data dictionary and general report |
| 4.5 | Update the final report and summaries for every change in Phases 1–3 (Parquet paths, new flag columns, the new late count, the geolocation median table, the review rule) | Notebook 2 final report |
| 4.6 | Export the final report to `Reports/data_cleaning_report.md`, which the changelog promises but doesn't exist | `Reports/` |
| 4.7 | Correct `changelog.md` (C5): it describes the shirkavand payments version (5 rows dropped) and not the data actually in use | `changelog.md` |

---

## Phase 5: Notebook 3 Analysis Improvements

| # | Task | Why |
|---|---|---|
| 5.1 | Non-fulfilment rate = canceled + unavailable = **1.24%** (not 0.63%) | "Unavailable" is also a failed order |
| 5.2 | Add an order-status-by-purchase-month view | Shows that `shipped`/`invoiced`/`processing` orders are in progress at the data cutoff, not failures |
| 5.3 | Redesign the status chart: delivered vs not delivered, then a separate bar chart of non-delivered statuses. Use 1–2 decimal places | The 97% bar currently hides every other status |
| 5.4 | Add a daily-orders plot for Nov 2017 and update the conclusion: **Black Friday (2017-11-24, 1,176 orders) is confirmed**. Only *recurring seasonality* is unconfirmable | The current text understates what the data shows |
| 5.5 | State the window evidence: Nov 2016 = 0 orders, Dec 2016 = 1; Sep/Oct 2018 contain only canceled orders plus 1 shipped | Supports the valid-window choice |
| 5.6 | State that monthly counts include all statuses (orders *placed*). Add a delivered-only line if useful | Avoids confusion with later revenue and delivery work |
| 5.7 | Add orders-per-day alongside MoM % | Removes the month-length effect |
| 5.8 | Reorder the 2017 vs 2018 conclusion: lead with "2018 is flat or slightly declining" | A more useful insight than "2018 > 2017 every month" |
| 5.9 | Chart color: change the peak marker from red, which already means "excluded" | Avoids two meanings for one color |
| 5.10 | **Restart & Run All** before committing | Execution counts are currently out of order |

---

## Phase 6: Repository and Maintainability (optional, larger)

| # | Task | Notes |
|---|---|---|
| 6.1 | Move the cleaning logic into `src/cleaning.py` (one `clean_<table>()` function each) plus `src/io.py` (`load_clean(table)` / `save_clean(df, table)`). The notebook then calls the functions and shows the validation | Makes reruns reliable and removes the `df` alias bug class entirely |
| 6.2 | `config.py` (or a single top cell) for paths and the valid window `START`/`END` | Defined once, not per cell |
| 6.3 | README: goal, setup, notebook run order, folder layout, data source | — |
| 6.4 | Rename the notebook to `3_order_status_time_trends.ipynb`. Use simple branch names for future issues (`issue-5-…`) | No spaces, `&` or em-dashes |
| 6.5 | **❓ Decision 6-A:** How should raw data (122 MB, with one 62 MB file) be stored? **Recommended:** keep it as is for now (it works, and the course likely expects it), or move to Git LFS if pushes get slow. Alternative: a Kaggle download script and ignore `Data/Raw/` | — |
| 6.6 | Archive or close the `shirkavand` cleaning notebook once the team agrees that `2_data_cleaning.ipynb` is the single source of truth | Prevents two notebooks writing the same outputs |

---

## Suggested Order and Size

| Phase | Effort | Depends on | Changes results? |
|---|---|---|---|
| 0. Setup | Small | — | No |
| 1. Parquet | Small–medium | 0 | No (types only) |
| 2. Correctness | Small | 1 | **Yes** (late count, validation outputs) |
| 3. Methodology | Medium | 2 + decisions 3-A … 3-D | **Yes** (flags, geolocation, reviews) |
| 4. Documentation | Small–medium | 2, 3 | No |
| 5. Notebook 3 | Medium | 1 | Conclusions only |
| 6. Refactor | Large (optional) | 1–4 | No |

**Minimum recommended set:** Phases 0, 1, 2 and 4, plus 5.1 and 5.4. Together they fix every error found in the review. Phase 3 improves quality, and Phase 6 makes future work easier.

## Decisions Needed From You

| ID | Question | Recommended |
|---|---|---|
| 0-A | Which pandas version to pin? | The one the team actually used (likely 3.x) |
| 1-A | Keep CSV copies alongside Parquet? | No |
| 3-A | "Carrier before purchase" (166 rows): `NaT` or keep and flag? | Keep and flag |
| 3-B | Orders with several reviews: latest or mean? | Latest |
| 3-C | Rename the `…_lenght` columns? | Yes |
| 3-D | Fill missing product categories with `"unknown"`? | Yes |
| 6-A | Raw data storage? | Keep as is |

Also tell me which phases to implement. Note that Phase 2 and Phase 3 change numbers in your existing conclusions and report, and I would update the text to match.
