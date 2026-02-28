"""
LLM Provider Manager for coordinating multiple providers.
"""

import asyncio
import logging
import random
from typing import Dict, List, Optional, Type
from datetime import datetime, timedelta

from .base import (
    LLMProvider, 
    LLMRequest, 
    LLMResponse, 
    ProviderConfig,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    ModelUnavailableError
)
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleProvider

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    """Implements exponential backoff with jitter for retries."""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, 
                 max_retries: int = 3, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number."""
        if attempt <= 0:
            return 0
        
        # Exponential backoff: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        # Add jitter to avoid thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay
    
    async def execute_with_backoff(self, func, *args, **kwargs):
        """Execute a function with exponential backoff on retryable errors."""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except (RateLimitError, ProviderError) as e:
                last_error = e
                
                # Don't retry on non-retryable errors
                if isinstance(e, ProviderError) and not e.retryable:
                    raise e
                
                # Don't retry on the last attempt
                if attempt >= self.max_retries:
                    break
                
                # Calculate delay and wait
                delay = self.calculate_delay(attempt + 1)
                
                # For rate limit errors, respect the retry_after if provided
                if isinstance(e, RateLimitError) and e.retry_after:
                    delay = max(delay, e.retry_after)
                
                logger.info(f"Retrying after {delay:.2f}s (attempt {attempt + 1}/{self.max_retries})")
                await asyncio.sleep(delay)
        
        # All retries exhausted
        raise last_error


class ProviderHealthMonitor:
    """Monitors provider health and manages recovery."""
    
    def __init__(self, health_check_interval: timedelta = timedelta(minutes=5),
                 recovery_check_interval: timedelta = timedelta(minutes=15)):
        self.health_check_interval = health_check_interval
        self.recovery_check_interval = recovery_check_interval
        self.provider_health: Dict[str, bool] = {}
        self.last_health_check: Dict[str, datetime] = {}
        self.last_failure: Dict[str, datetime] = {}
        self.failure_count: Dict[str, int] = {}
        self.recovery_attempts: Dict[str, int] = {}
    
    def mark_provider_healthy(self, provider_name: str) -> None:
        """Mark a provider as healthy."""
        self.provider_health[provider_name] = True
        self.last_health_check[provider_name] = datetime.utcnow()
        self.failure_count[provider_name] = 0
        self.recovery_attempts[provider_name] = 0
        logger.info(f"Provider {provider_name} marked as healthy")
    
    def mark_provider_unhealthy(self, provider_name: str, error: Exception) -> None:
        """Mark a provider as unhealthy."""
        self.provider_health[provider_name] = False
        self.last_failure[provider_name] = datetime.utcnow()
        self.failure_count[provider_name] = self.failure_count.get(provider_name, 0) + 1
        logger.warning(f"Provider {provider_name} marked as unhealthy: {error}")
    
    def should_check_health(self, provider_name: str) -> bool:
        """Check if we should perform a health check for a provider."""
        now = datetime.utcnow()
        last_check = self.last_health_check.get(provider_name, datetime.min)
        
        # If provider is healthy, check less frequently
        if self.provider_health.get(provider_name, False):
            return (now - last_check) >= self.health_check_interval
        
        # If provider is unhealthy, check for recovery less frequently
        return (now - last_check) >= self.recovery_check_interval
    
    def is_provider_healthy(self, provider_name: str) -> bool:
        """Get the current health status of a provider."""
        return self.provider_health.get(provider_name, True)  # Assume healthy by default
    
    def get_failure_count(self, provider_name: str) -> int:
        """Get the failure count for a provider."""
        return self.failure_count.get(provider_name, 0)
    
    def should_attempt_recovery(self, provider_name: str) -> bool:
        """Check if we should attempt recovery for an unhealthy provider."""
        if self.is_provider_healthy(provider_name):
            return False
        
        now = datetime.utcnow()
        last_failure = self.last_failure.get(provider_name, datetime.min)
        recovery_attempts = self.recovery_attempts.get(provider_name, 0)
        
        # Exponential backoff for recovery attempts
        min_wait_time = timedelta(minutes=2 ** min(recovery_attempts, 6))  # Cap at 64 minutes
        
        return (now - last_failure) >= min_wait_time
    
    def increment_recovery_attempt(self, provider_name: str) -> None:
        """Increment the recovery attempt counter."""
        self.recovery_attempts[provider_name] = self.recovery_attempts.get(provider_name, 0) + 1


class ProviderRegistry:
    """Registry of available provider implementations."""
    
    _providers: Dict[str, Type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
    }
    
    @classmethod
    def get_provider_class(cls, provider_name: str) -> Optional[Type[LLMProvider]]:
        """Get provider class by name."""
        return cls._providers.get(provider_name.lower())
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[LLMProvider]) -> None:
        """Register a new provider class."""
        cls._providers[name.lower()] = provider_class
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available provider names."""
        return list(cls._providers.keys())


