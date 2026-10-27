import argparse
import csv
import difflib
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# What a CSV column can be: key -> the label shown in the app's dropdowns
FIELDS = {
    "date": "Date",
    "product": "Product",
    "quantity": "Quantity",
    "price": "Price",  # per item
    "total": "Total sales",  # for the whole sale line
    "category": "Category",
    "customer": "Customer",
    "branch": "Branch",
    "cost": "Cost",  # for the whole sale line
    "unit_cost": "Unit cost",  # per item
    "payment": "Payment method",
    "order_id": "Order ID",
    "staff": "Staff",
}

# Fields that get a "sales by ..." breakdown
GROUPS = ["product", "category", "customer", "branch", "payment", "staff"]

# ---------- dates ----------

_ISO = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
_DAY_FIRST = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"]
_MONTH_FIRST = ["%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y", "%m/%d/%y", "%m-%d-%y", "%m.%d.%y"]
_WORDS = ["%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y", "%b %d, %Y", "%B %d, %Y",
          "%b %d %Y", "%B %d %Y", "%d %b %y", "%d-%b-%y"]
_TIME = re.compile(r"[T\s]+\d{1,2}:\d{2}.*$", re.I)
_ORDINAL = re.compile(r"(\d)(st|nd|rd|th)\b", re.I)
_NUMERIC_DATE = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-]\d{2,4}")


def parse_date(text, day_first=True):
    """Read 2026-09-01, 01/09/2026, 1 Sep 2026 and similar. Any time of day is ignored."""
    cleaned = _ORDINAL.sub(r"\1", _TIME.sub("", " ".join(text.split())))
    numeric = _DAY_FIRST if day_first else _MONTH_FIRST
    for fmt in _ISO + numeric + _WORDS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date '{text}' isn't one I understand "
                     "(try 2026-09-01, 01/09/2026 or 1 Sep 2026)")


def date_order(texts):
    """How numeric dates like 01/09/2026 are ordered: "day" or "month" when some date
    settles it (13/09/2026 can only be day first), "unknown" when they're all
    ambiguous, "none" when there aren't any."""
    seen = False
    for text in texts:
        match = _NUMERIC_DATE.match(text)
        if match:
            first, second = int(match[1]), int(match[2])
            if first > 12:
                return "day"
            if second > 12:
                return "month"
            seen = True
    return "unknown" if seen else "none"


# ---------- guessing which column is which ----------

# Names that mean each field. Capitals, spaces, underscores and punctuation are
# ignored when comparing, so "Cost_Price", "cost price" and "COSTPRICE" are the same.
# A name can belong to two fields ("amount"); the values then decide which one.
HEADER_NAMES = {
    "date": ["date", "day", "order date", "sale date", "sold date", "sold on",
             "transaction date", "purchase date", "date of sale", "datetime", "timestamp"],
    "product": ["product", "product name", "item", "item name", "menu item", "goods", "article"],
    "quantity": ["quantity", "qty", "units", "units sold", "unit sold", "qty sold",
                 "amount", "count", "pieces", "pcs", "number of items", "no of items"],
    "price": ["price", "unit price", "price per item", "item price", "selling price",
              "sale price", "price each"],
    "total": ["total", "total sales", "sales", "revenue", "total price", "line total",
              "grand total", "sale amount", "total amount", "net sales", "amount"],
    "category": ["category", "product category", "item category", "type", "product type",
                 "department"],
    "customer": ["customer", "customer name", "client", "client name", "buyer", "shopper",
                 "guest", "member"],
    "branch": ["branch", "branch name", "store", "store name", "location", "shop",
               "shop name", "outlet", "site"],
    "cost": ["cost", "total cost", "cost price", "cogs"],
    "unit_cost": ["unit cost", "cost per item", "cost per unit", "item cost"],
    "payment": ["payment method", "payment", "payment type", "payment mode", "paid by",
                "pay mode", "tender"],
    "order_id": ["order id", "order", "order number", "order no", "transaction id",
                 "transaction", "receipt", "receipt number", "invoice", "invoice number",
                 "invoice no", "ticket"],
    "staff": ["staff", "staff name", "employee", "employee name", "cashier", "server",
              "salesperson", "sales rep", "seller", "waiter", "barista"],
}

