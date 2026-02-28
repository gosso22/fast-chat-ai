"""
Factory for creating LLM provider instances from configuration.
"""

from typing import List
import logging

from app.core.config import settings
from .base import ProviderConfig
from .manager import LLMProviderManager

logger = logging.getLogger(__name__)


def create_provider_configs() -> List[ProviderConfig]:
    """Create provider configurations from application settings."""
    configs = []
    
    # OpenAI Provider
    if settings.OPENAI_API_KEY and settings.OPENAI_ENABLED:
        configs.append(ProviderConfig(
            name="openai",
            api_key=settings.OPENAI_API_KEY,
            models=[],  # Will use default models from provider
            enabled=settings.OPENAI_ENABLED,
            priority=settings.OPENAI_PRIORITY
        ))
        logger.info("Configured OpenAI provider")
    else:
        logger.warning("OpenAI provider not configured (missing API key or disabled)")
    
    # Anthropic Provider
    if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_ENABLED:
        configs.append(ProviderConfig(
            name="anthropic",
            api_key=settings.ANTHROPIC_API_KEY,
            models=[],  # Will use default models from provider
            enabled=settings.ANTHROPIC_ENABLED,
            priority=settings.ANTHROPIC_PRIORITY
        ))
        logger.info("Configured Anthropic provider")
    else:
        logger.warning("Anthropic provider not configured (missing API key or disabled)")
    
    # Google AI Provider
    if settings.GOOGLE_API_KEY and settings.GOOGLE_ENABLED:
        configs.append(ProviderConfig(
            name="google",
            api_key=settings.GOOGLE_API_KEY,
            models=[],  # Will use default models from provider
            enabled=settings.GOOGLE_ENABLED,
            priority=settings.GOOGLE_PRIORITY
        ))
        logger.info("Configured Google AI provider")
    else:
        logger.warning("Google AI provider not configured (missing API key or disabled)")
    
    if not configs:
        logger.error("No LLM providers configured! Please set API keys and enable providers.")
    
    return configs


def create_llm_manager() -> LLMProviderManager:
    """Create and initialize the LLM provider manager."""
    configs = create_provider_configs()
    
    # Import cost_tracker here to avoid circular imports
    from ..cost_tracker import cost_tracker
    
    manager = LLMProviderManager(configs, cost_tracker)
    
    logger.info(f"Initialized LLM manager with {len(manager.providers)} providers")
    
    return manager


# Global instance - will be initialized when the module is imported
llm_manager: LLMProviderManager = None


def get_llm_manager() -> LLMProviderManager:
    """Get the global LLM manager instance."""
    global llm_manager
    if llm_manager is None:
        llm_manager = create_llm_manager()
    return llm_manager


def reset_llm_manager() -> None:
    """Reset the global LLM manager instance (useful for testing)."""
    global llm_manager
    llm_manager = None