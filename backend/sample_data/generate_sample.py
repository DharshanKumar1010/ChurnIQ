"""Generate sample_data/customers_realistic.csv — 800 rows with realistic churn.

Design:
  - Each customer is drawn from one of two overlapping segments:
      Churned  (22% base rate): low logins, low feature usage, high support load,
                                low NPS, stale activity, billing friction.
      Active   (78% base rate): opposite profile.
  - Overlap is intentional — distributions share ~15-25% of their range,
    making the task learnable but not trivially separable (target AUC ~0.83-0.90).
  - Firmographics (country, industry, company_size) carry NO signal — noise.

Run from backend/:
    python sample_data/generate_sample.py
"""

import csv
import statistics
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from faker import Faker

RNG = np.random.default_rng(42)
fake = Faker()
Faker.seed(42)

TODAY = date(2026, 6, 12)
N_CUSTOMERS = 800
CHURN_RATE = 0.22          # base churn probability

PLANS = ["free", "starter", "growth", "enterprise"]
PLAN_REVENUE = {
    "free": (0.0, 0.0),
    "starter": (49.0, 199.0),
    "growth": (299.0, 999.0),
    "enterprise": (1500.0, 5000.0),
}
INDUSTRIES = [
    "SaaS", "FinTech", "HealthTech", "E-commerce", "EdTech",
    "MarTech", "HRTech", "LegalTech", "InsurTech", "PropTech",
]
COMPANY_SIZES = ["small", "mid", "large"]
COUNTRIES = ["US", "GB", "CA", "AU", "DE", "FR", "IN", "SG", "NL", "BR"]

HEADERS = [
    "external_id", "name", "email", "phone",
    "plan", "monthly_revenue", "contract_length_months", "signup_date",
    "contract_end_date", "last_activity_date", "logins_last_30d",
    "feature_usage_score", "support_tickets_open", "support_tickets_total",
    "nps_score", "billing_issues_count", "country", "industry",
    "company_size", "is_churned", "churned_at",
]


def _rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=int(RNG.integers(0, delta + 1)))


