import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read_sales(lines):
    """Parse sales from an iterable of CSV text lines."""
    for row in csv.DictReader(lines):
        quantity = int(row["quantity"])
        yield {
            "date": date.fromisoformat(row["date"]),
            "product": row["product"],
            "quantity": quantity,
            "total": quantity * float(row["price"]),
        }


def load_sales(path):
    with open(path, newline="") as f:
        yield from read_sales(f)


def summarize(sales):
    """Totals, best seller and monthly sales, or None if there are no sales."""
    units = defaultdict(int)
    revenue = defaultdict(float)
    by_month = defaultdict(float)
    grand_total = 0.0
    count = 0

    for sale in sales:
        units[sale["product"]] += sale["quantity"]
        revenue[sale["product"]] += sale["total"]
        by_month[sale["date"].strftime("%Y-%m")] += sale["total"]
        grand_total += sale["total"]
        count += 1

    if not count:
        return None

    # Best seller is the product with the most units sold
    best = max(units, key=units.get)
    return {
        "count": count,
        "items": sum(units.values()),
        "total": grand_total,
        "best": best,
        "best_units": units[best],
        "best_revenue": revenue[best],
        "by_month": dict(sorted(by_month.items())),
    }


def month_label(month, fmt="%B %Y"):
    return date.fromisoformat(month + "-01").strftime(fmt)


def build_monthly_chart(by_month):
    """Return a matplotlib Figure of monthly sales (needs matplotlib)."""
    from matplotlib.figure import Figure

    months = sorted(by_month)
    labels = [month_label(m, "%b %Y") for m in months]
    totals = [by_month[m] for m in months]

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    fig = Figure(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor(surface)
    ax = fig.subplots()
    ax.set_facecolor(surface)

    bars = ax.bar(labels, totals, width=0.5, color="#2a78d6", zorder=2)
    ax.bar_label(bars, labels=[f"${t:,.0f}" for t in totals],
                 padding=4, color=ink, fontsize=10)

    ax.set_title("Monthly sales", loc="left", color=ink,
                 fontsize=13, fontweight="bold", pad=14)
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.set_ylim(0, max(totals) * 1.15)
    ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
    ax.tick_params(colors=muted, length=0, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(muted)

    fig.tight_layout()
    return fig


def save_monthly_chart(by_month, out_path):
    try:
        fig = build_monthly_chart(by_month)
    except ImportError:
        print("\n(Skipping chart: install matplotlib with "
              "'python3 -m pip install matplotlib')")
        return

    fig.savefig(out_path, facecolor=fig.get_facecolor())
    print(f"\nChart saved to {out_path}")


def main(path=HERE / "sales.csv"):
    summary = summarize(load_sales(path))

    if summary is None:
        print(f"No sales found in {path}.")
        return

    print(f"Sales report for {Path(path).name}")
    print("=" * 32)
    print(f"Total sales:  ${summary['total']:,.2f} from {summary['count']} sales "
          f"({summary['items']} items)")
    print(f"Best seller:  {summary['best']} ({summary['best_units']} units, "
          f"${summary['best_revenue']:,.2f})")

    print("\nSales by month:")
    for month, total in summary["by_month"].items():
        print(f"  {month_label(month):<15} ${total:>9,.2f}")

    # Chart goes next to the CSV it was made from
    save_monthly_chart(summary["by_month"], Path(path).parent / "monthly_sales.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Summarize a sales CSV (columns: date, product, quantity, price) "
                    "and save a monthly sales chart next to it.")
    parser.add_argument("csv", nargs="?", default=HERE / "sales.csv", type=Path,
                        help="CSV file to read (default: sales.csv next to this script)")
    args = parser.parse_args()

    try:
        main(args.csv)
    except FileNotFoundError:
        sys.exit(f"Error: can't find '{args.csv}'.")
    except KeyError as e:
        sys.exit(f"Error: '{args.csv}' is missing the {e} column. "
                 "Expected columns: date, product, quantity, price.")
    except ValueError as e:
        sys.exit(f"Error: bad value in '{args.csv}': {e}")
