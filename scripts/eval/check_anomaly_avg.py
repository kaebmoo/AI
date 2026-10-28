"""Read-only check for "which units are off their earlier average this month" on feed_sales (plan/PLAN_ANOMALY_AVG_FIX.md).

The portal answer of 2026-10-28 compared a month's SUM(amount) with AVG(amount) over the raw rows of the months
before — an average per row (org × product), not per month — so every unit with many rows looked hundreds of
times up. This prints, from the same data the server reads:

  1. one unit's row-average (what the system used) next to its monthly average and month total, for the asked
     month in this year and in the year before (tells which year a pasted answer came from)
  2. company monthly totals (metric = 'actual') from January to the asked month
  3. the units whose month differs from their monthly average of January .. the month before (months with no
     rows count as 0; units with no rows in either side are kept) — the oracle for the fix

Usage (from the AI repo root on the machine that runs the server):
  venv/bin/python scripts/eval/check_anomaly_avg.py --db "$(ls -t .source_cache/datafeed_sales-*.duckdb | head -1)"
  venv/bin/python scripts/eval/check_anomaly_avg.py --csv <NT-Report>/DataFeed/dist/sales/latest/fact_sales.csv
Options: --month 202609 --unit 'ฝ่ายธุรกิจลูกค้าภาครัฐ' --by unit_fname --min-diff 5000000 --min-pct 30 --z 2
"""

import argparse
import re
import sys

import duckdb

VIEW = "feed_sales_fact_sales"


def connect(args):
    if args.db:
        return duckdb.connect(args.db, read_only=True)
    con = duckdb.connect()
    # the server's dialect (database_adapter._build_view_db): the sniffer alone misreads fact_sales.csv;
    # a view cannot take a parameter, hence the quoted literal
    path = "'" + args.csv.replace("'", "''") + "'"
    con.execute(f"CREATE VIEW {VIEW} AS SELECT * FROM read_csv({path}, header=true, delim=',', quote='\"', "
                "escape='\"', sample_size=-1)")
    return con


def unit_check(con, by, unit, month):
    sql = f"""
        SELECT ROUND(AVG(amount) FILTER (WHERE year_month BETWEEN ? AND ?), 2)     AS "เฉลี่ยต่อแถว (ที่ระบบใช้)",
               ROUND(SUM(amount) FILTER (WHERE year_month BETWEEN ? AND ?) / ?, 2) AS "เฉลี่ยต่อเดือน (ที่ควรใช้)",
               ROUND(SUM(amount) FILTER (WHERE year_month = ?), 2)                 AS "ยอดเดือนที่ถาม",
               COUNT(*)    FILTER (WHERE year_month = ?)                           AS "จำนวนแถวเดือนที่ถาม"
        FROM {VIEW} WHERE metric = 'actual' AND {by} = ?"""
    year, mm = divmod(month, 100)
    first, last = year * 100 + 1, month - 1
    return con.execute(sql, [first, last, first, last, mm - 1, month, month, unit]).df()


def company(con, month):
    year = month // 100
    return con.execute(f"""
        SELECT year_month, ROUND(SUM(amount) / 1e6, 2) AS "ล้านบาท" FROM {VIEW}
        WHERE metric = 'actual' AND year_month BETWEEN ? AND ? GROUP BY year_month ORDER BY year_month""",
                       [year * 100 + 1, month]).df()


def anomalies(con, by, month, min_diff, min_pct, z):
    year, mm = divmod(month, 100)
    months = ", ".join(f"({year * 100 + m})" for m in range(1, mm))
    return con.execute(f"""
        WITH monthly AS (
            SELECT {by} AS unit, year_month, SUM(amount) AS amt FROM {VIEW}
            WHERE metric = 'actual' AND year_month BETWEEN ? AND ? GROUP BY 1, 2),
        units AS (SELECT DISTINCT unit FROM monthly),
        months AS (SELECT * FROM (VALUES {months}) AS v(year_month)),
        base AS (
            SELECT u.unit, AVG(COALESCE(m.amt, 0)) AS avg_month, STDDEV_SAMP(COALESCE(m.amt, 0)) AS sd_month
            FROM units u CROSS JOIN months p
            LEFT JOIN monthly m ON m.unit = u.unit AND m.year_month = p.year_month
            GROUP BY u.unit),
        cur AS (
            SELECT u.unit, COALESCE(m.amt, 0) AS amt FROM units u
            LEFT JOIN monthly m ON m.unit = u.unit AND m.year_month = ?)
        SELECT b.unit                                                         AS "หน่วยงาน",
               ROUND(b.avg_month / 1e6, 2)                                    AS "เฉลี่ย/เดือนก่อนหน้า (ล้าน)",
               ROUND(c.amt / 1e6, 2)                                          AS "เดือนที่ถาม (ล้าน)",
               ROUND((c.amt - b.avg_month) / 1e6, 2)                          AS "ส่วนต่าง (ล้าน)",
               ROUND((c.amt - b.avg_month) / NULLIF(ABS(b.avg_month), 0) * 100, 1) AS "% เปลี่ยน",
               ROUND((c.amt - b.avg_month) / NULLIF(b.sd_month, 0), 1)        AS "z"
        FROM base b JOIN cur c ON c.unit = b.unit
        WHERE ABS(c.amt - b.avg_month) >= ?
          AND (ABS(c.amt - b.avg_month) >= ? * ABS(b.avg_month) OR ABS(c.amt - b.avg_month) >= ? * b.sd_month)
        ORDER BY ABS(c.amt - b.avg_month) DESC""",
                       [year * 100 + 1, month, month, min_diff, min_pct / 100, z]).df()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", help=".source_cache/datafeed_sales-*.duckdb (the view the server queries)")
    src.add_argument("--csv", help="DataFeed/dist/sales/latest/fact_sales.csv")
    p.add_argument("--month", type=int, default=202609, help="asked month YYYYMM (ค.ศ.), February or later")
    p.add_argument("--unit", default="ฝ่ายธุรกิจลูกค้าภาครัฐ")
    p.add_argument("--by", default="unit_fname", help="unit column, e.g. unit_fname or unit_fname_current")
    p.add_argument("--min-diff", type=float, default=5e6, help="baht")
    p.add_argument("--min-pct", type=float, default=30.0)
    p.add_argument("--z", type=float, default=2.0)
    args = p.parse_args()
    if not 2 <= args.month % 100 <= 12:
        sys.exit("--month must be YYYYMM with a month from 02 to 12")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.by):
        sys.exit("--by must be a column name")

    con = connect(args)
    for month in (args.month, args.month - 100):
        print(f"\n== 1) {args.unit}: เดือน {month} เทียบ ม.ค.–เดือนก่อนหน้า")
        print(unit_check(con, args.by, args.unit, month).to_string(index=False))
    print(f"\n== 2) ยอดขายทั้งบริษัทรายเดือน (actual) ถึง {args.month}")
    print(company(con, args.month).to_string(index=False))
    print(f"\n== 3) หน่วยงานที่เดือน {args.month} ต่างจากค่าเฉลี่ยต่อเดือนก่อนหน้า (>= {args.min_diff:,.0f} บาท และ "
          f">= {args.min_pct:g}% หรือ >= {args.z:g} SD)")
    print(anomalies(con, args.by, args.month, args.min_diff, args.min_pct, args.z).to_string(index=False))


if __name__ == "__main__":
    main()
