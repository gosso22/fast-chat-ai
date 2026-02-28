"""
Integration tests for LLM provider failover and error handling.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta

from app.services.llm_providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderConfig,
    ModelConfig,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    ModelUnavailableError,
    ModelCapability
)
from app.services.llm_providers.manager import (
    LLMProviderManager,
    ExponentialBackoff,
    ProviderHealthMonitor,
    ProviderRegistry
)


class MockProvider(LLMProvider):
    """Mock provider for testing."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.generate_response_mock = AsyncMock()
        self.is_available_mock = AsyncMock(return_value=True)
        self.call_count = 0
        
        # Default model config
        if not config.models:
            self.config.models = [
                ModelConfig(
                    name="mock-model",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=8192,
                    capabilities=[ModelCapability.CHAT]
                )
            ]
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return await self.generate_response_mock(request)
    
    async def is_available(self) -> bool:
        return await self.is_available_mock()
    
    def get_available_models(self) -> list[str]:
        return [model.name for model in self.config.models]
    
    def get_model_config(self, model_name: str) -> ModelConfig | None:
        for model in self.config.models:
            if model.name == model_name:
                return model
        return None
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        model_config = self.get_model_config(model_name)
        if not model_config:
            return 0.0
        
        input_cost = (input_tokens / 1000) * model_config.input_cost_per_1k_tokens
        output_cost = (output_tokens / 1000) * model_config.output_cost_per_1k_tokens
        return input_cost + output_cost


@pytest.fixture
def sample_request():
    """Sample LLM request for testing."""
    return LLMRequest(
        messages=[{"role": "user", "content": "Hello, world!"}],
        max_tokens=100,
        temperature=0.7
    )


@pytest.fixture
def sample_response():
    """Sample LLM response for testing."""
    return LLMResponse(
        content="Hello! How can I help you?",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        cost=0.05,
        provider="mock",
        model="mock-model"
    )


@pytest.fixture
def provider_configs():
    """Sample provider configurations."""
    return [
        ProviderConfig(
            name="provider1",
            api_key="key1",
            models=[
                ModelConfig(
                    name="mock-model-1",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=8192,
                    capabilities=[ModelCapability.CHAT]
                )
            ],
            enabled=True,
            priority=1
        ),
        ProviderConfig(
            name="provider2",
            api_key="key2",
            models=[
                ModelConfig(
                    name="mock-model-2",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=8192,
                    capabilities=[ModelCapability.CHAT]
                )
            ],
            enabled=True,
            priority=2
        ),
        ProviderConfig(
            name="provider3",
            api_key="key3",
            models=[
                ModelConfig(
                    name="mock-model-3",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=8192,
                    capabilities=[ModelCapability.CHAT]
                )
            ],
            enabled=True,
            priority=3
        )
    ]


class TestExponentialBackoff:
    """Test exponential backoff functionality."""
    
    def test_calculate_delay(self):
        """Test delay calculation."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0, jitter=False)
        
        assert backoff.calculate_delay(0) == 0
        assert backoff.calculate_delay(1) == 1.0
        assert backoff.calculate_delay(2) == 2.0
        assert backoff.calculate_delay(3) == 4.0
        assert backoff.calculate_delay(4) == 8.0
        
        # Test max delay cap
        assert backoff.calculate_delay(10) == 60.0
    
    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0, jitter=True)
        
        delay1 = backoff.calculate_delay(3)
        delay2 = backoff.calculate_delay(3)
        
        # With jitter, delays should be different
        assert delay1 != delay2
        # But both should be between 2.0 and 4.0 (50% to 100% of base delay)
        assert 2.0 <= delay1 <= 4.0
        assert 2.0 <= delay2 <= 4.0
    
    @pytest.mark.asyncio
    async def test_execute_with_backoff_success(self):
        """Test successful execution without retries."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        
        async def success_func():
            return "success"
        
        result = await backoff.execute_with_backoff(success_func)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_execute_with_backoff_retry_success(self):
        """Test successful execution after retries."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        call_count = 0
        
        async def retry_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RateLimitError("Rate limited", "test")
            return "success"
        
        result = await backoff.execute_with_backoff(retry_then_success)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_with_backoff_max_retries(self):
        """Test failure after max retries."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=2)
        
        async def always_fail():
            raise RateLimitError("Always fails", "test")
        
        with pytest.raises(RateLimitError):
            await backoff.execute_with_backoff(always_fail)
    
    @pytest.mark.asyncio
    async def test_execute_with_backoff_non_retryable(self):
        """Test immediate failure on non-retryable errors."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        
        async def non_retryable_error():
            raise ProviderError("Non-retryable", "test", retryable=False)
        
        with pytest.raises(ProviderError):
            await backoff.execute_with_backoff(non_retryable_error)
    
    @pytest.mark.asyncio
    async def test_execute_with_backoff_rate_limit_retry_after(self):
        """Test respecting retry_after in rate limit errors."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=1)
        
        start_time = datetime.utcnow()
        
        async def rate_limit_with_retry_after():
            raise RateLimitError("Rate limited", "test", retry_after=0.1)
        
        with pytest.raises(RateLimitError):
            await backoff.execute_with_backoff(rate_limit_with_retry_after)
        
        # Should have waited at least 0.1 seconds
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        assert elapsed >= 0.1