# Payment words, so a column of "Card" / "Cash" / "Visa" is recognised by its values
_PAYMENT_WORDS = {"cash", "card", "credit", "debit", "creditcard", "debitcard", "visa",
                  "mastercard", "amex", "americanexpress", "paypal", "applepay", "googlepay",
                  "gpay", "venmo", "upi", "cheque", "check", "banktransfer", "transfer",
                  "mobile", "mobilepay", "giftcard", "voucher", "contactless"}

_SAMPLE_ROWS = 500


def _norm(text):
    """Lower-case, without anything in brackets, and only letters and digits."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[(\[].*?[)\]]", " ", text.lower()))


_LOOKUP = {}
for _key, _names in HEADER_NAMES.items():
    for _name in _names:
        _LOOKUP.setdefault(_norm(_name), []).append(_key)


def _as_number(text):
    try:
        return float(text.strip().lstrip("$£€₹¥").replace(",", ""))
    except ValueError:
        return None


def _is_date(text):
    for day_first in (True, False):
        try:
            parse_date(text, day_first)
            return True
        except ValueError:
            pass
    return False


def _mostly(values, test, share=0.9):
    return sum(1 for v in values if test(v)) >= share * len(values)


def _fits(key, values):
    """Do these values make sense for this kind of column?"""
    if key in ("price", "total", "cost", "unit_cost"):
        return _mostly(values, lambda v: _as_number(v) is not None)
    if key == "quantity":
        return _mostly(values, lambda v: _as_number(v) is not None and _as_number(v).is_integer())
    if key == "date":
        return _mostly(values, _is_date)
    return True


def guess_columns(header, rows=()):
    """For each column, a guess (field, how) or None when nothing fits well.

    `how` says what the guess is based on: "name" (the header is a known name),
    "similar" (a close spelling or variant of one) or "data" (the values look like
    dates or payment methods). A name match is only kept if the values agree, so a
    "Date" column full of words is not trusted. Each field is given to one column."""
    rows = list(rows)[:_SAMPLE_ROWS]
    candidates = []  # (score, column, field, how); better evidence wins, then leftmost
    for i, name in enumerate(header):
        values = [r[i].strip() for r in rows if i < len(r) and r[i].strip()]
        if rows and not values:
            continue  # an empty column can't be anything

        norm = _norm(name)
        how, keys = "name", _LOOKUP.get(norm)
        if not keys and len(norm) >= 4:
            close = difflib.get_close_matches(norm, _LOOKUP, n=1, cutoff=0.84)
            how, keys = "similar", _LOOKUP[close[0]] if close else None
        key = next((k for k in keys or [] if not rows or _fits(k, values)), None)
        if key:
            candidates.append((3 if how == "name" else 2, i, key, how))
        elif rows and _fits("date", values):
            candidates.append((1, i, "date", "data"))
        elif rows and _mostly(values, lambda v: _norm(v) in _PAYMENT_WORDS, share=0.8):
            candidates.append((1, i, "payment", "data"))

    guesses, used = [None] * len(header), set()
    for _, i, key, how in sorted(candidates, key=lambda c: (-c[0], c[1])):
        if guesses[i] is None and key not in used:
            guesses[i] = (key, how)
            used.add(key)
    return guesses


# ---------- reading ----------

def _number(label, text):
    value = _as_number(text)
    if value is None:
        raise ValueError(f"{label} '{text}' isn't a number")
    return value


def _whole(label, text):
    value = _number(label, text)
    if not value.is_integer():
        raise ValueError(f"{label} '{text}' isn't a whole number")
    return int(value)


def _text(value):
    return None if value is None else value or "(blank)"


def _build_sale(row, columns, day_first):
    def cell(key):
        return row[columns[key]].strip() if key in columns else None

    quantity = _whole("Quantity", cell("quantity")) if "quantity" in columns else None
    units = 1 if quantity is None else quantity  # no Quantity column: one item per row

    if "total" in columns:
        revenue = _number("Total sales", cell("total"))
    elif "price" in columns:
        revenue = _number("Price", cell("price")) * units
    else:
        revenue = None

    if "cost" in columns:
        cost = _number("Cost", cell("cost"))
    elif "unit_cost" in columns:
        cost = _number("Unit cost", cell("unit_cost")) * units
    else:
        cost = None

    return {
        "date": parse_date(cell("date"), day_first) if "date" in columns else None,
        "quantity": quantity,
        "revenue": revenue,
        "cost": cost,
        **{key: _text(cell(key)) for key in GROUPS + ["order_id"]},
    }


def read_sales_mapped(rows, columns, day_first=True):
    """Parse sales from lists of cells; columns maps a field name to its column number."""
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            sale = _build_sale(row, columns, day_first)
        except IndexError:
            raise ValueError(f"row {n} doesn't have enough columns") from None
        except ValueError as e:
            raise ValueError(f"row {n}: {e}") from None
        yield sale


# ---------- summary ----------

def summarize(sales):
    """Everything the chosen columns allow, or None if there are no sales.
    Entries the columns can't support are None (or left out)."""
    sales = list(sales)
    if not sales:
        return None
    first = sales[0]
    has_qty = first["quantity"] is not None
    has_rev = first["revenue"] is not None
    has_cost = first["cost"] is not None
    has_date = first["date"] is not None

    revenue = sum(s["revenue"] for s in sales) if has_rev else None
    cost = sum(s["cost"] for s in sales) if has_cost else None
    profit = revenue - cost if has_rev and has_cost else None
    orders = len({s["order_id"] for s in sales}) if first["order_id"] is not None else None

    groups = {}
    for key in GROUPS:
        if first[key] is None:
            continue
        totals = defaultdict(lambda: {"sales": 0, "units": 0, "revenue": 0.0, "profit": 0.0})
        for s in sales:
            t = totals[s[key]]
            t["sales"] += 1
            if has_qty:
                t["units"] += s["quantity"]
            if has_rev:
                t["revenue"] += s["revenue"]
            if profit is not None:
                t["profit"] += s["revenue"] - s["cost"]
        rows = [{"name": name,
                 "sales": t["sales"],
                 "units": t["units"] if has_qty else None,
                 "revenue": t["revenue"] if has_rev else None,
                 "profit": t["profit"] if profit is not None else None}
                for name, t in totals.items()]
        rows.sort(key=lambda r: (-(r["revenue"] if has_rev else r["sales"]), r["name"]))
        groups[FIELDS[key]] = rows

    best = None
    if FIELDS["product"] in groups:
        by_units = [(r["units"] if has_qty else r["sales"], r) for r in groups[FIELDS["product"]]]
        _, top = min(by_units, key=lambda p: (-p[0], p[1]["name"]))
        best = {**top, "basis": "units" if has_qty else "sales"}

    monthly = None
    if has_date:
        values = defaultdict(float)
        for s in sales:
            values[s["date"].strftime("%Y-%m")] += s["revenue"] if has_rev else 1
        monthly = {"values": dict(sorted(values.items())),
                   "metric": "revenue" if has_rev else "sales"}

    return {
        "count": len(sales),
        "items": sum(s["quantity"] for s in sales) if has_qty else None,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "margin": profit / revenue * 100 if profit is not None and revenue else None,
        "orders": orders,
        "avg_order": revenue / orders if has_rev and orders else None,
        "first_date": min(s["date"] for s in sales) if has_date else None,
        "last_date": max(s["date"] for s in sales) if has_date else None,
        "best": best,
        "monthly": monthly,
        "groups": groups,
    }