def make_row(i: int) -> dict:
    is_churned: bool = RNG.random() < CHURN_RATE

    # ── Per-segment feature distributions ─────────────────────────────────────
    # Distributions are intentionally overlapping: ~20% of each segment's
    # feature values fall into the other segment's core range, ensuring the
    # classifier has to deal with ambiguous cases.

    # 15% of churned look engaged (sudden / surprise churners).
    # 10% of active look stressed (at-risk but haven't left yet).
    # These "confused" rows are the hard cases that prevent AUC → 1.0.
    confused = (is_churned  and RNG.random() < 0.15) or \
               (not is_churned and RNG.random() < 0.10)
    use_churned_profile = is_churned != confused      # XOR: flips profile for confused rows

    if use_churned_profile:
        # Low-engagement, high-friction profile
        logins            = max(0, int(RNG.poisson(4)))
        feature_usage     = float(np.clip(RNG.normal(27.0, 16.0), 0.0, 100.0))
        tickets_total     = int(RNG.poisson(6))
        billing_issues    = int(RNG.poisson(1.8))
        nps_raw           = int(np.clip(RNG.normal(5.0, 28.0), -100, 100))
        recency_days      = int(np.clip(RNG.gamma(2.5, 32.0), 10, 400))
        plan_weights      = np.array([0.28, 0.48, 0.18, 0.06])
    else:
        # Engaged, healthy profile
        logins            = max(0, int(RNG.poisson(21)))
        feature_usage     = float(np.clip(RNG.normal(71.0, 14.0), 0.0, 100.0))
        tickets_total     = int(RNG.poisson(1))
        billing_issues    = int(RNG.poisson(0.12))
        nps_raw           = int(np.clip(RNG.normal(60.0, 20.0), -100, 100))
        recency_days      = int(np.clip(RNG.gamma(1.5, 5.0), 0, 60))
        plan_weights      = np.array([0.08, 0.32, 0.38, 0.22])

    # ── Derived / correlated fields ────────────────────────────────────────────
    tickets_open = min(tickets_total, int(RNG.poisson(max(0.1, tickets_total * 0.45))))
    nps: int | None = None if RNG.random() < 0.08 else nps_raw

    # Plan (segment-weighted; still has noise — enterprise can churn)
    plan_weights = plan_weights / plan_weights.sum()
    plan: str = str(RNG.choice(PLANS, p=plan_weights))
    lo, hi = PLAN_REVENUE[plan]
    revenue = round(float(RNG.uniform(lo, hi)), 2) if hi > 0 else 0.0

    # Tenure
    signup = _rand_date(date(2022, 1, 1), date(2025, 3, 1))

    # Contract: growth/enterprise more likely; churned less likely to have one
    contract_p = 0.65 if plan in ("growth", "enterprise") else 0.0
    if is_churned:
        contract_p *= 0.45
    has_contract = RNG.random() < contract_p
    contract_months: int | None = None
    contract_end: date | None = None
    if has_contract:
        contract_months = int(RNG.choice([12, 24]))
        yrs, mo = divmod(signup.month + contract_months - 1, 12)
        contract_end = date(signup.year + yrs + mo // 12, mo % 12 + 1, 1)

    # Last activity derived from recency_days
    activity_date = max(signup, TODAY - timedelta(days=recency_days))

    churned_at: date | None = None
    if is_churned:
        earliest = signup + timedelta(days=30)
        latest   = min(TODAY, activity_date + timedelta(days=int(RNG.integers(1, 30))))
        if latest > earliest:
            churned_at = _rand_date(earliest, latest)
        else:
            churned_at = latest

    return {
        "external_id": f"EXT-{2000 + i}",
        "name": fake.company(),
        "email": fake.company_email(),
        "phone": fake.phone_number()[:20],
        "plan": plan,
        "monthly_revenue": f"{revenue:.2f}",
        "contract_length_months": contract_months if contract_months else "",
        "signup_date": signup.isoformat(),
        "contract_end_date": contract_end.isoformat() if contract_end else "",
        "last_activity_date": activity_date.isoformat(),
        "logins_last_30d": logins,
        "feature_usage_score": round(feature_usage, 1),
        "support_tickets_open": tickets_open,
        "support_tickets_total": tickets_total,
        "nps_score": nps if nps is not None else "",
        "billing_issues_count": billing_issues,
        "country": str(RNG.choice(COUNTRIES)),
        "industry": str(RNG.choice(INDUSTRIES)),
        "company_size": str(RNG.choice(COMPANY_SIZES)),
        "is_churned": "true" if is_churned else "false",
        "churned_at": churned_at.isoformat() if churned_at else "",
    }


def main() -> None:
    rows = [make_row(i) for i in range(N_CUSTOMERS)]

    churned_rows = [r for r in rows if r["is_churned"] == "true"]
    active_rows  = [r for r in rows if r["is_churned"] == "false"]
    n_c, n_a = len(churned_rows), len(active_rows)
    print(f"\n{N_CUSTOMERS} rows total: {n_c} churned ({n_c/N_CUSTOMERS:.1%})  "
          f"{n_a} active ({n_a/N_CUSTOMERS:.1%})")

    print("\nFeature separation (signal check):")
    print(f"  {'Feature':<25} {'Churned':>10} {'Active':>10} {'Cohen d':>10}")
    print(f"  {'-'*55}")
    for field in ["logins_last_30d", "feature_usage_score",
                  "support_tickets_total", "billing_issues_count", "nps_score"]:
        c_vals = [float(r[field]) for r in churned_rows if str(r[field]) != ""]
        a_vals = [float(r[field]) for r in active_rows  if str(r[field]) != ""]
        c_mean = statistics.mean(c_vals)
        a_mean = statistics.mean(a_vals)
        pooled_sd = (statistics.variance(c_vals) * len(c_vals) +
                     statistics.variance(a_vals) * len(a_vals)) ** 0.5 / (len(c_vals) + len(a_vals)) ** 0.5
        cohen_d = abs(c_mean - a_mean) / max(pooled_sd, 0.001)
        print(f"  {field:<25} {c_mean:>10.2f} {a_mean:>10.2f} {cohen_d:>10.2f}")

    out = Path(__file__).parent / "customers_realistic.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved -> {out}\n")


if __name__ == "__main__":
    main()
