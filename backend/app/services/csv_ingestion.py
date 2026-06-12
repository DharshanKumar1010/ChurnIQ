import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.models.customer import PlanType
from app.schemas.customer import CustomerCreate

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_PLAN_MAP: dict[str, PlanType] = {p.value.lower(): p for p in PlanType}
_BOOL_TRUE = {"true", "1", "yes", "y"}
_BOOL_FALSE = {"false", "0", "no", "n", ""}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class RowError:
    row: int
    error: str
    raw: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    valid: list[CustomerCreate]
    errors: list[RowError]


# ---------------------------------------------------------------------------
# Field coercions
# ---------------------------------------------------------------------------
def _parse_date(value: str) -> date:
    """Accept YYYY-MM-DD only; raise ValueError with a clear message on failure."""
    v = value.strip()
    if not v:
        raise ValueError("date value is empty")
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"invalid date '{v}'; expected YYYY-MM-DD")


def _parse_decimal(value: str, default: str = "0") -> Decimal:
    v = value.strip().lstrip("$£€")  # strip common currency prefixes
    try:
        return Decimal(v) if v else Decimal(default)
    except InvalidOperation:
        raise ValueError(f"invalid number '{value}'")


def _parse_int(value: str, default: int = 0) -> int:
    v = value.strip()
    try:
        return int(v) if v else default
    except ValueError:
        raise ValueError(f"invalid integer '{value}'")


def _parse_bool(value: str, default: bool = False) -> bool:
    v = value.strip().lower()
    if v in _BOOL_TRUE:
        return True
    if v in _BOOL_FALSE:
        return False
    raise ValueError(f"invalid boolean '{value}'; use true/false/1/0/yes/no")


def _parse_plan(value: str) -> PlanType:
    v = value.strip().lower()
    if not v:
        return PlanType.starter
    if v not in _PLAN_MAP:
        valid = ", ".join(_PLAN_MAP)
        raise ValueError(f"invalid plan '{value}'; valid values: {valid}")
    return _PLAN_MAP[v]


# ---------------------------------------------------------------------------
# Row → CustomerCreate
# ---------------------------------------------------------------------------
def _row_to_customer_create(row: dict[str, str]) -> CustomerCreate:
    """Convert one DictReader row into a validated CustomerCreate.

    Raises ValueError with a descriptive message on any field problem.
    """
    def g(key: str, default: str = "") -> str:
        return (row.get(key) or default).strip()

    # Required fields
    name = g("name")
    if not name:
        raise ValueError("'name' is required")
    signup_raw = g("signup_date")
    if not signup_raw:
        raise ValueError("'signup_date' is required")
    signup_date = _parse_date(signup_raw)

    # Optional dates
    contract_end_date = _parse_date(g("contract_end_date")) if g("contract_end_date") else None
    last_activity_date = _parse_date(g("last_activity_date")) if g("last_activity_date") else None
    churned_at = _parse_date(g("churned_at")) if g("churned_at") else None

    # Optional numerics
    nps_raw = g("nps_score")
    nps_score = _parse_int(nps_raw) if nps_raw else None

    feat_raw = g("feature_usage_score")
    feature_usage_score = _parse_decimal(feat_raw) if feat_raw else None

    contract_raw = g("contract_length_months")
    contract_length_months = _parse_int(contract_raw) if contract_raw else None

    country = g("country").upper() if g("country") else None

    return CustomerCreate(
        name=name,
        signup_date=signup_date,
        external_id=g("external_id") or None,
        email=g("email") or None,
        phone=g("phone") or None,
        plan=_parse_plan(g("plan")),
        monthly_revenue=_parse_decimal(g("monthly_revenue")),
        contract_length_months=contract_length_months,
        contract_end_date=contract_end_date,
        last_activity_date=last_activity_date,
        logins_last_30d=_parse_int(g("logins_last_30d")),
        feature_usage_score=feature_usage_score,
        support_tickets_open=_parse_int(g("support_tickets_open")),
        support_tickets_total=_parse_int(g("support_tickets_total")),
        nps_score=nps_score,
        billing_issues_count=_parse_int(g("billing_issues_count")),
        country=country,
        industry=g("industry") or None,
        company_size=g("company_size") or None,
        is_churned=_parse_bool(g("is_churned")),
        churned_at=churned_at,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_csv(content: bytes) -> ParseResult:
    """Parse CSV bytes into a ParseResult with valid rows and per-row errors.

    Tries UTF-8-sig (BOM), UTF-8, then latin-1 for encoding.
    Raises ValueError only for file-level problems (too large, empty, bad encoding).
    Row-level problems are collected in ParseResult.errors instead.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File exceeds the {MAX_UPLOAD_BYTES // 1_048_576} MB size limit"
        )

    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ValueError("Could not decode the file — upload a UTF-8 encoded CSV")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file is empty or has no header row")

    valid: list[CustomerCreate] = []
    errors: list[RowError] = []

    for line_num, row in enumerate(reader, start=2):  # row 1 is the header
        if not any(v.strip() for v in row.values()):
            continue  # skip blank lines
        try:
            customer = _row_to_customer_create(row)
            valid.append(customer)
        except Exception as exc:
            errors.append(RowError(row=line_num, error=str(exc), raw=dict(row)))
            logger.debug("CSV line %d skipped: %s", line_num, exc)

    return ParseResult(valid=valid, errors=errors)
