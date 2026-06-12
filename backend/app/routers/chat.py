"""Chat router — RAG-powered churn analytics assistant."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag import ask_llm, build_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Answer a churn-related question grounded in the user's live data."""
    context = await build_context(db, current_user)
    reply = await ask_llm(context, request.message)
    return ChatResponse(reply=reply)
