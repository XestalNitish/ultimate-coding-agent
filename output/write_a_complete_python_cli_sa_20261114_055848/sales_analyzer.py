import csv
import json
import sqlite3
import sys
from datetime import datetime


def parse_csv(csv_string):
    reader = csv.DictReader(csv_string.splitlines())
    rows = []
    for row in reader:
        rows.append(
            {
                "id": row.get("id", ""),
                "date": row.get("date", ""),
                "product": row.get("product", ""),
                "category": row.get("category", ""),
                "quantity": int(row.get("quantity", 0)),
                "unit_price": float(row.get("unit_price", 0.0)),
                "total_amount": float(row.get("total_amount", 0.0)),
            }
        )
    return rows


def _init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            product TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_amount REAL NOT NULL
        )
        """
    )
    conn.commit()


def analyze(conn, rows):
    _init_db(conn)
    for row in rows:
        conn.execute(
            """
            INSERT INTO transactions (id, date, product, category, quantity, unit_price, total_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["date"],
                row["product"],
                row["category"],
                row["quantity"],
                row["unit_price"],
                row["total_amount"],
            ),
        )
    conn.commit()

    total_revenue = conn.execute(
        "SELECT SUM(total_amount) AS total FROM transactions"
    ).fetchone()[0]

    monthly_growth = []
    if rows:
        months = sorted({row["date"] for row in rows})
        for i in range(1, len(months)):
            prev_month = months[i - 1]
            curr_month = months[i]
            prev_revenue = conn.execute(
                "SELECT SUM(total_amount) AS total FROM transactions WHERE date LIKE ?",
                (f"{prev_month}%",),
            ).fetchone()[0]
            curr_revenue = conn.execute(
                "SELECT SUM(total_amount) AS total FROM transactions WHERE date LIKE ?",
                (f"{curr_month}%",),
            ).fetchone()[0]
            monthly_growth.append(
                {
                    "from_month": prev_month,
                    "to_month": curr_month,
                    "revenue_from": round(prev_revenue, 2),
                    "revenue_to": round(curr_revenue, 2),
                    "growth": round(curr_revenue - prev_revenue, 2),
                }
            )

    category_breakdown = []
    for category, revenue in conn.execute(
        "SELECT category, SUM(total_amount) AS revenue FROM transactions GROUP BY category ORDER BY revenue DESC"
    ):
        category_breakdown.append(
            {
                "category": category,
                "revenue": round(revenue, 2),
            }
        )

    return {
        "total_revenue": round(total_revenue, 2),
        "monthly_growth": monthly_growth,
        "top_categories": category_breakdown,
    }


def generate_text_report(report):
    lines = []
    lines.append("SALES ANALYTICS REPORT")
    lines.append("=" * 20)
    lines.append(f"Total Revenue: ${report['total_revenue']:.2f}")
    lines.append("")
    lines.append("Monthly Growth:")
    if report["monthly_growth"]:
        for item in report["monthly_growth"]:
            delta = item["growth"]
            delta_str = f"+${delta:.2f}" if delta >= 0 else f"-${abs(delta):.2f}"
            lines.append(
                f"  {item['from_month']} -> {item['to_month']}: "
                f"${item['revenue_from']:.2f} -> ${item['revenue_to']:.2f} ({delta_str})"
            )
    else:
        lines.append("  No monthly growth data available.")
    lines.append("")
    lines.append("Top Categories by Revenue:")
    if report["top_categories"]:
        for item in report["top_categories"]:
            lines.append(f"  {item['category']}: ${item['revenue']:.2f}")
    else:
        lines.append("  No category data available.")
    return "\n".join(lines)


def generate_json_report(report):
    return json.dumps(report, indent=2, default=str)


def selftest():
    csv_string = (
        "id,date,product,category,quantity,unit_price,total_amount\n"
        "1,2024-01-05,Widget,A,2,10.00,20.00\n"
        "2,2024-01-10,Widget,B,1,15.00,15.00\n"
        "3,2024-02-01,Gadget,C,3,8.00,24.00\n"
        "4,2024-02-15,Gadget,C,2,9.00,18.00\n"
    )
    rows = parse_csv(csv_string)
    assert len(rows) == 4, "CSV parsing should return 4 rows"

    conn = sqlite3.connect(":memory:")
    analyze(conn, rows)

    inserted = conn.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()[0]
    assert inserted == 4, "Database insertion should store all 4 parsed rows"

    total_revenue = conn.execute("SELECT SUM(total_amount) AS total FROM transactions").fetchone()[0]
    assert abs(total_revenue - 77.0) < 0.01, "Total revenue aggregation should match expected value"

    breakdown = dict(conn.execute("SELECT category, SUM(total_amount) AS revenue FROM transactions GROUP BY category"))
    assert breakdown.get("A") == 20.0, "Category breakdown should match expected revenue"
    assert breakdown.get("C") == 42.0, "Category breakdown should match expected revenue"

    conn.close()
    return True


def main():
    if len(sys.argv) == 1:
        selftest()
        print("SELFTEST OK")
        return

    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    if mode not in ("text", "json"):
        print("Invalid mode. Use 'text' or 'json'.", file=sys.stderr)
        return

    csv_string = (
        "id,date,product,category,quantity,unit_price,total_amount\n"
        "1,2024-01-05,Widget,A,2,10.00,20.00\n"
        "2,2024-01-10,Widget,B,1,15.00,15.00\n"
        "3,2024-02-01,Gadget,C,3,8.00,24.00\n"
        "4,2024-02-15,Gadget,C,2,9.00,18.00\n"
    )
    rows = parse_csv(csv_string)
    conn = sqlite3.connect(":memory:")
    report = analyze(conn, rows)
    conn.close()

    if mode == "json":
        print(generate_json_report(report))
    else:
        print(generate_text_report(report))


if __name__ == "__main__":
    main()