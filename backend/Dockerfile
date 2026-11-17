# Multi-stage build for the FastAPI backend.
#
# The builder stage builds everything - applies every feature's migrations,
# generates the synthetic group, reconciles the invoices, runs the acceptance
# checks - from code and a seed, then checks every table against the digests
# pinned in infra-azure/build.sha256. A mismatch, or a failing acceptance check,
# fails the image build: an image that cannot reproduce the pinned output is
# never pushed.
#
# So the runtime needs no blob store and no database server, and a cold start
# is the time it takes uvicorn to start.

# ---------- builder ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd backend && uv sync --frozen --no-install-project --no-dev

COPY backend/src ./backend/src
COPY scripts ./scripts
COPY infra-azure/build.sha256 ./infra-azure/build.sha256
# The last graded eval, shown on the Data agent page.
COPY evals ./evals

ARG GIT_SHA=""
ENV GIT_SHA=$GIT_SHA
RUN cd backend && .venv/bin/python ../scripts/build_platform.py

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ARG GIT_SHA=""
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    GIT_SHA=$GIT_SHA

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
# WORKDIR creates /app as root before the USER switch; the app writes its
# working copy of the database under data/.
RUN chown app:app /app /app/data

USER app
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
