"""
Unit tests for LLM provider abstraction layer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.llm_providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ProviderConfig,
    ModelCapability,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    ModelUnavailableError
)
from app.services.llm_providers.openai_provider import OpenAIProvider
from app.services.llm_providers.anthropic_provider import AnthropicProvider
from app.services.llm_providers.google_provider import GoogleProvider
from app.services.llm_providers.manager import LLMProviderManager, ProviderRegistry


class TestModelConfig:
    """Test ModelConfig validation and functionality."""
    
    def test_model_config_creation(self):
        """Test creating a valid model config."""
        config = ModelConfig(
            name="test-model",
            input_cost_per_1k_tokens=0.001,
            output_cost_per_1k_tokens=0.002,
            max_tokens=4096,
            context_window=8192,
            capabilities=[ModelCapability.CHAT]
        )
        
        assert config.name == "test-model"
        assert config.input_cost_per_1k_tokens == 0.001
        assert config.output_cost_per_1k_tokens == 0.002
        assert config.max_tokens == 4096
        assert config.context_window == 8192
        assert ModelCapability.CHAT in config.capabilities
    
    def test_model_config_validation(self):
        """Test model config validation."""
        # Test negative costs
        with pytest.raises(ValueError):
            ModelConfig(
                name="test",
                input_cost_per_1k_tokens=-0.001,
                output_cost_per_1k_tokens=0.002,
                max_tokens=4096,
                context_window=8192
            )
        
        # Test zero max_tokens
        with pytest.raises(ValueError):
            ModelConfig(
                name="test",
                input_cost_per_1k_tokens=0.001,
                output_cost_per_1k_tokens=0.002,
                max_tokens=0,
                context_window=8192
            )


class TestProviderConfig:
    """Test ProviderConfig validation and functionality."""
    
    def test_provider_config_creation(self):
        """Test creating a valid provider config."""
        model_config = ModelConfig(
            name="test-model",
            input_cost_per_1k_tokens=0.001,
            output_cost_per_1k_tokens=0.002,
            max_tokens=4096,
            context_window=8192
        )
        
        config = ProviderConfig(
            name="test-provider",
            api_key="test-key",
            models=[model_config],
            enabled=True,
            priority=1
        )
        
        assert config.name == "test-provider"
        assert config.api_key == "test-key"
        assert len(config.models) == 1
        assert config.enabled is True
        assert config.priority == 1


class TestLLMRequest:
    """Test LLMRequest validation and functionality."""
    
    def test_llm_request_creation(self):
        """Test creating a valid LLM request."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            temperature=0.7,
            top_p=1.0,
            stream=False
        )
        
        assert len(request.messages) == 1
        assert request.messages[0]["role"] == "user"
        assert request.max_tokens == 100
        assert request.temperature == 0.7
        assert request.top_p == 1.0
        assert request.stream is False
    
    def test_llm_request_validation(self):
        """Test LLM request validation."""
        # Test invalid temperature
        with pytest.raises(ValueError):
            LLMRequest(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=3.0  # Too high
            )
        
        # Test invalid top_p
        with pytest.raises(ValueError):
            LLMRequest(
                messages=[{"role": "user", "content": "Hello"}],
                top_p=1.5  # Too high
            )


class TestLLMResponse:
    """Test LLMResponse functionality."""
    
    def test_llm_response_creation(self):
        """Test creating a valid LLM response."""
        response = LLMResponse(
            content="Hello there!",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost=0.001,
            provider="test-provider",
            model="test-model"
        )
        
        assert response.content == "Hello there!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.total_tokens == 15
        assert response.cost == 0.001
        assert response.provider == "test-provider"
        assert response.model == "test-model"
        assert isinstance(response.timestamp, datetime)


class MockProvider(LLMProvider):
    """Mock provider for testing base functionality."""
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        model = self.get_best_model_for_request(request) or "mock-model"
        return LLMResponse(
            content="Mock response",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost=0.001,
            provider=self.name,
            model=model
        )
    
    async def is_available(self) -> bool:
        return True
    
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
            return 0.001
        
        input_cost = (input_tokens / 1000) * model_config.input_cost_per_1k_tokens
        output_cost = (output_tokens / 1000) * model_config.output_cost_per_1k_tokens
        
        return input_cost + output_cost