# ---------- text shared by the CLI, the app and the PDF ----------

def money(value):
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def month_label(month, fmt="%B %Y"):
    return datetime.strptime(month, "%Y-%m").strftime(fmt)


def period_text(summary):
    if summary["first_date"] is None:
        return None
    first, last = summary["first_date"], summary["last_date"]
    return f"{first.day} {first:%b %Y} to {last.day} {last:%b %Y}"


def headline_facts(summary):
    """(label, value, detail or None) for each headline figure the data supports."""
    facts = []
    if summary["revenue"] is not None:
        facts.append(("Total sales", money(summary["revenue"]), None))
    items = summary["items"]
    facts.append(("Sales", f"{summary['count']:,}",
                  None if items is None else f"{items:,} items"))
    if summary["profit"] is not None:
        margin = summary["margin"]
        facts.append(("Profit", money(summary["profit"]),
                      None if margin is None else f"{margin:.1f}% margin"))
    if summary["orders"] is not None:
        avg = summary["avg_order"]
        facts.append(("Orders", f"{summary['orders']:,}",
                      None if avg is None else f"average {money(avg)}"))
    best = summary["best"]
    if best:
        detail = [f"{best['units']:,} units" if best["basis"] == "units"
                  else f"{best['sales']:,} sales"]
        if best["revenue"] is not None:
            detail.append(money(best["revenue"]))
        facts.append(("Best seller", best["name"], ", ".join(detail)))
    return facts


