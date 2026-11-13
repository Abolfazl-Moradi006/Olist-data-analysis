# Olist E-commerce Data Analysis

Analysis of the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce): about 99k orders placed on the Olist marketplace between September 2016 and October 2018, with customers, sellers, products, payments, reviews and geolocation.

**Deliverables**

| File | What it is |
|---|---|
| `notebooks/final_analysis.ipynb` | Final integrated notebook: runs from the raw CSV files to the business insights (10 sections) |
| `reports/management_report.docx` | Management report in Persian (Word, editable): dataset and method, business overview, 5 key findings, 3 recommendations, discussion, limitations |
| `reports/management_report.pdf` | The same report exported to PDF |
| `outputs/charts/*.png` | All charts of the final notebook |
| `outputs/tables/*.csv` | Supporting tables (monthly KPIs, states, categories, delivery) |
| `outputs/key_metrics.json` | Every number used in the report, exported by the notebook |
| `src/` | Shared Python code (paths, cleaning, metric definitions, plotting, report builder) |

## 1. Install

Requires **Python 3.12 or newer** (tested with 3.13).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

To open the notebook interactively, use VS Code (Jupyter extension) or install JupyterLab: `pip install jupyterlab`.

## 2. Get the raw data

The Kaggle files are not included (about 125 MB). Download them from
<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> (free Kaggle account), or with the Kaggle CLI:

```bash
kaggle datasets download -d olistbr/brazilian-ecommerce -p Data/Raw --unzip
```

`Data/Raw/` must then contain these files (the last one is included in this project; it holds the IBGE 2017 state population estimates used for per-capita metrics):

```
olist_customers_dataset.csv        olist_order_reviews_dataset.csv
olist_geolocation_dataset.csv      olist_orders_dataset.csv
olist_order_items_dataset.csv      olist_products_dataset.csv
olist_order_payments_dataset.csv   olist_sellers_dataset.csv
product_category_name_translation.csv
brazil_states_population.csv
```

> **Important:** put the raw CSV files directly in `Data/Raw/` (for example `Data/Raw/olist_orders_dataset.csv`), not in a subfolder. All notebooks read the raw data from this path and write the cleaned tables to `Data/Processed/`, so they fail if the files are anywhere else.

## 3. Run the final notebook

Open `notebooks/final_analysis.ipynb` and run all cells (*Restart & Run All*), or run it headless from the project root:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/final_analysis.ipynb
```

It takes under a minute. The notebook:

1. loads and profiles the raw tables,
2. cleans them with `src/cleaning.py` and writes `Data/Processed/*.parquet`,
3. to 9. runs the analyses (orders and time, customers and geography, products and payments, delivery, reviews, sellers, multi-table analysis),
4. ends with the key findings, recommendations and quality checks, and exports `outputs/key_metrics.json`.

All paths are built from the project root (`src/config.py`), so the notebook works from any working directory and operating system.

## 4. Management report

`reports/management_report.docx` is the editable report and `reports/management_report.pdf` is its PDF export. The report is based only on the team notebooks 1 to 8: every number, chart, conclusion and recommendation in it comes from those notebooks, and each section names the notebook that holds the supporting analysis. The report uses the Persian fonts *B Nazanin* and *B Titr*; install them to view the Word file as intended (the PDF has the fonts embedded).

## Metric definitions

Defined once in `src/metrics.py` and used in every section:

| Metric | Definition |
|---|---|
| Orders | unique `order_id` (payment records are never counted as orders) |
| Unique customers | `nunique(customer_unique_id)` (`customer_id` is one id per order) |
| Product sales | `SUM(price)` from `order_items` |
| Revenue | `SUM(price + freight_value)` from `order_items`, aggregated per order |
| Average order value | revenue / orders with items |
| Amount paid | `SUM(payment_value)` (includes installment interest, reported separately) |
| Review score | latest review per order |
| Delivery time / late | delivered orders only; late = delivery date after the estimated date (calendar days) |

Trends use the valid window **January 2017 to August 2018**; the months before and after are incomplete.

## Project structure

```
notebooks/
  final_analysis.ipynb     final integrated notebook
  1_... to 8_...ipynb      original team notebooks (kept in the repository for reference)
src/
  config.py                paths and constants
  data_loading.py          raw loading and profiling
  cleaning.py              cleaning and feature engineering (reproduces notebook 2 exactly)
  metrics.py               shared metric definitions and the order-level table
  viz.py                   plot style and chart export
Data/
  Raw/                     raw CSV files (download, see above)
  Processed/               cleaned Parquet files (generated, ignored by git)
outputs/charts, outputs/tables, outputs/key_metrics.json
reports/management_report.docx, reports/management_report.pdf
```
