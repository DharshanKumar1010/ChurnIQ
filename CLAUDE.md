# ChurnIQ — Project Memory

## What this is
Multi-tenant SaaS churn prediction platform — FastAPI backend, React frontend,
XGBoost + SHAP ML pipeline, RAG chatbot (Groq/Llama-3.3-70b), deployed via
Docker/Render/Vercel.

## Project location
- Root: `C:\Users\LENOVO\OneDrive\Pictures\Documents\ChurnIQ\`
- `backend/` — FastAPI + PostgreSQL/Supabase, Python 3.11.9 venv at `backend\.venv`
- `frontend/` — React 18 + TS + Vite + Tailwind

## Environment notes
- Supabase Postgres (session pooler, port 5432)
- Groq API key stored in `.env` as `OPENAI_API_KEY` (OpenAI-compatible endpoint)
- Required backend env vars: `DATABASE_URL`, `SECRET_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- Required frontend env var: `VITE_API_URL`

## ✅ Completed (Weeks 1-6, mostly)

### Backend
- JWT auth: register, login, refresh (rotating, HTTPOnly cookie), `/me` — tested
- Customer CRUD: 5 endpoints, multi-tenant scoped to `current_user.id`
- CSV bulk import: `/customers/bulk-import` (validates rows, returns created/skipped/errors)
- ML pipeline: 16-feature engineering (RFM, engagement, tenure), XGBoost training, `ModelVersion` registry
- Active model: `v20260612-xgb-v3` — AUC-ROC 0.9179 (Optuna-tuned, 25 trials)
- Predictions router: `/predictions/model-versions`, `/predictions/run`, `/predictions/{customer_id}`
- SHAP explainability: `shap_values` + `top_factors` stored per prediction
- Analytics: `compute_snapshot()`, `/analytics/snapshot`, `/analytics/snapshots`, `/analytics/summary` — verified on 847-customer dataset
- RAG chatbot: `/chat` endpoint (Groq, grounded responses)
- Optimization: `GET /customers` attaches `latest_risk_tier` + `latest_churn_probability` (avoids N+1)

### Test data
847 synthetic customers, ~21.5% churn rate, realistic correlations

### Frontend
- Auth: Login, Register, AuthContext, useAuth, ProtectedRoute, token refresh interceptor
- `Layout.tsx` — sidebar nav
- `Dashboard.tsx` — 4 stat cards + recharts donut
- `Customers.tsx` — paginated table, risk tier badges, click → detail
- `CustomerDetail.tsx` — customer fields + SHAP horizontal bar chart
- `Chat.tsx` — RAG chat UI
- All wired in `App.tsx`, build succeeds

## ✅ Completed: Week 6, Day 4-6 — Dockerize + CI/CD

### Docker / deploy infra
- `backend/Dockerfile` — multi-stage (builder venv + slim runtime), copies `backend/` + `models/`
- `frontend/Dockerfile` — multi-stage (node build + nginx:alpine), nginx.conf with SPA fallback
- `frontend/nginx.conf` — `try_files $uri /index.html`, 1y asset cache, gzip
- `docker-compose.yml` — local full-stack: backend :8000, frontend nginx :5173
- `.github/workflows/ci.yml` — backend lint+import check+Docker build; frontend tsc+build+Docker build
- `.gitignore` at project root
- `backend/.env.example` + `frontend/.env.example` — all vars documented

### Code changes for portability
- `frontend/src/api/client.ts` — baseURL uses `VITE_API_URL` env var (falls back to localhost:8000)
- `backend/app/core/config.py` — added `CORS_EXTRA_ORIGINS` (comma-separated) merged into `ALLOWED_ORIGINS`
- `backend/app/routers/predictions.py` — fallback model artifact path resolution via `_ARTIFACT_ROOT/<version>/pipeline.joblib` when DB-stored path doesn't exist (handles Windows→Linux path mismatch)

### Key layout facts for Docker
- Models live at project root `models/` — Docker copies them to `/app/models/` in the image
- `_ARTIFACT_ROOT = Path(__file__).parents[4] / "models"` resolves to `/app/models/` ✓
- Backend runs from `WORKDIR /app/backend`, venv at `/opt/venv`

## ⏳ Remaining: Deploy to Render + Vercel

- Push repo to GitHub (needed for Render + Vercel autodeploy)
- Backend → Render: set all env vars from `backend/.env.example`, build command `docker build -f backend/Dockerfile`, start command already in Dockerfile CMD
- Frontend → Vercel: root dir `frontend/`, build cmd `npm run build`, output `dist`, set `VITE_API_URL=<render-backend-url>`
- After both deploy: set `CORS_EXTRA_ORIGINS=<vercel-url>` on Render backend and redeploy

## Conventions / notes for Claude Code
- Don't break existing tested auth/CRUD/ML routes
- Keep `.env` out of git; use `.env.example` for documented vars
- Prefer multi-stage Docker builds for smaller images
- This is the final phase — goal is a live, shareable deployed product