class TestProviderHealthMonitor:
    """Test provider health monitoring functionality."""
    
    def test_mark_provider_healthy(self):
        """Test marking provider as healthy."""
        monitor = ProviderHealthMonitor()
        
        monitor.mark_provider_healthy("test_provider")
        
        assert monitor.is_provider_healthy("test_provider") is True
        assert monitor.get_failure_count("test_provider") == 0
        assert "test_provider" in monitor.last_health_check
    
    def test_mark_provider_unhealthy(self):
        """Test marking provider as unhealthy."""
        monitor = ProviderHealthMonitor()
        
        error = Exception("Test error")
        monitor.mark_provider_unhealthy("test_provider", error)
        
        assert monitor.is_provider_healthy("test_provider") is False
        assert monitor.get_failure_count("test_provider") == 1
        assert "test_provider" in monitor.last_failure
    
    def test_should_check_health_healthy_provider(self):
        """Test health check timing for healthy providers."""
        monitor = ProviderHealthMonitor(
            health_check_interval=timedelta(minutes=5)
        )
        
        # Mark as healthy
        monitor.mark_provider_healthy("test_provider")
        
        # Should not check immediately
        assert monitor.should_check_health("test_provider") is False
        
        # Simulate time passing
        monitor.last_health_check["test_provider"] = datetime.utcnow() - timedelta(minutes=6)
        
        # Should check now
        assert monitor.should_check_health("test_provider") is True
    
    def test_should_check_health_unhealthy_provider(self):
        """Test health check timing for unhealthy providers."""
        monitor = ProviderHealthMonitor(
            recovery_check_interval=timedelta(minutes=15)
        )
        
        # Initially, provider has no health check history, so should check
        assert monitor.should_check_health("test_provider") is True
        
        # Mark as unhealthy (this doesn't set last_health_check)
        monitor.mark_provider_unhealthy("test_provider", Exception("Test"))
        
        # Still should check because last_health_check defaults to datetime.min
        assert monitor.should_check_health("test_provider") is True
        
        # Now simulate that we just did a health check by setting last_health_check to now
        monitor.last_health_check["test_provider"] = datetime.utcnow()
        
        # Should not check immediately after a health check
        assert monitor.should_check_health("test_provider") is False
        
        # Simulate time passing beyond recovery interval
        monitor.last_health_check["test_provider"] = datetime.utcnow() - timedelta(minutes=16)
        
        # Should check now
        assert monitor.should_check_health("test_provider") is True
    
    def test_should_attempt_recovery(self):
        """Test recovery attempt logic."""
        monitor = ProviderHealthMonitor()
        
        # Healthy provider should not attempt recovery
        monitor.mark_provider_healthy("test_provider")
        assert monitor.should_attempt_recovery("test_provider") is False
        
        # Unhealthy provider should wait before recovery
        monitor.mark_provider_unhealthy("test_provider", Exception("Test"))
        assert monitor.should_attempt_recovery("test_provider") is False
        
        # Simulate time passing
        monitor.last_failure["test_provider"] = datetime.utcnow() - timedelta(minutes=3)
        assert monitor.should_attempt_recovery("test_provider") is True
    
    def test_increment_recovery_attempt(self):
        """Test recovery attempt counter."""
        monitor = ProviderHealthMonitor()
        
        assert monitor.recovery_attempts.get("test_provider", 0) == 0
        
        monitor.increment_recovery_attempt("test_provider")
        assert monitor.recovery_attempts["test_provider"] == 1
        
        monitor.increment_recovery_attempt("test_provider")
        assert monitor.recovery_attempts["test_provider"] == 2


