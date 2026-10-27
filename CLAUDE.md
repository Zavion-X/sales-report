# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Reads a sales CSV and builds a report from whichever columns it has: totals, profit, best seller, monthly sales and breakdowns by product, category, customer, branch, payment method and staff. It runs as a command-line report and as a Streamlit web app with a PDF download. There's no build step, and no tests or linter configured. Install dependencies with `pip install -r requirements.txt`.

## Running

```
python3 report.py              # uses sales.csv next to the script
python3 report.py other.csv    # any CSV; columns are found by their header names
streamlit run app.py           # web app: upload a CSV and choose each column's meaning
```

- The CLI recognises headers through `HEADER_NAMES` in `report.py` (`date`, `item`, `qty`, `total sales`, `cashier`, ...). The app starts from the same guesses, and the user can change every column with a dropdown.
- The default CSV path is relative to the script, not the working directory. `monthly_sales.png` is written next to whichever CSV was read (only when there's a Date column), and each run overwrites it. It's git-ignored.
- `sales.csv` is fake data made by a one-off script that wasn't kept. It runs from Sept 1 to Oct 26, 2026, so October is a partial month.

## How the columns work

No field is required. Each report section appears only when its columns exist, so keep that rule when adding sections:

- **Sales figures:** `Total sales` is used as is. Otherwise `Price` (per item) is multiplied by `Quantity`. With no Quantity column each row counts as one item.
- **Profit:** `Cost` is the cost of the whole sale, `Unit cost` is per item (times Quantity). Profit needs a cost plus sales figures.
- **Best seller:** ranked by units sold, or by number of sales when there's no Quantity column.
- **Orders and average order value:** need `Order ID`.
- **Monthly chart and table:** need `Date`. Without sales figures they count sales per month.
- **Breakdown tables:** one per Product, Category, Customer, Branch, Payment method and Staff column.
- **Dates:** `parse_date()` takes ISO, `01/09/2026`, `1 Sep 2026` and similar, and ignores times of day. Numeric dates are ambiguous, so `date_order()` looks for one like `13/09/2026` that settles day-first or month-first. If none does, the app asks and the CLI assumes day first.

## Structure

`report.py` is layered so the CLI, the app and the PDF share it:

- `read_sales_mapped(rows, columns, day_first)` turns lists of cells into sale dicts, where `columns` maps a field name to a column number. Errors say the row number and the field.
- `summarize()` returns everything the columns allow; unsupported entries are `None` or missing.
- `headline_facts()`, `group_table()`, `money()` and the monthly text helpers produce the wording once for all three front ends.
- `build_monthly_chart()` returns a matplotlib `Figure`. `build_pdf()` returns PDF bytes (headline figures, chart if there are dates, top 5 of each breakdown) using fpdf2. Both import their library lazily, and the PDF's built-in fonts are Latin-1 only, so other characters print as `?`.

`app.py` is a thin UI over `report.py`, so keep new logic there. After an upload it shows the first 5 rows in a grid of 4 columns per row, with a dropdown above each column and a "Using: ..." summary below. It decodes the upload with `utf-8-sig`, and bad files or choices show an `st.error` or `st.warning` instead of a traceback.

Streamlit's `AppTest` can't simulate `st.file_uploader`, so test the upload path by patching `st.file_uploader` with a fake object that has `getvalue()`, `name` and `file_id`. Then set the dropdowns with `at.selectbox[i].set_value(...)` and call `at.run()`. Run such a script with the project folder on `PYTHONPATH`, or `import report` fails.
