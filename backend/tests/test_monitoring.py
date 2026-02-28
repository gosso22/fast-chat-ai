"""
Tests for the monitoring, health-check, and usage reporting system.

Covers:
- MetricsCollector service (request & document processing metrics)
- Health check endpoints (quick and detailed)
- Usage reporting endpoints (LLM costs, document stats, request stats)
- Cost alert integration

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.services.metrics_collector import (
    MetricsCollector,
    RequestMetric,
    DocumentProcessingMetric,
)


# ======================================================================
# MetricsCollector unit tests
# ======================================================================


class TestMetricsCollector:
    @pytest.fixture
    def collector(self):
        return MetricsCollector()

    # --- Request metrics ---

    @pytest.mark.asyncio
    async def test_record_and_query_request_metric(self, collector):
        await collector.record_request(RequestMetric(
            endpoint="/api/v1/chat",
            method="POST",
            status_code=200,
            duration_ms=150.0,
        ))
        stats = await collector.get_request_stats()
        assert stats["total_requests"] == 1
        assert stats["avg_response_time_ms"] == 150.0
        assert stats["error_count"] == 0
        assert stats["error_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_error_rate_calculation(self, collector):
        for code in [200, 200, 500, 422]:
            await collector.record_request(RequestMetric(
                endpoint="/test", method="GET", status_code=code, duration_ms=10.0,
            ))
        stats = await collector.get_request_stats()
        assert stats["total_requests"] == 4
        assert stats["error_count"] == 2
        assert stats["error_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_endpoint_breakdown(self, collector):
        await collector.record_request(RequestMetric(
            endpoint="/a", method="GET", status_code=200, duration_ms=10.0,
        ))
        await collector.record_request(RequestMetric(
            endpoint="/a", method="GET", status_code=200, duration_ms=30.0,
        ))
        await collector.record_request(RequestMetric(
            endpoint="/b", method="POST", status_code=500, duration_ms=5.0,
        ))
        stats = await collector.get_request_stats()
        assert stats["endpoint_breakdown"]["/a"]["count"] == 2
        assert stats["endpoint_breakdown"]["/a"]["avg_ms"] == 20.0
        assert stats["endpoint_breakdown"]["/b"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_status_code_breakdown(self, collector):
        for code in [200, 200, 201, 404]:
            await collector.record_request(RequestMetric(
                endpoint="/x", method="GET", status_code=code, duration_ms=1.0,
            ))
        stats = await collector.get_request_stats()
        assert stats["status_code_breakdown"]["200"] == 2
        assert stats["status_code_breakdown"]["201"] == 1
        assert stats["status_code_breakdown"]["404"] == 1

    @pytest.mark.asyncio
    async def test_time_range_filtering(self, collector):
        old = datetime.utcnow() - timedelta(days=5)
        recent = datetime.utcnow()
        await collector.record_request(RequestMetric(
            endpoint="/old", method="GET", status_code=200, duration_ms=1.0, timestamp=old,
        ))
        await collector.record_request(RequestMetric(
            endpoint="/new", method="GET", status_code=200, duration_ms=2.0, timestamp=recent,
        ))
        stats = await collector.get_request_stats(
            start=datetime.utcnow() - timedelta(days=1),
        )
        assert stats["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_empty_stats(self, collector):
        stats = await collector.get_request_stats()
        assert stats["total_requests"] == 0
        assert stats["avg_response_time_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_max_records_cap(self):
        collector = MetricsCollector(max_records=5)
        for i in range(10):
            await collector.record_request(RequestMetric(
                endpoint="/x", method="GET", status_code=200, duration_ms=float(i),
            ))
        stats = await collector.get_request_stats()
        assert stats["total_requests"] == 5

    # --- Document processing metrics ---

    @pytest.mark.asyncio
    async def test_record_document_processing(self, collector):
        await collector.record_document_processing(DocumentProcessingMetric(
            document_id="doc-1",
            filename="test.pdf",
            file_size=1024,
            processing_time_ms=500.0,
            chunk_count=10,
            success=True,
        ))
        stats = await collector.get_document_processing_stats()
        assert stats["total_processed"] == 1
        assert stats["success_count"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["total_chunks_created"] == 10

    @pytest.mark.asyncio
    async def test_document_processing_failure_tracking(self, collector):
        await collector.record_document_processing(DocumentProcessingMetric(
            document_id="doc-1", filename="good.pdf", file_size=100,
            processing_time_ms=100.0, chunk_count=5, success=True,
        ))
        await collector.record_document_processing(DocumentProcessingMetric(
            document_id="doc-2", filename="bad.pdf", file_size=200,
            processing_time_ms=50.0, chunk_count=0, success=False,
            error="Corrupt file",
        ))
        stats = await collector.get_document_processing_stats()
        assert stats["total_processed"] == 2
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_empty_document_stats(self, collector):
        stats = await collector.get_document_processing_stats()
        assert stats["total_processed"] == 0
        assert stats["success_rate"] == 0.0

    # --- Uptime ---

    def test_uptime_seconds(self, collector):
        assert collector.get_uptime_seconds() >= 0

    # --- Clear ---

    @pytest.mark.asyncio
    async def test_clear(self, collector):
        await collector.record_request(RequestMetric(
            endpoint="/x", method="GET", status_code=200, duration_ms=1.0,
        ))
        await collector.clear()
        stats = await collector.get_request_stats()
        assert stats["total_requests"] == 0


# ======================================================================
# API endpoint tests
# ======================================================================


class TestHealthEndpoints:
    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app)

    def test_quick_health_check(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    @patch("app.api.monitoring.metrics_collector")
    def test_detailed_health_check_structure(self, mock_collector, client):
        mock_collector.get_uptime_seconds.return_value = 42.0
        resp = client.get("/api/v1/health/detailed")
        # May be degraded if DB/Redis aren't running in test env – that's fine
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "uptime_seconds" in data


class TestUsageEndpoints:
    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app)

    @patch("app.api.monitoring.cost_tracker")
    @patch("app.api.monitoring.metrics_collector")
    def test_usage_report(self, mock_metrics, mock_cost, client):
        mock_cost.get_usage_summary = AsyncMock(return_value=MagicMock(
            total_requests=5, total_tokens=1000, total_cost=0.05,
            provider_breakdown={}, model_breakdown={},
        ))
        mock_cost.get_cost_trends = AsyncMock(return_value={})
        mock_cost.check_cost_alerts = AsyncMock(return_value=[])
        mock_cost.get_provider_efficiency = AsyncMock(return_value={})
        mock_metrics.get_document_processing_stats = AsyncMock(return_value={
            "total_processed": 0, "success_count": 0, "failure_count": 0,
            "success_rate": 0.0, "avg_processing_time_ms": 0.0,
            "total_chunks_created": 0,
        })

        resp = client.get("/api/v1/metrics/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_usage" in data
        assert "document_processing" in data
        assert "alerts" in data
        assert data["llm_usage"]["total_requests"] == 5

    @patch("app.api.monitoring.cost_tracker")
    @patch("app.api.monitoring.metrics_collector")
    def test_usage_report_with_date_range(self, mock_metrics, mock_cost, client):
        mock_cost.get_usage_summary = AsyncMock(return_value=MagicMock(
            total_requests=0, total_tokens=0, total_cost=0.0,
            provider_breakdown={}, model_breakdown={},
        ))
        mock_cost.get_cost_trends = AsyncMock(return_value={})
        mock_cost.check_cost_alerts = AsyncMock(return_value=[])
        mock_cost.get_provider_efficiency = AsyncMock(return_value={})
        mock_metrics.get_document_processing_stats = AsyncMock(return_value={
            "total_processed": 0, "success_count": 0, "failure_count": 0,
            "success_rate": 0.0, "avg_processing_time_ms": 0.0,
            "total_chunks_created": 0,
        })

        resp = client.get(
            "/api/v1/metrics/usage",
            params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
        )
        assert resp.status_code == 200

    @patch("app.api.monitoring.metrics_collector")
    def test_request_metrics(self, mock_metrics, client):
        mock_metrics.get_request_stats = AsyncMock(return_value={
            "total_requests": 10,
            "avg_response_time_ms": 42.5,
            "error_count": 1,
            "error_rate": 0.1,
            "status_code_breakdown": {"200": 9, "500": 1},
            "endpoint_breakdown": {},
        })

        resp = client.get("/api/v1/metrics/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 10
        assert data["avg_response_time_ms"] == 42.5


class TestCostAlertIntegration:
    """Verify cost alert logic surfaces through the usage endpoint."""

    @patch("app.api.monitoring.cost_tracker")
    @patch("app.api.monitoring.metrics_collector")
    def test_alerts_included_in_usage_report(self, mock_metrics, mock_cost):
        from app.main import app
        client = TestClient(app)

        mock_cost.get_usage_summary = AsyncMock(return_value=MagicMock(
            total_requests=0, total_tokens=0, total_cost=0.0,
            provider_breakdown={}, model_breakdown={},
        ))
        mock_cost.get_cost_trends = AsyncMock(return_value={})
        mock_cost.check_cost_alerts = AsyncMock(return_value=[
            "Daily cost limit exceeded: $12.00 >= $10.00"
        ])
        mock_cost.get_provider_efficiency = AsyncMock(return_value={})
        mock_metrics.get_document_processing_stats = AsyncMock(return_value={
            "total_processed": 0, "success_count": 0, "failure_count": 0,
            "success_rate": 0.0, "avg_processing_time_ms": 0.0,
            "total_chunks_created": 0,
        })

        resp = client.get("/api/v1/metrics/usage")
        data = resp.json()
        assert len(data["alerts"]) == 1
        assert "exceeded" in data["alerts"][0]
