"""
Monitoring, health-check, and usage reporting API endpoints.

Provides:
- GET /health              – quick liveness probe
- GET /health/detailed     – deep health check (DB, Redis, LLM providers)
- GET /metrics/usage       – LLM cost & document processing usage report
- GET /metrics/requests    – request-level performance metrics

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.services.cost_tracker import cost_tracker
from app.services.metrics_collector import metrics_collector

logger = logging.getLogger("rag_chatbot.monitoring")

router = APIRouter(tags=["monitoring"])


# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Quick liveness probe – always returns 200 if the process is up."""
    return {"status": "healthy"}


@router.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """Deep health check that probes DB, Redis, and LLM provider status."""
    checks: Dict[str, Any] = {}

    # --- Database ---
    try:
        from app.db.base import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        checks["database"] = {"status": "unhealthy", "error": str(exc)}

    # --- Redis ---
    try:
        from app.services.redis_client import RedisClient

        rc = RedisClient()
        await rc.connect()
        connected = await rc.is_connected()
        await rc.disconnect()
        checks["redis"] = {"status": "healthy" if connected else "unhealthy"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        checks["redis"] = {"status": "unhealthy", "error": str(exc)}

    # --- LLM providers (lightweight – just report cached status) ---
    try:
        from app.api.chat import get_rag_pipeline

        pipeline = await get_rag_pipeline()
        if pipeline and pipeline.llm_manager:
            provider_status = pipeline.llm_manager.get_provider_status()
            checks["llm_providers"] = {
                name: {"enabled": info.get("enabled"), "healthy": info.get("healthy")}
                for name, info in provider_status.items()
            }
        else:
            checks["llm_providers"] = {"status": "not_configured"}
    except Exception as exc:
        logger.warning("LLM provider health check failed: %s", exc)
        checks["llm_providers"] = {"status": "unknown", "error": str(exc)}

    overall = "healthy" if all(
        c.get("status") == "healthy" for c in checks.values() if isinstance(c, dict) and "status" in c
    ) else "degraded"

    return {
        "status": overall,
        "uptime_seconds": round(metrics_collector.get_uptime_seconds(), 1),
        "checks": checks,
    }


# ------------------------------------------------------------------
# Usage / cost reporting
# ------------------------------------------------------------------


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-format date string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/metrics/usage")
async def usage_report(
    start_date: Optional[str] = Query(None, description="ISO start date, e.g. 2025-01-01"),
    end_date: Optional[str] = Query(None, description="ISO end date, e.g. 2025-01-31"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days (used when start_date is omitted)"),
) -> Dict[str, Any]:
    """
    Combined usage report: LLM costs, document processing stats, and cost alerts.

    Supports date-range filtering via start_date/end_date or a rolling window via days.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is None:
        start = datetime.utcnow() - timedelta(days=days)
    if end is None:
        end = datetime.utcnow()

    llm_summary = await cost_tracker.get_usage_summary(start, end)
    cost_trends = await cost_tracker.get_cost_trends(days=days)
    alerts = await cost_tracker.check_cost_alerts()
    provider_efficiency = await cost_tracker.get_provider_efficiency()
    doc_stats = await metrics_collector.get_document_processing_stats(start, end)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "llm_usage": {
            "total_requests": llm_summary.total_requests,
            "total_tokens": llm_summary.total_tokens,
            "total_cost": round(llm_summary.total_cost, 6),
            "provider_breakdown": llm_summary.provider_breakdown,
            "model_breakdown": llm_summary.model_breakdown,
        },
        "cost_trends": cost_trends,
        "provider_efficiency": provider_efficiency,
        "document_processing": doc_stats,
        "alerts": alerts,
    }


@router.get("/metrics/requests")
async def request_metrics(
    start_date: Optional[str] = Query(None, description="ISO start date"),
    end_date: Optional[str] = Query(None, description="ISO end date"),
    days: int = Query(1, ge=1, le=365, description="Lookback window in days"),
) -> Dict[str, Any]:
    """Request-level performance metrics: response times, error rates, endpoint breakdown."""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is None:
        start = datetime.utcnow() - timedelta(days=days)
    if end is None:
        end = datetime.utcnow()

    stats = await metrics_collector.get_request_stats(start, end)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        **stats,
    }