class TestLLMProviderManagerFailover:
    """Test LLM provider manager failover scenarios."""
    
    @pytest.mark.asyncio
    async def test_successful_response_first_provider(self, provider_configs, sample_request, sample_response):
        """Test successful response from first provider."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        ProviderRegistry.register_provider("provider2", MockProvider)
        ProviderRegistry.register_provider("provider3", MockProvider)
        
        manager = LLMProviderManager(provider_configs)
        
        # Configure first provider to succeed
        provider1 = manager.get_provider("provider1")
        provider1.generate_response_mock.return_value = sample_response
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        assert provider1.call_count == 1
        
        # Other providers should not be called
        provider2 = manager.get_provider("provider2")
        provider3 = manager.get_provider("provider3")
        assert provider2.call_count == 0
        assert provider3.call_count == 0
    
    @pytest.mark.asyncio
    async def test_failover_to_second_provider(self, provider_configs, sample_request, sample_response):
        """Test failover to second provider when first fails."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        ProviderRegistry.register_provider("provider2", MockProvider)
        ProviderRegistry.register_provider("provider3", MockProvider)
        
        manager = LLMProviderManager(provider_configs)
        
        # Configure first provider to fail, second to succeed
        provider1 = manager.get_provider("provider1")
        provider1.generate_response_mock.side_effect = RateLimitError("Rate limited", "provider1")
        
        provider2 = manager.get_provider("provider2")
        provider2.generate_response_mock.return_value = sample_response
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        assert provider2.call_count == 1
        
        # First provider should be marked as unhealthy
        assert not manager.health_monitor.is_provider_healthy("provider1")
        assert manager.health_monitor.is_provider_healthy("provider2")
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self, provider_configs, sample_request):
        """Test behavior when all providers fail."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        ProviderRegistry.register_provider("provider2", MockProvider)
        ProviderRegistry.register_provider("provider3", MockProvider)
        
        manager = LLMProviderManager(provider_configs)
        
        # Configure all providers to fail
        for provider_name in ["provider1", "provider2", "provider3"]:
            provider = manager.get_provider(provider_name)
            provider.generate_response_mock.side_effect = RateLimitError("Rate limited", provider_name)
        
        with pytest.raises(ProviderError, match="All providers failed"):
            await manager.generate_response(sample_request)
        
        # All providers should be marked as unhealthy
        for provider_name in ["provider1", "provider2", "provider3"]:
            assert not manager.health_monitor.is_provider_healthy(provider_name)
    
    @pytest.mark.asyncio
    async def test_authentication_error_marks_unhealthy(self, provider_configs, sample_request):
        """Test that authentication errors mark providers as unhealthy."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        ProviderRegistry.register_provider("provider2", MockProvider)
        
        manager = LLMProviderManager(provider_configs[:2])
        
        # Configure first provider to have auth error, second to succeed
        provider1 = manager.get_provider("provider1")
        provider1.generate_response_mock.side_effect = AuthenticationError("Invalid API key", "provider1")
        
        provider2 = manager.get_provider("provider2")
        sample_response = LLMResponse(
            content="Success",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cost=0.05,
            provider="provider2",
            model="mock-model"
        )
        provider2.generate_response_mock.return_value = sample_response
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        assert not manager.health_monitor.is_provider_healthy("provider1")
        assert manager.health_monitor.is_provider_healthy("provider2")
    
    @pytest.mark.asyncio
    async def test_model_unavailable_does_not_mark_unhealthy(self, provider_configs, sample_request):
        """Test that model unavailable errors don't mark providers as unhealthy."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        ProviderRegistry.register_provider("provider2", MockProvider)
        
        manager = LLMProviderManager(provider_configs[:2])
        
        # Configure first provider to have model unavailable, second to succeed
        provider1 = manager.get_provider("provider1")
        provider1.generate_response_mock.side_effect = ModelUnavailableError("Model not found", "provider1", "model")
        
        provider2 = manager.get_provider("provider2")
        sample_response = LLMResponse(
            content="Success",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cost=0.05,
            provider="provider2",
            model="mock-model"
        )
        provider2.generate_response_mock.return_value = sample_response
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        # Provider1 should still be considered healthy (model unavailable is temporary)
        assert manager.health_monitor.is_provider_healthy("provider1")
        assert manager.health_monitor.is_provider_healthy("provider2")
    
    @pytest.mark.asyncio
    async def test_health_check_recovery(self, provider_configs, sample_request):
        """Test provider recovery through health checks."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        
        manager = LLMProviderManager(provider_configs[:1])
        provider1 = manager.get_provider("provider1")
        
        # Mark provider as unhealthy
        manager.health_monitor.mark_provider_unhealthy("provider1", Exception("Test error"))
        
        # Configure provider to be available again
        provider1.is_available_mock.return_value = True
        
        # Force health check by setting last check time to past
        manager.health_monitor.last_health_check["provider1"] = datetime.utcnow() - timedelta(hours=1)
        manager.health_monitor.last_failure["provider1"] = datetime.utcnow() - timedelta(hours=1)
        
        # Check if provider is healthy (should trigger health check)
        is_healthy = await manager._is_provider_healthy(provider1)
        
        assert is_healthy
        assert manager.health_monitor.is_provider_healthy("provider1")
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_integration(self, provider_configs, sample_request, sample_response):
        """Test exponential backoff integration with provider manager."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        
        # Use shorter delays for testing
        manager = LLMProviderManager(provider_configs[:1])
        manager.backoff = ExponentialBackoff(base_delay=0.01, max_retries=2)
        
        provider1 = manager.get_provider("provider1")
        
        # Configure provider to fail twice, then succeed
        call_count = 0
        async def mock_generate_response(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RateLimitError("Rate limited", "provider1")
            return sample_response
        
        provider1.generate_response_mock.side_effect = mock_generate_response
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        assert call_count == 3  # Failed twice, succeeded on third try
    
    @pytest.mark.asyncio
    async def test_provider_priority_ordering(self, sample_request, sample_response):
        """Test that providers are tried in priority order."""
        configs = [
            ProviderConfig(
                name="high_priority", 
                api_key="key1", 
                models=[
                    ModelConfig(
                        name="mock-model-high",
                        input_cost_per_1k_tokens=0.001,
                        output_cost_per_1k_tokens=0.002,
                        max_tokens=4096,
                        context_window=8192,
                        capabilities=[ModelCapability.CHAT]
                    )
                ], 
                enabled=True, 
                priority=1
            ),
            ProviderConfig(
                name="low_priority", 
                api_key="key2", 
                models=[
                    ModelConfig(
                        name="mock-model-low",
                        input_cost_per_1k_tokens=0.001,
                        output_cost_per_1k_tokens=0.002,
                        max_tokens=4096,
                        context_window=8192,
                        capabilities=[ModelCapability.CHAT]
                    )
                ], 
                enabled=True, 
                priority=3
            ),
            ProviderConfig(
                name="medium_priority", 
                api_key="key3", 
                models=[
                    ModelConfig(
                        name="mock-model-medium",
                        input_cost_per_1k_tokens=0.001,
                        output_cost_per_1k_tokens=0.002,
                        max_tokens=4096,
                        context_window=8192,
                        capabilities=[ModelCapability.CHAT]
                    )
                ], 
                enabled=True, 
                priority=2
            ),
        ]
        
        # Register mock providers
        for config in configs:
            ProviderRegistry.register_provider(config.name, MockProvider)
        
        manager = LLMProviderManager(configs)
        # Disable exponential backoff for this test to avoid retries
        manager.backoff = ExponentialBackoff(base_delay=0.01, max_retries=0)
        
        # Configure high priority provider to fail, medium priority to succeed
        high_priority = manager.get_provider("high_priority")
        high_priority.generate_response_mock.side_effect = RateLimitError("Rate limited", "high_priority")
        
        medium_priority = manager.get_provider("medium_priority")
        medium_priority.generate_response_mock.return_value = sample_response
        
        low_priority = manager.get_provider("low_priority")
        
        result = await manager.generate_response(sample_request)
        
        assert result == sample_response
        assert high_priority.call_count == 1  # Tried first (no retries)
        assert medium_priority.call_count == 1  # Succeeded second
        assert low_priority.call_count == 0  # Never tried
    
    def test_get_provider_status_with_health_info(self, provider_configs):
        """Test provider status includes health information."""
        # Register mock provider
        ProviderRegistry.register_provider("provider1", MockProvider)
        
        manager = LLMProviderManager(provider_configs[:1])
        
        # Mark provider as unhealthy with some failures
        manager.health_monitor.mark_provider_unhealthy("provider1", Exception("Test error"))
        manager.health_monitor.mark_provider_unhealthy("provider1", Exception("Another error"))
        
        status = manager.get_provider_status()
        
        assert "provider1" in status
        provider_status = status["provider1"]
        
        assert provider_status["enabled"] is True
        assert provider_status["healthy"] is False
        assert provider_status["failure_count"] == 2
        assert provider_status["recovery_attempts"] == 0
        assert "last_health_check" in provider_status