"""
Metrics collection service for tracking response times, error rates, and system health.

Provides in-memory metrics aggregation for monitoring endpoints (Requirements 8.1-8.4).
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("rag_chatbot.metrics")


@dataclass
class RequestMetric:
    """Single request metric record."""
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None


@dataclass
class DocumentProcessingMetric:
    """Metric for document processing operations."""
    document_id: str
    filename: str
    file_size: int
    processing_time_ms: float
    chunk_count: int
    success: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None


class MetricsCollector:
    """Collects and aggregates application metrics."""

    def __init__(self, max_records: int = 10_000) -> None:
        self._request_metrics: List[RequestMetric] = []
        self._doc_metrics: List[DocumentProcessingMetric] = []
        self._max_records = max_records
        self._lock = asyncio.Lock()
        self._start_time = datetime.utcnow()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    async def record_request(self, metric: RequestMetric) -> None:
        async with self._lock:
            self._request_metrics.append(metric)
            if len(self._request_metrics) > self._max_records:
                self._request_metrics = self._request_metrics[-self._max_records:]

    async def record_document_processing(self, metric: DocumentProcessingMetric) -> None:
        async with self._lock:
            self._doc_metrics.append(metric)
            if len(self._doc_metrics) > self._max_records:
                self._doc_metrics = self._doc_metrics[-self._max_records:]

    # ------------------------------------------------------------------
    # Request metrics queries
    # ------------------------------------------------------------------

    async def get_request_stats(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate request statistics for a time window."""
        records = self._filter_by_time(self._request_metrics, start, end)
        if not records:
            return {
                "total_requests": 0,
                "avg_response_time_ms": 0.0,
                "error_count": 0,
                "error_rate": 0.0,
                "status_code_breakdown": {},
                "endpoint_breakdown": {},
            }

        total = len(records)
        error_count = sum(1 for r in records if r.status_code >= 400)
        avg_duration = sum(r.duration_ms for r in records) / total

        status_breakdown: Dict[str, int] = defaultdict(int)
        endpoint_breakdown: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_ms": 0.0, "errors": 0}
        )
        for r in records:
            status_breakdown[str(r.status_code)] += 1
            ep = endpoint_breakdown[r.endpoint]
            ep["count"] += 1
            ep["total_ms"] += r.duration_ms
            if r.status_code >= 400:
                ep["errors"] += 1

        for ep in endpoint_breakdown.values():
            ep["avg_ms"] = round(ep["total_ms"] / ep["count"], 2) if ep["count"] else 0
            del ep["total_ms"]

        return {
            "total_requests": total,
            "avg_response_time_ms": round(avg_duration, 2),
            "error_count": error_count,
            "error_rate": round(error_count / total, 4) if total else 0.0,
            "status_code_breakdown": dict(status_breakdown),
            "endpoint_breakdown": dict(endpoint_breakdown),
        }

    # ------------------------------------------------------------------
    # Document processing metrics queries
    # ------------------------------------------------------------------

    async def get_document_processing_stats(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate document processing statistics."""
        records = self._filter_by_time(self._doc_metrics, start, end)
        if not records:
            return {
                "total_processed": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_processing_time_ms": 0.0,
                "total_chunks_created": 0,
            }

        total = len(records)
        successes = sum(1 for r in records if r.success)
        failures = total - successes
        avg_time = sum(r.processing_time_ms for r in records) / total
        total_chunks = sum(r.chunk_count for r in records)

        return {
            "total_processed": total,
            "success_count": successes,
            "failure_count": failures,
            "success_rate": round(successes / total, 4) if total else 0.0,
            "avg_processing_time_ms": round(avg_time, 2),
            "total_chunks_created": total_chunks,
        }

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_uptime_seconds(self) -> float:
        return (datetime.utcnow() - self._start_time).total_seconds()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_time(records: list, start: Optional[datetime], end: Optional[datetime]) -> list:
        if start is None and end is None:
            return records
        return [
            r for r in records
            if (start is None or r.timestamp >= start)
            and (end is None or r.timestamp <= end)
        ]

    async def clear(self) -> None:
        """Clear all collected metrics."""
        async with self._lock:
            self._request_metrics.clear()
            self._doc_metrics.clear()


# Global singleton
metrics_collector = MetricsCollector()
