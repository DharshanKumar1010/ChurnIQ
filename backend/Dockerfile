# Stage 1: build dependencies into an isolated venv
FROM python:3.11-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# Stage 2: lean runtime image
FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy the venv from the builder (no build tools in the final image)
COPY --from=builder /opt/venv /opt/venv

# App layout:
#   /app/backend/   → FastAPI source (WORKDIR, PYTHONPATH)
#   /app/models/    → joblib artifacts (expected by _ARTIFACT_ROOT = parents[4]/models)
WORKDIR /app/backend

COPY backend/ .
COPY models/ /app/models/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
