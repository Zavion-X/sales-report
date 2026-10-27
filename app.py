import csv
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from report import (FIELDS, build_monthly_chart, build_pdf, date_order, group_table,
                    guess_columns, headline_facts, month_label, monthly_text,
                    monthly_title, period_text, read_sales_mapped, summarize)

PREVIEW_ROWS = 5
PER_ROW = 4  # preview columns per row, so wide files wrap instead of getting cramped
GROUP_ROWS = 10
IGNORE = "Ignore"
LABELS = list(FIELDS.values()) + [IGNORE]
KEY_OF = {label: key for key, label in FIELDS.items()}

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
st.caption(f"First {PREVIEW_ROWS} rows. Set each column you want to use and leave the "
           "rest on Ignore. Price and Unit cost are per item, while Total sales and "
           "Cost are for the whole sale.")
guesses = guess_columns(header)
choices = []
for start in range(0, len(header), PER_ROW):
    cells = st.columns(min(PER_ROW, len(header)))
    for i in range(start, min(start + PER_ROW, len(header))):
        name = header[i].strip() or f"Column {i + 1}"
        with cells[i - start]:
            choices.append(st.selectbox(
                name, LABELS,
                index=LABELS.index(FIELDS[guesses[i]] if guesses[i] else IGNORE),
                key=f"column-{uploaded.file_id}-{i}",
                label_visibility="collapsed",
            ))
            st.dataframe(
                pd.DataFrame({name: [r[i] if i < len(r) else "" for r in rows[:PREVIEW_ROWS]]}),
                hide_index=True,
            )

repeated = [label for label in LABELS[:-1] if choices.count(label) > 1]
if repeated:
    st.warning("More than one column is set to " + ", ".join(repeated)
               + ". Each can only be used once.")
    st.stop()

columns = {KEY_OF[c]: i for i, c in enumerate(choices) if c != IGNORE}
if not columns:
    st.info("Set at least one column (like Date or Total sales) to build the report.")
    st.stop()
st.caption("Using: " + ", ".join(f"{c} = {header[i].strip() or f'Column {i + 1}'}"
                                 for i, c in enumerate(choices) if c != IGNORE))

# Dates like 01/09/2026 can be read either way round
day_first = True
if "date" in columns:
    idx = columns["date"]
    order = date_order(r[idx] for r in rows if idx < len(r))
    if order == "unknown":
        pick = st.radio("Dates like 01/09/2026 are written", ["Day first (1 Sep)", "Month first (9 Jan)"],
                        horizontal=True, key=f"date-order-{uploaded.file_id}")
        day_first = pick.startswith("Day")
    elif order in ("day", "month"):
        day_first = order == "day"
        st.caption("Dates read as " + ("day first." if day_first else "month first."))

tips = []
if "date" not in columns:
    tips.append("a Date column for monthly sales")
if "total" not in columns and "price" not in columns:
    tips.append("Total sales or Price for sales figures")
elif "cost" not in columns and "unit_cost" not in columns:
    tips.append("Cost or Unit cost for profit")
if "product" not in columns:
    tips.append("Product for the best seller")
if tips:
    st.caption("To unlock more, also set " + "; ".join(tips) + ".")

try:
    summary = summarize(read_sales_mapped(rows, columns, day_first))
except ValueError as e:
    st.error(f"Couldn't read the file with those choices: {e}. "
             "Check that each column is set correctly.")
    st.stop()

if summary is None:
    st.warning("No sales found in that file.")
    st.stop()

st.divider()
period = period_text(summary)
if period:
    st.caption(period)
facts = headline_facts(summary)
for start in range(0, len(facts), 3):
    for col, (label, value, detail) in zip(st.columns(3), facts[start:start + 3]):
        col.metric(label, value, detail, delta_color="off")

monthly = summary["monthly"]
if monthly:
    st.subheader(monthly_title(monthly))
    st.pyplot(build_monthly_chart(monthly))
    st.dataframe(
        pd.DataFrame({
            "Month": [month_label(m) for m in monthly["values"]],
            "Sales": [monthly_text(monthly, v) for v in monthly["values"].values()],
        }),
        hide_index=True,
    )

if summary["groups"]:
    st.subheader("Breakdown")
    tabs = st.tabs(list(summary["groups"]))
    for tab, (label, group) in zip(tabs, summary["groups"].items()):
        with tab:
            headers, body = group_table(group, GROUP_ROWS)
            st.dataframe(pd.DataFrame(body, columns=[label, *headers]), hide_index=True)
            if len(group) > GROUP_ROWS:
                st.caption(f"Top {GROUP_ROWS} of {len(group)}.")

st.download_button(
    "Download PDF",
    data=build_pdf(summary, title=f"Sales report: {uploaded.name}"),
    file_name=f"{Path(uploaded.name).stem}_report.pdf",
    mime="application/pdf",
)