def group_table(rows, limit=None):
    """(column headers after the name, body rows of text) for a breakdown."""
    first = rows[0]
    headers = ["Sales"]
    for header, key in [("Units", "units"), ("Revenue", "revenue"), ("Profit", "profit")]:
        if first[key] is not None:
            headers.append(header)
    body = []
    for r in rows[:limit]:
        cells = [f"{r['sales']:,}"]
        if "Units" in headers:
            cells.append(f"{r['units']:,}")
        if "Revenue" in headers:
            cells.append(money(r["revenue"]))
        if "Profit" in headers:
            cells.append(money(r["profit"]))
        body.append([r["name"], *cells])
    return headers, body


def monthly_title(monthly):
    return "Monthly sales" if monthly["metric"] == "revenue" else "Sales per month"


def monthly_text(monthly, value):
    return money(value) if monthly["metric"] == "revenue" else f"{value:,.0f}"


# ---------- chart and PDF ----------

def build_monthly_chart(monthly):
    """Return a matplotlib Figure of monthly sales (needs matplotlib)."""
    from matplotlib.figure import Figure

    values = monthly["values"]
    months = list(values)
    labels = [month_label(m, "%b %Y") for m in months]
    totals = list(values.values())
    as_money = monthly["metric"] == "revenue"

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    fig = Figure(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor(surface)
    ax = fig.subplots()
    ax.set_facecolor(surface)

    bars = ax.bar(labels, totals, width=0.5, color="#2a78d6", zorder=2)
    ax.bar_label(bars, labels=[f"${t:,.0f}" if as_money else f"{t:,.0f}" for t in totals],
                 padding=4, color=ink, fontsize=10)

    ax.set_title(monthly_title(monthly), loc="left", color=ink,
                 fontsize=13, fontweight="bold", pad=14)
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}" if as_money else f"{v:,.0f}")
    ax.set_ylim(0, max(totals) * 1.15)
    ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
    ax.tick_params(colors=muted, length=0, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(muted)

    fig.tight_layout()
    return fig


def build_pdf(summary, title="Sales report", table_rows=5):
    """Return the report as PDF bytes: the headline figures, the monthly chart
    and a short table for each breakdown, for whatever the data supports."""
    import io
    from fpdf import FPDF

    # The built-in PDF fonts only cover Latin-1, so swap anything else for "?"
    def latin1(text):
        return str(text).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, latin1(title), new_x="LMARGIN", new_y="NEXT")
    period = period_text(summary)
    if period:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(0, 7, period, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for label, value, detail in headline_facts(summary):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(35, 8, label)
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 8, latin1(value + (f" ({detail})" if detail else "")),
                 new_x="LMARGIN", new_y="NEXT")

    if summary["monthly"]:
        fig = build_monthly_chart(summary["monthly"])
        chart = io.BytesIO()
        fig.savefig(chart, format="png", facecolor=fig.get_facecolor())
        chart.seek(0)
        height = pdf.epw * 4.2 / 7
        if pdf.get_y() + height + 6 > pdf.page_break_trigger:
            pdf.add_page()
        pdf.ln(6)
        top = pdf.get_y()
        pdf.image(chart, w=pdf.epw)
        pdf.set_y(top + height)

    for label, rows in summary["groups"].items():
        headers, body = group_table(rows, table_rows)
        if pdf.get_y() + 8 * (len(body) + 3) > pdf.page_break_trigger:
            pdf.add_page()
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 13)
        more = f" (top {table_rows} of {len(rows)})" if len(rows) > table_rows else ""
        pdf.cell(0, 9, latin1(f"By {label.lower()}{more}"), new_x="LMARGIN", new_y="NEXT")

        num_w = 28
        name_w = pdf.epw - num_w * len(headers)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(240, 240, 238)
        pdf.cell(name_w, 7, latin1(label), fill=True)
        for j, header in enumerate(headers):
            last = j == len(headers) - 1
            pdf.cell(num_w, 7, header, align="R", fill=True,
                     **({"new_x": "LMARGIN", "new_y": "NEXT"} if last else {}))
        pdf.set_font("Helvetica", "", 10)
        for name, *cells in body:
            pdf.cell(name_w, 7, latin1(name[:40]), border="B")
            for j, text in enumerate(cells):
                last = j == len(cells) - 1
                pdf.cell(num_w, 7, text, align="R", border="B",
                         **({"new_x": "LMARGIN", "new_y": "NEXT"} if last else {}))
    return bytes(pdf.output())


