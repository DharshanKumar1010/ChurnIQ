import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.customer import Customer, PlanType
from app.models.prediction import ChurnPrediction
from app.models.user import User
from app.schemas.bulk_import import BulkImportResponse, RowErrorDetail
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.csv_ingestion import parse_csv

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_owned_customer(
    customer_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Customer:
    """Fetch a customer by id, enforcing ownership. Raises 404 if missing or not owned."""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.user_id == current_user.id,
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


# ---------------------------------------------------------------------------
# POST /bulk-import  (must be registered before /{customer_id})
# ---------------------------------------------------------------------------
@router.post("/bulk-import", response_model=BulkImportResponse)
async def bulk_import_customers(
    file: UploadFile = File(..., description="UTF-8 CSV with customer records"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkImportResponse:
    """Ingest a CSV of customers.  Invalid rows are skipped and reported; the
    batch is never aborted by a single bad row."""
    if file.content_type not in ("text/csv", "application/csv", "application/octet-stream", "text/plain"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload must be a CSV file",
        )

    content = await file.read()
    try:
        result = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if result.valid:
        db.add_all(
            Customer(**row.model_dump(), user_id=current_user.id)
            for row in result.valid
        )
        await db.flush()

    return BulkImportResponse(
        created=len(result.valid),
        skipped=len(result.errors),
        errors=[RowErrorDetail(row=e.row, error=e.error) for e in result.errors],
    )


# ---------------------------------------------------------------------------
# POST /
# ---------------------------------------------------------------------------
@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    """Create a new customer scoped to the authenticated user."""
    customer = Customer(**body.model_dump(), user_id=current_user.id)
    db.add(customer)
    await db.flush()
    await db.refresh(customer)
    return customer


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------
@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    plan: PlanType | None = Query(None, description="Filter by subscription plan"),
    is_churned: bool | None = Query(None, description="Filter by churn status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerListResponse:
    """List all customers belonging to the authenticated user, with optional filters."""
    base_filter = [Customer.user_id == current_user.id]
    if plan is not None:
        base_filter.append(Customer.plan == plan)
    if is_churned is not None:
        base_filter.append(Customer.is_churned == is_churned)

    total_result = await db.execute(
        select(func.count(Customer.id)).where(*base_filter)
    )
    total = total_result.scalar_one()

    rows_result = await db.execute(
        select(Customer).where(*base_filter).order_by(Customer.created_at.desc()).offset(skip).limit(limit)
    )
    items = list(rows_result.scalars().all())

    # Attach latest prediction data to each customer for display in the list
    if items:
        customer_ids = [c.id for c in items]
        pred_result = await db.execute(
            select(ChurnPrediction)
            .where(ChurnPrediction.customer_id.in_(customer_ids))
            .order_by(ChurnPrediction.predicted_at.desc())
        )
        latest: dict[uuid.UUID, ChurnPrediction] = {}
        for p in pred_result.scalars().all():
            if p.customer_id not in latest:
                latest[p.customer_id] = p
        for c in items:
            pred = latest.get(c.id)
            c.latest_risk_tier = pred.risk_tier if pred else None  # type: ignore[attr-defined]
            c.latest_churn_probability = pred.churn_probability if pred else None  # type: ignore[attr-defined]

    return CustomerListResponse(items=items, total=total, skip=skip, limit=limit)


# ---------------------------------------------------------------------------
# GET /{customer_id}
# ---------------------------------------------------------------------------
@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    """Fetch a single customer by id."""
    return await _get_owned_customer(customer_id, current_user, db)


# ---------------------------------------------------------------------------
# PUT /{customer_id}
# ---------------------------------------------------------------------------
@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    """Update a customer. Only fields present in the request body are written."""
    customer = await _get_owned_customer(customer_id, current_user, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    await db.flush()
    await db.refresh(customer)
    return customer


# ---------------------------------------------------------------------------
# DELETE /{customer_id}
# ---------------------------------------------------------------------------
@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Permanently delete a customer and all related predictions."""
    customer = await _get_owned_customer(customer_id, current_user, db)
    await db.delete(customer)
    await db.flush()
