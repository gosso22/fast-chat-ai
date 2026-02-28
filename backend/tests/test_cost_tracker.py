"""
Unit tests for cost tracking and monitoring functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from app.services.cost_tracker import CostTracker, UsageRecord, UsageSummary
from app.services.llm_providers.base import LLMResponse


class TestCostTracker:
    """Test cost tracking functionality."""
    
    @pytest.fixture
    def cost_tracker(self):
        """Create a fresh cost tracker for each test."""
        return CostTracker()
    
    @pytest.fixture
    def sample_response(self):
        """Create a sample LLM response for testing."""
        return LLMResponse(
            content="Test response",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.001,
            provider="test-provider",
            model="test-model",
            timestamp=datetime.utcnow()
        )
    
    @pytest.mark.asyncio
    async def test_record_usage(self, cost_tracker, sample_response):
        """Test recording usage from an LLM response."""
        await cost_tracker.record_usage(sample_response, "conv-123", "user-456")
        
        assert len(cost_tracker.usage_records) == 1
        record = cost_tracker.usage_records[0]
        
        assert record.provider == "test-provider"
        assert record.model == "test-model"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.total_tokens == 150
        assert record.cost == 0.001
        assert record.conversation_id == "conv-123"
        assert record.user_id == "user-456"
    
    @pytest.mark.asyncio
    async def test_daily_cost_tracking(self, cost_tracker, sample_response):
        """Test daily cost tracking."""
        # Record usage
        await cost_tracker.record_usage(sample_response)
        
        # Check daily cost
        daily_cost = await cost_tracker.get_daily_cost()
        assert daily_cost == 0.001
        
        # Record another usage
        sample_response.cost = 0.002
        await cost_tracker.record_usage(sample_response)
        
        daily_cost = await cost_tracker.get_daily_cost()
        assert daily_cost == 0.003
    
    @pytest.mark.asyncio
    async def test_monthly_cost_tracking(self, cost_tracker, sample_response):
        """Test monthly cost tracking."""
        await cost_tracker.record_usage(sample_response)
        
        monthly_cost = await cost_tracker.get_monthly_cost()
        assert monthly_cost == 0.001
    
    @pytest.mark.asyncio
    async def test_provider_cost_breakdown(self, cost_tracker, sample_response):
        """Test provider cost breakdown."""
        # Record usage for different providers
        await cost_tracker.record_usage(sample_response)
        
        sample_response.provider = "another-provider"
        sample_response.cost = 0.002
        await cost_tracker.record_usage(sample_response)
        
        provider_costs = await cost_tracker.get_provider_costs()
        assert provider_costs["test-provider"] == 0.001
        assert provider_costs["another-provider"] == 0.002
    
    @pytest.mark.asyncio
    async def test_model_cost_breakdown(self, cost_tracker, sample_response):
        """Test model cost breakdown."""
        await cost_tracker.record_usage(sample_response)
        
        sample_response.model = "another-model"
        sample_response.cost = 0.003
        await cost_tracker.record_usage(sample_response)
        
        model_costs = await cost_tracker.get_model_costs()
        assert model_costs["test-model"] == 0.001
        assert model_costs["another-model"] == 0.003
    
    @pytest.mark.asyncio
    async def test_usage_summary(self, cost_tracker, sample_response):
        """Test usage summary generation."""
        # Record multiple usage records
        await cost_tracker.record_usage(sample_response)
        
        sample_response.cost = 0.002
        sample_response.total_tokens = 200
        await cost_tracker.record_usage(sample_response)
        
        summary = await cost_tracker.get_usage_summary()
        
        assert summary.total_requests == 2
        assert summary.total_tokens == 350  # 150 + 200
        assert summary.total_cost == 0.003  # 0.001 + 0.002
        assert "test-provider" in summary.provider_breakdown
        assert summary.provider_breakdown["test-provider"]["requests"] == 2
    
    @pytest.mark.asyncio
    async def test_usage_summary_with_date_range(self, cost_tracker, sample_response):
        """Test usage summary with date filtering."""
        # Record usage with different timestamps
        old_timestamp = datetime.utcnow() - timedelta(days=10)
        sample_response.timestamp = old_timestamp
        await cost_tracker.record_usage(sample_response)
        
        recent_timestamp = datetime.utcnow() - timedelta(days=1)
        sample_response.timestamp = recent_timestamp
        sample_response.cost = 0.002
        await cost_tracker.record_usage(sample_response)
        
        # Get summary for last 5 days (should only include recent record)
        start_date = datetime.utcnow() - timedelta(days=5)
        summary = await cost_tracker.get_usage_summary(start_date=start_date)
        
        assert summary.total_requests == 1
        assert summary.total_cost == 0.002
    
    @pytest.mark.asyncio
    async def test_cost_trends(self, cost_tracker, sample_response):
        """Test cost trends over time."""
        await cost_tracker.record_usage(sample_response)
        
        trends = await cost_tracker.get_cost_trends(days=7)
        
        # Should have 8 days of data (including today)
        assert len(trends) == 8
        
        # Today should have the recorded cost
        today_key = datetime.utcnow().strftime("%Y-%m-%d")
        assert trends[today_key] == 0.001
    
    @pytest.mark.asyncio
    async def test_cost_alerts(self, cost_tracker, sample_response):
        """Test cost alert system."""
        # Test no alerts initially
        alerts = await cost_tracker.check_cost_alerts(daily_limit=1.0, monthly_limit=10.0)
        assert len(alerts) == 0
        
        # Record high cost usage
        sample_response.cost = 1.5
        await cost_tracker.record_usage(sample_response)
        
        # Should trigger daily limit alert (monthly will also be exceeded since daily = monthly in this case)
        alerts = await cost_tracker.check_cost_alerts(daily_limit=1.0, monthly_limit=1.0)
        assert len(alerts) >= 1  # At least daily exceeded
        assert any("Daily cost limit exceeded" in alert for alert in alerts)
    
    @pytest.mark.asyncio
    async def test_cost_warning_alerts(self, cost_tracker, sample_response):
        """Test cost warning alerts (80% threshold)."""
        # Record usage at 80% of daily limit
        sample_response.cost = 0.8
        await cost_tracker.record_usage(sample_response)
        
        alerts = await cost_tracker.check_cost_alerts(daily_limit=1.0, monthly_limit=1.0)
        assert len(alerts) >= 1  # At least daily warning
        assert any("Daily cost warning" in alert for alert in alerts)
    
    @pytest.mark.asyncio
    async def test_most_expensive_requests(self, cost_tracker, sample_response):
        """Test getting most expensive requests."""
        # Record requests with different costs
        costs = [0.001, 0.005, 0.003, 0.010, 0.002]
        for cost in costs:
            sample_response.cost = cost
            await cost_tracker.record_usage(sample_response)
        
        expensive_requests = await cost_tracker.get_most_expensive_requests(limit=3)
        
        assert len(expensive_requests) == 3
        assert expensive_requests[0].cost == 0.010  # Most expensive first
        assert expensive_requests[1].cost == 0.005
        assert expensive_requests[2].cost == 0.003
    
    @pytest.mark.asyncio
    async def test_provider_efficiency(self, cost_tracker, sample_response):
        """Test provider efficiency calculations."""
        # Record usage for different providers
        await cost_tracker.record_usage(sample_response)  # test-provider: 0.001 cost, 150 tokens
        
        sample_response.provider = "expensive-provider"
        sample_response.cost = 0.010
        sample_response.total_tokens = 100
        await cost_tracker.record_usage(sample_response)
        
        efficiency = await cost_tracker.get_provider_efficiency()
        
        assert "test-provider" in efficiency
        assert "expensive-provider" in efficiency
        
        # test-provider should be more efficient (lower cost per token)
        test_efficiency = efficiency["test-provider"]["cost_per_token"]
        expensive_efficiency = efficiency["expensive-provider"]["cost_per_token"]
        
        assert test_efficiency < expensive_efficiency
    
    @pytest.mark.asyncio
    async def test_clear_old_records(self, cost_tracker, sample_response):
        """Test clearing old usage records."""
        # Record old usage
        old_timestamp = datetime.utcnow() - timedelta(days=100)
        sample_response.timestamp = old_timestamp
        await cost_tracker.record_usage(sample_response)
        
        # Record recent usage
        recent_timestamp = datetime.utcnow() - timedelta(days=1)
        sample_response.timestamp = recent_timestamp
        await cost_tracker.record_usage(sample_response)
        
        assert len(cost_tracker.usage_records) == 2
        
        # Clear records older than 90 days
        removed_count = await cost_tracker.clear_old_records(days_to_keep=90)
        
        assert removed_count == 1
        assert len(cost_tracker.usage_records) == 1
        assert cost_tracker.usage_records[0].timestamp == recent_timestamp


class TestUsageRecord:
    """Test UsageRecord data class."""
    
    def test_usage_record_creation(self):
        """Test creating a usage record."""
        timestamp = datetime.utcnow()
        record = UsageRecord(
            timestamp=timestamp,
            provider="test-provider",
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.001,
            conversation_id="conv-123",
            user_id="user-456"
        )
        
        assert record.timestamp == timestamp
        assert record.provider == "test-provider"
        assert record.model == "test-model"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.total_tokens == 150
        assert record.cost == 0.001
        assert record.conversation_id == "conv-123"
        assert record.user_id == "user-456"


class TestUsageSummary:
    """Test UsageSummary data class."""
    
    def test_usage_summary_creation(self):
        """Test creating a usage summary."""
        provider_breakdown = {
            "provider1": {"tokens": 1000, "cost": 0.01, "requests": 5}
        }
        model_breakdown = {
            "model1": {"tokens": 1000, "cost": 0.01, "requests": 5}
        }
        
        summary = UsageSummary(
            total_requests=5,
            total_tokens=1000,
            total_cost=0.01,
            provider_breakdown=provider_breakdown,
            model_breakdown=model_breakdown,
            time_period="2024-01-01 to 2024-01-31"
        )
        
        assert summary.total_requests == 5
        assert summary.total_tokens == 1000
        assert summary.total_cost == 0.01
        assert summary.provider_breakdown == provider_breakdown
        assert summary.model_breakdown == model_breakdown
        assert summary.time_period == "2024-01-01 to 2024-01-31"