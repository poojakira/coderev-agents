# syntax=docker/dockerfile:1.7
# Fix A3-ABSENT-001: Dockerfile with pinned digest, multi-stage build, non-root user.
#
# Base image digest verified from Docker Hub python:3.11.9-slim on 2026-05-25.
# To re-verify: docker pull python:3.11.9-slim && docker inspect python:3.11.9-slim | jq '.[0].RepoDigests'
# Update the digest below after any base image update.

# ── Stage 1: build wheel ──────────────────────────────────────────────────
FROM python:3.11.9-slim@sha256:491392e89b47a9c37bf02e61e4b91c6ef0f3695f24519f90ced4e2fd1e8cfcd8 AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

# Build wheel in isolation — no test/train/quantize deps in final image
RUN pip install --no-cache-dir "build==1.2.2" && \
    python -m build --wheel --outdir /dist

# ── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.11.9-slim@sha256:491392e89b47a9c37bf02e61e4b91c6ef0f3695f24519f90ced4e2fd1e8cfcd8 AS runtime

# Non-root user — Fix A3-ABSENT-001 / EXEC-A3 Step 2
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy only the wheel from builder stage — source code not present in runtime image
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# No secrets in ENV or ARG layers.
# CODEREV_LLM_API_KEY and CODEREV_API_SECRET_KEY must be injected at runtime
# via orchestrator environment variables or K8s Secrets — never baked into image.

USER appuser

EXPOSE 8000

# Health check using stdlib only — no curl dependency in runtime image
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8000/health', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

ENTRYPOINT ["uvicorn", "coderev.api.main:app", \
            "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
