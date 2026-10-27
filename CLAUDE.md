# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Reads a sales CSV and shows the total sales, best-selling product and monthly sales, as a command-line report and as a Streamlit web app. There's no build step, and no tests or linter configured. Install dependencies with `pip install -r requirements.txt`.

## Running

```
python3 report.py              # uses sales.csv next to the script
python3 report.py other.csv    # any CSV with the same columns
streamlit run app.py           # web app: upload a CSV in the browser
```

- CSV columns: `date` (YYYY-MM-DD), `product`, `quantity`, `price`. `price` is per item, and a sale's total is `quantity * price`.
- The default CSV path is relative to the script, not the working directory. `monthly_sales.png` is written next to whichever CSV was read, and each run overwrites it. It's git-ignored.
- "Best seller" is ranked by units sold, not revenue.
- `sales.csv` is fake data made by a one-off script that wasn't kept. It runs from Sept 1 to Oct 26, 2026, so October is a partial month.

## Structure

`report.py` is layered so other front ends can reuse it: `read_sales(lines)` parses any CSV text, `summarize()` computes the totals, best seller and monthly dict, and `build_monthly_chart()` returns a matplotlib `Figure`. `main()` and the CLI only print and save a file on top of those. matplotlib is imported lazily inside `build_monthly_chart()`, so if it's missing the CLI report still prints and the chart is skipped.

`app.py` is a thin UI over `report.py` (it imports `read_sales`, `summarize`, `build_monthly_chart`, so keep new logic in `report.py`). It decodes the upload with `utf-8-sig`, and bad files show an `st.error` or `st.warning` instead of a traceback. Streamlit's `AppTest` can't simulate `st.file_uploader`, so test the upload path by patching `st.file_uploader` with a fake object that has `getvalue()`.
