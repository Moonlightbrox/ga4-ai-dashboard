"""
test_raw_report.py
=====================================================================
Manual test runner for RAW ANALYTICAL TABLES

Usage:
    python -m scripts.test_raw_report traffic
"""

import sys

from analytics.raw_reports import (
    get_template_table,
    get_landingpage_table,
)

# =====================================================================
# CONFIG
# =====================================================================

START_DATE = "30daysAgo"
END_DATE = "today"

# ---------------------------------------------------------------------
# REPORT REGISTRY
# ---------------------------------------------------------------------
# Maps CLI argument -> function that builds the report
# This is the ONLY place you need to edit to add new reports
# ---------------------------------------------------------------------

REPORTS = {
    "template": get_template_table,
    "landingpage": get_landingpage_table,
}


# =====================================================================
# RUNNER
# =====================================================================

def main():
    if len(sys.argv) < 2:
        print("❌ Please specify a report to run.")
        print("Available reports:")
        for name in REPORTS:
            print(f" - {name}")
        sys.exit(1)

    report_name = sys.argv[1]

    if report_name not in REPORTS:
        print(f"❌ Unknown report: '{report_name}'")
        print("Available reports:")
        for name in REPORTS:
            print(f" - {name}")
        sys.exit(1)

    print(f"▶ Running report: {report_name}")

    report_fn = REPORTS[report_name]

    df = report_fn(
        start_date=START_DATE,
        end_date=END_DATE,
    )

    # -----------------------------------------------------------------
    # Basic sanity checks
    # -----------------------------------------------------------------
    print(f"\n{report_name.upper()} TABLE")
    print("Rows:", len(df))
    print("Columns:", list(df.columns))
    print(df.head())

    # -----------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------
    csv_path = f"{report_name}_table.csv"
    json_path = f"{report_name}_table.json"

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)

    print("\nExported:")
    print(f"- {csv_path}")
    print(f"- {json_path}")


if __name__ == "__main__":
    main()