class TestLLMProvider:
    """Test base LLM provider functionality."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        model_config = ModelConfig(
            name="mock-model",
            input_cost_per_1k_tokens=0.001,
            output_cost_per_1k_tokens=0.002,
            max_tokens=4096,
            context_window=8192
        )
        
        config = ProviderConfig(
            name="mock-provider",
            api_key="test-key",
            models=[model_config],
            priority=1
        )
        
        provider = MockProvider(config)
        
        assert provider.name == "mock-provider"
        assert provider.is_enabled is True
        assert provider.priority == 1
    
    def test_provider_validation(self):
        """Test provider configuration validation."""
        # Test missing API key
        config = ProviderConfig(
            name="mock-provider",
            api_key="",
            models=[],
            priority=1
        )
        
        with pytest.raises(ValueError, match="API key is required"):
            MockProvider(config)
        
        # Test missing models
        config = ProviderConfig(
            name="mock-provider",
            api_key="test-key",
            models=[],
            priority=1
        )
        
        with pytest.raises(ValueError, match="At least one model must be configured"):
            MockProvider(config)
    
    def test_get_best_model_for_request(self):
        """Test model selection logic."""
        model_config1 = ModelConfig(
            name="expensive-model",
            input_cost_per_1k_tokens=0.01,
            output_cost_per_1k_tokens=0.02,
            max_tokens=4096,
            context_window=8192
        )
        
        model_config2 = ModelConfig(
            name="cheap-model",
            input_cost_per_1k_tokens=0.001,
            output_cost_per_1k_tokens=0.002,
            max_tokens=4096,
            context_window=8192
        )
        
        config = ProviderConfig(
            name="mock-provider",
            api_key="test-key",
            models=[model_config1, model_config2],
            priority=1
        )
        
        provider = MockProvider(config)
        
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        # Should select the cheaper model
        best_model = provider.get_best_model_for_request(request)
        assert best_model == "cheap-model"
        
        # Should respect model preference
        request.model_preference = "expensive-model"
        best_model = provider.get_best_model_for_request(request)
        assert best_model == "expensive-model"


class TestProviderRegistry:
    """Test provider registry functionality."""
    
    def test_get_provider_class(self):
        """Test getting provider classes."""
        assert ProviderRegistry.get_provider_class("openai") == OpenAIProvider
        assert ProviderRegistry.get_provider_class("anthropic") == AnthropicProvider
        assert ProviderRegistry.get_provider_class("google") == GoogleProvider
        assert ProviderRegistry.get_provider_class("nonexistent") is None
    
    def test_register_provider(self):
        """Test registering new provider."""
        ProviderRegistry.register_provider("mock", MockProvider)
        assert ProviderRegistry.get_provider_class("mock") == MockProvider
    
    def test_get_available_providers(self):
        """Test getting available providers."""
        providers = ProviderRegistry.get_available_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "google" in providers


class TestLLMProviderManager:
    """Test LLM provider manager functionality."""
    
    @pytest.fixture
    def mock_configs(self):
        """Create mock provider configurations."""
        model_config = ModelConfig(
            name="mock-model",
            input_cost_per_1k_tokens=0.001,
            output_cost_per_1k_tokens=0.002,
            max_tokens=4096,
            context_window=8192
        )
        
        return [
            ProviderConfig(
                name="mock1",
                api_key="test-key-1",
                models=[model_config],
                priority=1
            ),
            ProviderConfig(
                name="mock2",
                api_key="test-key-2",
                models=[model_config],
                priority=2
            )
        ]
    
    def test_manager_initialization(self, mock_configs):
        """Test manager initialization."""
        # Register mock providers
        ProviderRegistry.register_provider("mock1", MockProvider)
        ProviderRegistry.register_provider("mock2", MockProvider)
        
        manager = LLMProviderManager(mock_configs)
        
        # Should have initialized providers
        assert len(manager.providers) == 2
        assert all(manager.health_monitor.is_provider_healthy(name) for name in manager.providers.keys())
    
    @pytest.mark.asyncio
    async def test_generate_response_with_cost_tracking(self, mock_configs):
        """Test response generation with cost tracking."""
        # Register mock providers
        ProviderRegistry.register_provider("mock1", MockProvider)
        ProviderRegistry.register_provider("mock2", MockProvider)
        
        # Create a cost tracker for testing
        from app.services.cost_tracker import CostTracker
        test_cost_tracker = CostTracker()
        
        manager = LLMProviderManager(mock_configs, test_cost_tracker)
        
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        response = await manager.generate_response(request, "conv-123", "user-456")
        
        assert response.content == "Mock response"
        assert response.provider in ["mock1", "mock2"]
        
        # Check that usage was recorded in cost tracker
        assert len(test_cost_tracker.usage_records) > 0
        
        # Find the recorded usage
        recorded_usage = None
        for record in test_cost_tracker.usage_records:
            if record.conversation_id == "conv-123" and record.user_id == "user-456":
                recorded_usage = record
                break
        
        assert recorded_usage is not None
        assert recorded_usage.provider in ["mock1", "mock2"]
    
    def test_get_provider_status(self, mock_configs):
        """Test getting provider status."""
        # Register mock providers
        ProviderRegistry.register_provider("mock1", MockProvider)
        ProviderRegistry.register_provider("mock2", MockProvider)
        
        manager = LLMProviderManager(mock_configs)
        status = manager.get_provider_status()
        
        assert len(status) == 2
        for provider_status in status.values():
            assert "enabled" in provider_status
            assert "healthy" in provider_status
            assert "priority" in provider_status
            assert "models" in provider_status
    
    @pytest.mark.asyncio
    async def test_calculate_request_cost(self, mock_configs):
        """Test cost calculation."""
        # Register mock providers
        ProviderRegistry.register_provider("mock1", MockProvider)
        ProviderRegistry.register_provider("mock2", MockProvider)
        
        manager = LLMProviderManager(mock_configs)
        
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        costs = await manager.calculate_request_cost(request)
        
        assert len(costs) == 2
        assert all(cost >= 0 for cost in costs.values())
    
    @pytest.mark.asyncio
    async def test_cost_monitoring_methods(self, mock_configs):
        """Test cost monitoring methods."""
        # Register mock providers
        ProviderRegistry.register_provider("mock1", MockProvider)
        ProviderRegistry.register_provider("mock2", MockProvider)
        
        # Create a cost tracker for testing
        from app.services.cost_tracker import CostTracker
        test_cost_tracker = CostTracker()
        
        manager = LLMProviderManager(mock_configs, test_cost_tracker)
        
        # Test cost summary
        summary = await manager.get_cost_summary()
        assert summary is not None
        assert summary.total_requests >= 0
        assert summary.total_cost >= 0
        
        # Test daily cost
        daily_cost = await manager.get_daily_cost()
        assert daily_cost >= 0
        
        # Test monthly cost
        monthly_cost = await manager.get_monthly_cost()
        assert monthly_cost >= 0
        
        # Test provider efficiency
        efficiency = await manager.get_provider_efficiency()
        assert isinstance(efficiency, dict)
        
        # Test cost alerts
        alerts = await manager.check_cost_alerts()
        assert isinstance(alerts, list)
        
        # Test cost trends
        trends = await manager.get_cost_trends()
        assert isinstance(trends, dict)


class TestProviderExceptions:
    """Test provider exception handling."""
    
    def test_provider_error(self):
        """Test ProviderError creation."""
        error = ProviderError("Test error", "test-provider", retryable=True)
        
        assert str(error) == "Test error"
        assert error.provider == "test-provider"
        assert error.retryable is True
    
    def test_rate_limit_error(self):
        """Test RateLimitError creation."""
        error = RateLimitError("Rate limit exceeded", "test-provider", retry_after=60)
        
        assert str(error) == "Rate limit exceeded"
        assert error.provider == "test-provider"
        assert error.retryable is True
        assert error.retry_after == 60
    
    def test_authentication_error(self):
        """Test AuthenticationError creation."""
        error = AuthenticationError("Invalid API key", "test-provider")
        
        assert str(error) == "Invalid API key"
        assert error.provider == "test-provider"
        assert error.retryable is False
    
    def test_model_unavailable_error(self):
        """Test ModelUnavailableError creation."""
        error = ModelUnavailableError("Model not found", "test-provider", "test-model")
        
        assert str(error) == "Model not found"
        assert error.provider == "test-provider"
        assert error.retryable is True
        assert error.model == "test-model"