"""Convert Telco Customer Churn CSV to ChurnIQ bulk-import format.

Usage:
    python backend/scripts/import_telco_data.py [--preview] [--input PATH] [--output PATH]

    --preview   Print 5 sample rows and exit (no output file written).
    --input     Path to the raw Telco CSV (default: the WA_Fn... file in Downloads).
    --output    Path for the ChurnIQ-ready CSV (default: backend/sample_data/telco_import.csv).

Column mapping notes
--------------------
DIRECT mappings (value taken as-is or with trivial coercion):
  customerID      → external_id  (kept as-is)
  MonthlyCharges  → monthly_revenue
  Churn           → is_churned  (Yes/No → True/False)

DERIVED mappings (computed from Telco columns):
  customerID      → name          "Telco-<customerID>" placeholder (no name in dataset)
  tenure (months) → signup_date   ref_date − tenure×30 days  (ref_date = 2024-01-15)
  Contract        → plan          Month-to-month→starter | One year→growth | Two year→enterprise
  Contract        → contract_length_months   null / 12 / 24
  signup_date + months → contract_end_date
  Churn + ref     → last_activity_date   active=ref_date, churned=ref_date−30d
  Churn + ref     → churned_at   ref_date for churned rows

PROXY mappings (no direct equivalent; reasonable signal derived from related columns):
  InternetService → logins_last_30d
      Fiber optic: 15 active / 4 churned
      DSL:          8 active / 2 churned
      No internet:  3 active / 1 churned
      Rationale: internet tier is the best available proxy for digital engagement.

  service count   → feature_usage_score  (0-100)
      Services scored: PhoneService, OnlineSecurity, OnlineBackup, DeviceProtection,
                       TechSupport, StreamingTV, StreamingMovies + MultipleLines bonus.
      feature_usage_score = (active_service_count / 8) * 100

  tenure + TechSupport → support_tickets_total
      Without TechSupport: approx 1 ticket per 12 months (tenure÷12, min 0)
      With TechSupport:    approx 1 ticket per 24 months (tenure÷24, min 0)
      Rationale: TechSupport subscription inversely correlates with raw ticket volume.

  support_tickets_open = 0 for all rows (no open-ticket data in Telco dataset).

  PaymentMethod → billing_issues_count
      Electronic check:         2 (churned) / 1 (active)
      Mailed check:             1 (churned) / 0 (active)
      Bank/Credit card (auto):  0
      Rationale: electronic check historically has highest churn correlation in Telco.

NO EQUIVALENT (left null → XGBoost SimpleImputer fills with median at scoring time):
  nps_score       (no survey data in dataset)
  company_size    (Telco is B2C — no B2B firmographics)

CONSTANTS applied to all rows:
  country  = "US"  (dataset is a US telecom provider)
  industry = "Telecommunications"
"""

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
_DEFAULT_INPUT = Path(
    r"C:\Users\LENOVO\Downloads\cust churn data\WA_Fn-UseC_-Telco-Customer-Churn.csv"
)
_DEFAULT_OUTPUT = Path(__file__).parents[1] / "sample_data" / "telco_import.csv"

# Anchor date: treat this as the "as-of" date for the entire dataset.
# All tenure calculations are relative to this date.
_REF_DATE = date(2024, 1, 15)

# ChurnIQ output columns in the order the bulk-import endpoint expects
_OUTPUT_COLUMNS = [
    "external_id",
    "name",
    "email",
    "phone",
    "plan",
    "monthly_revenue",
    "contract_length_months",
    "signup_date",
    "contract_end_date",
    "last_activity_date",
    "logins_last_30d",
    "feature_usage_score",
    "support_tickets_open",
    "support_tickets_total",
    "nps_score",
    "billing_issues_count",
    "country",
    "industry",
    "company_size",
    "is_churned",
    "churned_at",
]

_SERVICES = [
    "PhoneService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
]  # 7 services; MultipleLines counts as an 8th bonus


def _map_plan(contract: str) -> str:
    return {
        "Month-to-month": "starter",
        "One year": "growth",
        "Two year": "enterprise",
    }.get(contract, "starter")


def _contract_months(contract: str) -> str:
    return {
        "Month-to-month": "",
        "One year": "12",
        "Two year": "24",
    }.get(contract, "")


def _logins(internet: str, churned: bool) -> int:
    base = {
        "Fiber optic": (15, 4),
        "DSL": (8, 2),
        "No": (3, 1),
    }.get(internet, (5, 2))
    return base[1] if churned else base[0]


def _service_count(row: pd.Series) -> int:
    count = sum(1 for s in _SERVICES if row.get(s) == "Yes")
    if row.get("MultipleLines") == "Yes":
        count += 1
    return count


def _feature_usage(row: pd.Series) -> str:
    score = round((_service_count(row) / 8) * 100, 2)
    return str(score)