class LLMProviderManager:
    """Manager for coordinating multiple LLM providers."""
    
    def __init__(self, provider_configs: List[ProviderConfig], cost_tracker=None):
        self.providers: Dict[str, LLMProvider] = {}
        self.cost_tracker = cost_tracker
        
        # Initialize health monitoring and backoff
        self.health_monitor = ProviderHealthMonitor()
        self.backoff = ExponentialBackoff(
            base_delay=1.0,
            max_delay=60.0,
            max_retries=3,
            jitter=True
        )
        
        # Initialize providers
        for config in provider_configs:
            self._initialize_provider(config)
    
    def _initialize_provider(self, config: ProviderConfig) -> None:
        """Initialize a provider from configuration."""
        if not config.enabled:
            logger.info(f"Provider {config.name} is disabled, skipping initialization")
            return
        
        provider_class = ProviderRegistry.get_provider_class(config.name)
        if not provider_class:
            logger.error(f"Unknown provider: {config.name}")
            return
        
        try:
            provider = provider_class(config)
            self.providers[config.name] = provider
            self.health_monitor.mark_provider_healthy(config.name)
            logger.info(f"Initialized provider: {config.name}")
        except Exception as e:
            logger.error(f"Failed to initialize provider {config.name}: {e}")
            self.health_monitor.mark_provider_unhealthy(config.name, e)
    
    async def generate_response(self, request: LLMRequest, conversation_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> LLMResponse:
        """Generate a response using the best available provider with failover and backoff."""
        if not self.providers:
            raise ProviderError("No providers available", "manager")
        
        # Get providers sorted by priority and health
        sorted_providers = await self._get_sorted_providers(request)
        
        if not sorted_providers:
            raise ProviderError("No healthy providers available", "manager")
        
        last_error = None
        
        for provider in sorted_providers:
            try:
                logger.info(f"Attempting to use provider: {provider.name}")
                
                # Use exponential backoff for this provider
                async def make_request():
                    response = await provider.generate_response(request)
                    # Mark provider as healthy on successful response
                    self.health_monitor.mark_provider_healthy(provider.name)
                    return response
                
                response = await self.backoff.execute_with_backoff(make_request)
                
                # Record usage for cost tracking if cost tracker is available
                if self.cost_tracker:
                    await self.cost_tracker.record_usage(response, conversation_id, user_id)
                
                logger.info(f"Successfully generated response using {provider.name}")
                return response
                
            except RateLimitError as e:
                logger.warning(f"Rate limit hit for {provider.name}: {e}")
                last_error = e
                self.health_monitor.mark_provider_unhealthy(provider.name, e)
                continue
                
            except AuthenticationError as e:
                logger.error(f"Authentication error for {provider.name}: {e}")
                last_error = e
                self.health_monitor.mark_provider_unhealthy(provider.name, e)
                continue
                
            except ModelUnavailableError as e:
                logger.warning(f"Model unavailable for {provider.name}: {e}")
                last_error = e
                # Don't mark as unhealthy for model unavailable - might be temporary
                continue
                
            except ProviderError as e:
                logger.error(f"Provider error for {provider.name}: {e}")
                last_error = e
                if not e.retryable:
                    self.health_monitor.mark_provider_unhealthy(provider.name, e)
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error for {provider.name}: {e}")
                last_error = ProviderError(str(e), provider.name, retryable=True)
                self.health_monitor.mark_provider_unhealthy(provider.name, last_error)
                continue
        
        # If we get here, all providers failed
        error_msg = f"All providers failed. Last error: {last_error}"
        raise ProviderError(error_msg, "manager")
    
    async def _get_sorted_providers(self, request: LLMRequest) -> List[LLMProvider]:
        """Get providers sorted by priority, health, and cost."""
        available_providers = []
        
        for provider in self.providers.values():
            if not provider.is_enabled:
                continue
            
            # Check if provider is healthy
            if not await self._is_provider_healthy(provider):
                continue
            
            # Check if provider has suitable models
            if not provider.get_best_model_for_request(request):
                continue
            
            available_providers.append(provider)
        
        # Sort by priority (lower number = higher priority), then by estimated cost
        def sort_key(provider: LLMProvider):
            priority = provider.priority
            
            # Estimate cost for this request
            model = provider.get_best_model_for_request(request)
            if model:
                # Rough estimation
                estimated_input_tokens = sum(len(msg.get("content", "")) for msg in request.messages) // 4
                estimated_output_tokens = min(request.max_tokens or 500, 500)
                cost = provider.calculate_cost(estimated_input_tokens, estimated_output_tokens, model)
            else:
                cost = float('inf')
            
            return (priority, cost)
        
        return sorted(available_providers, key=sort_key)
    
    async def _is_provider_healthy(self, provider: LLMProvider) -> bool:
        """Check if a provider is healthy, with caching and recovery attempts."""
        # Check if we should perform a health check
        if not self.health_monitor.should_check_health(provider.name):
            return self.health_monitor.is_provider_healthy(provider.name)
        
        # If provider is unhealthy, check if we should attempt recovery
        if not self.health_monitor.is_provider_healthy(provider.name):
            if not self.health_monitor.should_attempt_recovery(provider.name):
                return False
            
            # Increment recovery attempt counter
            self.health_monitor.increment_recovery_attempt(provider.name)
            logger.info(f"Attempting recovery for provider {provider.name}")
        
        # Perform health check
        try:
            is_healthy = await provider.is_available()
            if is_healthy:
                self.health_monitor.mark_provider_healthy(provider.name)
                logger.info(f"Provider {provider.name} health check passed")
            else:
                self.health_monitor.mark_provider_unhealthy(provider.name, 
                    Exception("Health check returned False"))
            return is_healthy
        except Exception as e:
            logger.warning(f"Health check failed for {provider.name}: {e}")
            self.health_monitor.mark_provider_unhealthy(provider.name, e)
            return False
    
    def get_provider_status(self) -> Dict[str, dict]:
        """Get status of all providers."""
        status = {}
        for name, provider in self.providers.items():
            status[name] = {
                "enabled": provider.is_enabled,
                "healthy": self.health_monitor.is_provider_healthy(name),
                "priority": provider.priority,
                "models": provider.get_available_models(),
                "last_health_check": self.health_monitor.last_health_check.get(name),
                "failure_count": self.health_monitor.get_failure_count(name),
                "recovery_attempts": self.health_monitor.recovery_attempts.get(name, 0)
            }
        return status
    
    def get_provider(self, name: str) -> Optional[LLMProvider]:
        """Get a specific provider by name."""
        return self.providers.get(name)
    
    def add_provider(self, config: ProviderConfig) -> None:
        """Add a new provider."""
        self._initialize_provider(config)
    
    def remove_provider(self, name: str) -> None:
        """Remove a provider."""
        if name in self.providers:
            del self.providers[name]
            # Clean up health monitor data
            if name in self.health_monitor.provider_health:
                del self.health_monitor.provider_health[name]
            if name in self.health_monitor.last_health_check:
                del self.health_monitor.last_health_check[name]
            if name in self.health_monitor.last_failure:
                del self.health_monitor.last_failure[name]
            if name in self.health_monitor.failure_count:
                del self.health_monitor.failure_count[name]
            if name in self.health_monitor.recovery_attempts:
                del self.health_monitor.recovery_attempts[name]
            logger.info(f"Removed provider: {name}")
    
    def enable_provider(self, name: str) -> None:
        """Enable a provider."""
        if name in self.providers:
            self.providers[name].config.enabled = True
            logger.info(f"Enabled provider: {name}")
    
    def disable_provider(self, name: str) -> None:
        """Disable a provider."""
        if name in self.providers:
            self.providers[name].config.enabled = False
            self.health_monitor.mark_provider_unhealthy(name, Exception("Provider manually disabled"))
            logger.info(f"Disabled provider: {name}")
    
    async def calculate_request_cost(self, request: LLMRequest) -> Dict[str, float]:
        """Calculate estimated cost for a request across all providers."""
        costs = {}
        
        # Rough estimation
        estimated_input_tokens = sum(len(msg.get("content", "")) for msg in request.messages) // 4
        estimated_output_tokens = min(request.max_tokens or 500, 500)
        
        for name, provider in self.providers.items():
            if not provider.is_enabled:
                continue
            
            model = provider.get_best_model_for_request(request)
            if model:
                cost = provider.calculate_cost(estimated_input_tokens, estimated_output_tokens, model)
                costs[name] = cost
        
        return costs
    
    async def get_cost_summary(self, start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None):
        """Get cost summary from the cost tracker."""
        if not self.cost_tracker:
            return None
        return await self.cost_tracker.get_usage_summary(start_date, end_date)
    
    async def get_daily_cost(self, date: Optional[datetime] = None) -> float:
        """Get daily cost from the cost tracker."""
        if not self.cost_tracker:
            return 0.0
        return await self.cost_tracker.get_daily_cost(date)
    
    async def get_monthly_cost(self, date: Optional[datetime] = None) -> float:
        """Get monthly cost from the cost tracker."""
        if not self.cost_tracker:
            return 0.0
        return await self.cost_tracker.get_monthly_cost(date)
    
    async def get_provider_efficiency(self):
        """Get provider efficiency metrics."""
        if not self.cost_tracker:
            return {}
        return await self.cost_tracker.get_provider_efficiency()
    
    async def check_cost_alerts(self, daily_limit: float = 10.0, 
                               monthly_limit: float = 100.0) -> List[str]:
        """Check for cost alerts."""
        if not self.cost_tracker:
            return []
        return await self.cost_tracker.check_cost_alerts(daily_limit, monthly_limit)
    
    async def get_cost_trends(self, days: int = 30) -> Dict[str, float]:
        """Get cost trends over time."""
        if not self.cost_tracker:
            return {}
        return await self.cost_tracker.get_cost_trends(days)