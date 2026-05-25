"""FastAPI serving endpoint for multi-agent code review.

Fixes applied:
  A2-004 — API key authentication + in-memory rate limiting
  A5-003 — opaque error responses; full exception logged server-side
  A5-004 — double-checked locking on graph singleton
  A5-006 — SecretStr consumed via .get_secret_value()
  A3-004 — Prometheus metrics via prometheus-fastapi-instrumentator
"""

import asyncio
import hashlib
import hmac
import os
import time
from collections import defaultdict
from threading import Lock

import structlog
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from coderev.agents.graph import compile_graph
from coderev.config import Settings

logger = structlog.get_logger()
_settings = Settings()

app = FastAPI(
    title="CodeRev Agents",
    description="Multi-agent code review powered by fine-tuned CodeLlama + LangGraph",
    version="0.3.2",
)

# ── TLS / host enforcement in production ────────────────────────────────────
if _settings.env == "production":
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_settings.allowed_hosts.split(","),
    )

# ── Prometheus metrics ───────────────────────────────────────────────────────
_trust_findings_counter = Counter(
    "coderev_trust_findings_total",
    "Number of prompt-injection markers detected in submitted diffs",
    ["finding_type"],
)
_diff_size_histogram = Histogram(
    "coderev_diff_size_bytes",
    "Size of submitted diffs in bytes",
    buckets=[500, 1000, 5000, 10000, 25000, 50000],
)
_agents_invoked_counter = Counter(
    "coderev_agents_invoked_total",
    "Number of times each agent was invoked",
    ["agent_name"],
)

Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app)

# ── Graph singleton with async double-checked locking (fix A5-004) ──────────
_graph = None
_graph_lock = asyncio.Lock()


async def get_graph():
    global _graph
    if _graph is None:
        async with _graph_lock:
            if _graph is None:
                _graph = compile_graph()
    return _graph


# ── Authentication (fix A2-004 / CWE-306) ───────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def _verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    """Constant-time API key comparison to prevent timing attacks."""
    expected = _settings.api_secret_key.get_secret_value()
    if not expected:
        logger.error("api_secret_key_not_configured")
        raise HTTPException(status_code=500, detail="Server misconfiguration.")
    provided_hash = hashlib.sha256(api_key.encode()).digest()
    expected_hash = hashlib.sha256(expected.encode()).digest()
    if not hmac.compare_digest(provided_hash, expected_hash):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return api_key


# ── In-memory rate limiter (fix A2-004) — replace with Redis in production ──
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()
_RATE_LIMIT = 20    # requests per window
_RATE_WINDOW = 60.0  # seconds


def _check_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_lock:
        timestamps = _rate_store[client_ip]
        _rate_store[client_ip] = [t for t in timestamps if now - t < _RATE_WINDOW]
        if len(_rate_store[client_ip]) >= _RATE_LIMIT:
            logger.warning("rate_limit_exceeded", client_ip=client_ip)
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        _rate_store[client_ip].append(now)


# ── Request / response models ────────────────────────────────────────────────
class ReviewRequest(BaseModel):
    diff: str = Field(..., min_length=5, max_length=50000)
    language: str = Field(default="", max_length=50)


class ReviewResponse(BaseModel):
    summary: str
    security_review: str
    style_review: str
    complexity_review: str
    agents_invoked: list[str]
    diff_sha256: str = ""
    diff_truncated: bool = False
    trust_findings: list[str] = Field(default_factory=list)


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.post(
    "/v1/review",
    response_model=ReviewResponse,
    dependencies=[Security(_verify_api_key)],
)
async def review_code(request: ReviewRequest, http_request: Request) -> ReviewResponse:
    """Submit a code diff for multi-agent review."""
    _check_rate_limit(http_request)

    diff_bytes = len(request.diff.encode("utf-8"))
    _diff_size_histogram.observe(diff_bytes)

    graph = await get_graph()

    initial_state = {
        "diff": request.diff,
        "language": request.language,
        "security_review": "",
        "style_review": "",
        "complexity_review": "",
        "run_security": True,
        "run_complexity": True,
        "diff_sha256": "",
        "diff_truncated": False,
        "trust_findings": [],
        "summary": "",
    }

    try:
        result = await graph.ainvoke(initial_state)
    except Exception:
        # Log full exception server-side; return opaque message to caller (fix A5-003).
        logger.exception("review_invocation_failed")
        raise HTTPException(status_code=500, detail="Review failed. Check server logs.")

    # Record metrics
    for finding in result.get("trust_findings", []):
        finding_type = finding.split(":")[0] if ":" in finding else finding
        _trust_findings_counter.labels(finding_type=finding_type).inc()

    agents: list[str] = ["style_agent"]
    if result.get("run_security"):
        agents.append("security_agent")
        _agents_invoked_counter.labels(agent_name="security_agent").inc()
    if result.get("run_complexity"):
        agents.append("complexity_agent")
        _agents_invoked_counter.labels(agent_name="complexity_agent").inc()
    _agents_invoked_counter.labels(agent_name="style_agent").inc()

    # Drift monitoring
    try:
        from coderev.monitoring.drift import monitor as drift_monitor
        drift_monitor.record(diff_bytes, bool(result.get("trust_findings")))
    except Exception:
        logger.warning("drift_monitor_error", exc_info=True)

    logger.info(
        "review_complete",
        sha256=result.get("diff_sha256", ""),
        agents=agents,
        trust_findings=result.get("trust_findings", []),
    )

    return ReviewResponse(
        summary=result.get("summary", ""),
        security_review=result.get("security_review", ""),
        style_review=result.get("style_review", ""),
        complexity_review=result.get("complexity_review", ""),
        agents_invoked=agents,
        diff_sha256=result.get("diff_sha256", ""),
        diff_truncated=result.get("diff_truncated", False),
        trust_findings=result.get("trust_findings", []),
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.3.2"}
