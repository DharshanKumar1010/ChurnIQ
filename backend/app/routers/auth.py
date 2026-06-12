import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_COOKIE_NAME = "refresh_token"
_COOKIE_PATH = "/api/v1/auth"
_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Write the refresh token into a secure HTTPOnly cookie."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Expire the refresh cookie immediately (used on logout / token reuse)."""
    response.delete_cookie(key=_COOKIE_NAME, path=_COOKIE_PATH)


async def _store_refresh_token(
    db: AsyncSession, user_id: object, raw_token: str
) -> None:
    """Persist a hashed refresh token record to the database."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------
@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Create a new user account and return tokens."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()   # populate user.id before referencing it

    raw_refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, raw_refresh)

    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=create_access_token(user.id))


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password and return tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Deliberate generic message — prevents email enumeration.
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    raw_refresh = create_refresh_token(user.id)
    await _store_refresh_token(db, user.id, raw_refresh)

    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=create_access_token(user.id))


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate the refresh token and issue a new access token."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    if refresh_token is None:
        raise credentials_error

    payload = decode_token(refresh_token)   # raises 401 on bad signature / expiry

    if payload.get("type") != "refresh":
        raise credentials_error

    token_hash = hash_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None or stored.revoked:
        # Token reuse detected — clear cookie and fail hard.
        _clear_refresh_cookie(response)
        raise credentials_error

    if stored.expires_at < datetime.now(timezone.utc):
        _clear_refresh_cookie(response)
        raise credentials_error

    # Revoke the consumed token (rotation: one use only).
    stored.revoked = True
    await db.flush()

    new_raw_refresh = create_refresh_token(stored.user_id)
    await _store_refresh_token(db, stored.user_id, new_raw_refresh)

    _set_refresh_cookie(response, new_raw_refresh)
    return TokenResponse(access_token=create_access_token(stored.user_id))


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user