def _support_total(tenure_months: int, has_tech_support: bool) -> int:
    divisor = 24 if has_tech_support else 12
    return max(0, tenure_months // divisor)


def _billing_issues(payment_method: str, churned: bool) -> int:
    if "Electronic check" in payment_method:
        return 2 if churned else 1
    if "Mailed check" in payment_method:
        return 1 if churned else 0
    return 0  # automatic payments (bank transfer / credit card)


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Map one Telco DataFrame to a ChurnIQ-ready DataFrame."""
    rows = []
    for _, r in df.iterrows():
        tenure = int(r["tenure"])
        churned = r["Churn"].strip().lower() == "yes"
        contract = r["Contract"].strip()
        internet = r["InternetService"].strip()
        payment = r["PaymentMethod"].strip()
        has_ts = r.get("TechSupport", "").strip() == "Yes"

        signup = _REF_DATE - timedelta(days=tenure * 30)

        months_str = _contract_months(contract)
        if months_str:
            months = int(months_str)
            if churned:
                # Churned: original contract term end (may be in the past — that's fine,
                # days_to_contract_end will be negative, which is a valid churn signal).
                end_date = signup + timedelta(days=months * 30)
            else:
                # Active: roll forward to the end of the CURRENT renewal period so
                # days_to_contract_end is always future-facing (the next real renewal date).
                periods_elapsed = tenure // months  # complete periods since signup
                current_period_start = signup + timedelta(days=periods_elapsed * months * 30)
                end_date = current_period_start + timedelta(days=months * 30)
            contract_end = end_date.isoformat()
        else:
            contract_end = ""

        last_activity = (
            (_REF_DATE - timedelta(days=30)).isoformat()
            if churned
            else _REF_DATE.isoformat()
        )
        churned_at = _REF_DATE.isoformat() if churned else ""

        rows.append(
            {
                "external_id": r["customerID"],
                "name": f"Telco-{r['customerID']}",
                "email": "",
                "phone": "",
                "plan": _map_plan(contract),
                "monthly_revenue": str(round(float(r["monthly_revenue_clean"]), 2)),
                "contract_length_months": months_str,
                "signup_date": signup.isoformat(),
                "contract_end_date": contract_end,
                "last_activity_date": last_activity,
                "logins_last_30d": _logins(internet, churned),
                "feature_usage_score": _feature_usage(r),
                "support_tickets_open": 0,
                "support_tickets_total": _support_total(tenure, has_ts),
                "nps_score": "",
                "billing_issues_count": _billing_issues(payment, churned),
                "country": "US",
                "industry": "Telecommunications",
                "company_size": "",
                "is_churned": "true" if churned else "false",
                "churned_at": churned_at,
            }
        )

    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Telco CSV to ChurnIQ import format")
    parser.add_argument("--preview", action="store_true", help="Print 5 sample rows and exit")
    parser.add_argument("--input", default=str(_DEFAULT_INPUT), help="Path to Telco CSV")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT), help="Output CSV path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load + clean
    # ------------------------------------------------------------------
    print(f"Loading {input_path} …")
    df = pd.read_csv(input_path, dtype=str)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    # TotalCharges: some rows have blank string for tenure=0 customers.
    # Fill blanks with MonthlyCharges (best estimate for a brand-new subscriber).
    df["TotalCharges"] = df["TotalCharges"].str.strip()
    df["monthly_revenue_clean"] = pd.to_numeric(df["MonthlyCharges"], errors="coerce")
    df["total_charges_clean"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    blank_total = df["total_charges_clean"].isna().sum()
    df["total_charges_clean"] = df["total_charges_clean"].fillna(df["monthly_revenue_clean"])
    print(f"  TotalCharges: {blank_total} blank rows filled with MonthlyCharges")

    # ------------------------------------------------------------------
    # Convert
    # ------------------------------------------------------------------
    out = convert(df)

    if args.preview:
        print("\n=== 5-row sample (preview mode — no file written) ===\n")
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        pd.set_option("display.max_colwidth", 30)
        print(out.head(5).to_string(index=False))
        print(
            "\nMapping notes:\n"
            "  logins_last_30d    — proxy from InternetService tier (not from real login data)\n"
            "  feature_usage_score — proxy: active add-on services / 8 × 100\n"
            "  support_tickets_total — proxy: tenure÷12 or ÷24 depending on TechSupport\n"
            "  billing_issues_count — proxy: payment method risk (electronic check = higher)\n"
            "  nps_score          — left blank (null); model imputes median at scoring time\n"
            "  company_size       — left blank (null); B2C dataset, no firmographics\n"
        )
        return

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)

    print(f"\nOutput written: {output_path}")
    print(f"  Total rows:   {len(out)}")
    print(f"  Churned:      {(out['is_churned'] == 'true').sum()}")
    print(f"  Active:       {(out['is_churned'] == 'false').sum()}")
    print(f"  Churn rate:   {(out['is_churned'] == 'true').mean():.1%}")
    print(f"  Plans:        {out['plan'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