def save_monthly_chart(monthly, out_path):
    try:
        fig = build_monthly_chart(monthly)
    except ImportError:
        print("\n(Skipping chart: install matplotlib with "
              "'python3 -m pip install matplotlib')")
        return

    fig.savefig(out_path, facecolor=fig.get_facecolor())
    print(f"\nChart saved to {out_path}")


# ---------- command line ----------

def main(path=HERE / "sales.csv"):
    with open(path, newline="", encoding="utf-8-sig") as f:
        table = [row for row in csv.reader(f) if row]
    if not table:
        print(f"No sales found in {path}.")
        return
    header, rows = table[0], table[1:]

    columns = {g[0]: i for i, g in enumerate(guess_columns(header, rows)) if g}
    if not columns:
        sys.exit(f"Error: no column names in '{path}' that I recognise. Expected headers "
                 "such as date, product, quantity, price.")
    day_first = True
    if "date" in columns:
        day_first = date_order(r[columns["date"]] for r in rows if columns["date"] < len(r)) != "month"

    summary = summarize(read_sales_mapped(rows, columns, day_first))
    if summary is None:
        print(f"No sales found in {path}.")
        return

    print(f"Sales report for {Path(path).name}")
    print("=" * 32)
    if period_text(summary):
        print(f"Period:       {period_text(summary)}")
    for label, value, detail in headline_facts(summary):
        print(f"{label + ':':<13} {value}" + (f" ({detail})" if detail else ""))

    monthly = summary["monthly"]
    if monthly:
        print(f"\n{monthly_title(monthly)}:")
        for month, value in monthly["values"].items():
            print(f"  {month_label(month):<15} {monthly_text(monthly, value):>11}")

    for label, group in summary["groups"].items():
        headers, body = group_table(group, limit=5)
        print(f"\nBy {label.lower()} ({', '.join(h.lower() for h in headers)}):")
        for name, *cells in body:
            print(f"  {name[:28]:<30}" + "  ".join(f"{c:>11}" for c in cells))

    if monthly:
        # Chart goes next to the CSV it was made from
        save_monthly_chart(monthly, Path(path).parent / "monthly_sales.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Summarize a sales CSV and save a monthly sales chart next to it. "
                    "Columns are found by their header names (date, product, quantity, "
                    "price, total sales, category, customer, branch, cost, ...); the "
                    "report covers whatever those columns allow.")
    parser.add_argument("csv", nargs="?", default=HERE / "sales.csv", type=Path,
                        help="CSV file to read (default: sales.csv next to this script)")
    args = parser.parse_args()

    try:
        main(args.csv)
    except FileNotFoundError:
        sys.exit(f"Error: can't find '{args.csv}'.")
    except UnicodeDecodeError:
        sys.exit(f"Error: '{args.csv}' isn't a text CSV file.")
    except ValueError as e:
        sys.exit(f"Error: bad value in '{args.csv}': {e}")
