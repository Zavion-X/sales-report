import csv
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from report import build_monthly_chart, build_pdf, month_label, read_sales_mapped, summarize

PREVIEW_ROWS = 5
FIELDS = ["Date", "Product", "Quantity", "Price"]
OPTIONS = FIELDS + ["Ignore"]

# Header names we recognise on sight, so the dropdowns start out filled in
GUESSES = {
    "date": "Date",
    "product": "Product", "item": "Product",
    "quantity": "Quantity", "qty": "Quantity",
    "price": "Price",
}

st.set_page_config(page_title="Sales report", page_icon="📊")
st.title("Sales report")
st.caption("Upload a CSV, then tell the app what each column is.")

uploaded = st.file_uploader("Sales CSV", type="csv")
if uploaded is None:
    st.info("Upload a CSV file to see the report.")
    st.stop()

try:
    text = uploaded.getvalue().decode("utf-8-sig")
except UnicodeDecodeError:
    st.error("That file isn't a text CSV. Please upload a .csv file.")
    st.stop()

table = [row for row in csv.reader(io.StringIO(text, newline="")) if row]
if not table:
    st.warning("That file is empty.")
    st.stop()
header, rows = table[0], table[1:]

st.subheader("Choose what each column is")
st.caption(f"First {PREVIEW_ROWS} rows. Pick one column each for Date, Product, "
           "Quantity and Price, and Ignore the rest.")
choices = []
for i, (col, name) in enumerate(zip(st.columns(len(header)), header)):
    with col:
        choices.append(st.selectbox(
            name or f"Column {i + 1}", OPTIONS,
            index=OPTIONS.index(GUESSES.get(name.strip().lower(), "Ignore")),
            key=f"column-{uploaded.file_id}-{i}",
            label_visibility="collapsed",
        ))
        st.dataframe(
            pd.DataFrame({name: [r[i] if i < len(r) else "" for r in rows[:PREVIEW_ROWS]]}),
            hide_index=True,
        )

missing = [f for f in FIELDS if f not in choices]
repeated = [f for f in FIELDS if choices.count(f) > 1]
if missing or repeated:
    problems = []
    if missing:
        problems.append("still needs a column for " + ", ".join(missing))
    if repeated:
        problems.append("has more than one column set to " + ", ".join(repeated))
    st.warning("The report " + " and ".join(problems) + ".")
    st.stop()

indices = {f.lower(): choices.index(f) for f in FIELDS}
try:
    summary = summarize(read_sales_mapped(rows, indices))
except ValueError as e:
    st.error(f"Couldn't read the file with those choices: {e}. Check each column "
             "is set correctly. Dates need to look like 2026-09-01.")
    st.stop()

if summary is None:
    st.warning("No sales found in that file.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Total sales", f"${summary['total']:,.2f}")
col2.metric("Sales / items", f"{summary['count']} / {summary['items']}")
col3.metric("Best seller", summary["best"],
            f"{summary['best_units']} units, ${summary['best_revenue']:,.2f}",
            delta_color="off")

st.subheader("Sales by month")
st.pyplot(build_monthly_chart(summary["by_month"]))

st.dataframe(
    pd.DataFrame({
        "Month": [month_label(m) for m in summary["by_month"]],
        "Sales": [f"${t:,.2f}" for t in summary["by_month"].values()],
    }),
    hide_index=True,
)

st.download_button(
    "Download PDF",
    data=build_pdf(summary, title=f"Sales report: {uploaded.name}"),
    file_name=f"{Path(uploaded.name).stem}_report.pdf",
    mime="application/pdf",
)
