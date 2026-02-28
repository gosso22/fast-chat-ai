"""
Base classes and interfaces for LLM providers.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    """Capabilities that a model can have."""
    CHAT = "chat"
    COMPLETION = "completion"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    CODE = "code"


class ModelConfig(BaseModel):
    """Configuration for a specific model."""
    name: str
    input_cost_per_1k_tokens: float = Field(ge=0, description="Cost per 1000 input tokens")
    output_cost_per_1k_tokens: float = Field(ge=0, description="Cost per 1000 output tokens")
    max_tokens: int = Field(gt=0, description="Maximum tokens the model can handle")
    capabilities: List[ModelCapability] = Field(default_factory=list)
    context_window: int = Field(gt=0, description="Maximum context window size")


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""
    name: str
    api_key: str
    models: List[ModelConfig]
    enabled: bool = True
    priority: int = Field(ge=1, description="Provider priority (1 = highest)")
    base_url: Optional[str] = None
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")


class LLMResponse(BaseModel):
    """Response from an LLM provider."""
    content: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost: float = Field(ge=0)
    provider: str
    model: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMRequest(BaseModel):
    """Request to an LLM provider."""
    messages: List[Dict[str, str]]
    max_tokens: Optional[int] = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=1.0, ge=0, le=1)
    stream: bool = False
    model_preference: Optional[str] = None


class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, message: str, provider: str, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Exception raised when rate limit is exceeded."""
    def __init__(self, message: str, provider: str, retry_after: Optional[int] = None):
        super().__init__(message, provider, retryable=True)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Exception raised when authentication fails."""
    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, retryable=False)


class ModelUnavailableError(ProviderError):
    """Exception raised when a model is unavailable."""
    def __init__(self, message: str, provider: str, model: str):
        super().__init__(message, provider, retryable=True)
        self.model = model


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate provider configuration."""
        if not self.config.api_key:
            raise ValueError(f"API key is required for {self.config.name}")
        if not self.config.models:
            raise ValueError(f"At least one model must be configured for {self.config.name}")
    
    @property
    def name(self) -> str:
        """Get provider name."""
        return self.config.name
    
    @property
    def is_enabled(self) -> bool:
        """Check if provider is enabled."""
        return self.config.enabled
    
    @property
    def priority(self) -> int:
        """Get provider priority."""
        return self.config.priority
    
    @abstractmethod
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a response using the LLM provider."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is currently available."""
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available model names."""
        pass
    
    @abstractmethod
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a specific model."""
        pass
    
    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """Calculate cost for token usage."""
        pass
    
    def get_best_model_for_request(self, request: LLMRequest) -> Optional[str]:
        """Get the best model for a given request based on cost and capabilities."""
        available_models = self.get_available_models()
        
        # If user specified a model preference, use it if available
        if request.model_preference and request.model_preference in available_models:
            return request.model_preference
        
        # Otherwise, select the cheapest model that can handle the request
        best_model = None
        best_cost = float('inf')
        
        for model_name in available_models:
            model_config = self.get_model_config(model_name)
            if not model_config:
                continue
            
            # Estimate cost (assuming average output tokens)
            estimated_output_tokens = min(request.max_tokens or 500, 500)
            estimated_input_tokens = sum(len(msg.get("content", "")) for msg in request.messages) // 4  # Rough token estimate
            
            cost = self.calculate_cost(estimated_input_tokens, estimated_output_tokens, model_name)
            
            if cost < best_cost:
                best_cost = cost
                best_model = model_name
        
        return best_model