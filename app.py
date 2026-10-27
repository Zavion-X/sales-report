import io

import pandas as pd
import streamlit as st

from report import build_monthly_chart, month_label, read_sales, summarize

st.set_page_config(page_title="Sales report", page_icon="📊")
st.title("Sales report")
st.caption("Upload a CSV with the columns: date, product, quantity, price")

uploaded = st.file_uploader("Sales CSV", type="csv")
if uploaded is None:
    st.info("Upload a CSV file to see the report.")
    st.stop()

try:
    text = io.StringIO(uploaded.getvalue().decode("utf-8-sig"), newline="")
    summary = summarize(read_sales(text))
except UnicodeDecodeError:
    st.error("That file isn't a text CSV. Please upload a .csv file.")
    st.stop()
except KeyError as e:
    st.error(f"The file is missing the {e} column. "
             "Expected columns: date, product, quantity, price.")
    st.stop()
except ValueError as e:
    st.error(f"Bad value in the file: {e}")
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
