"""
OpenAI LLM Provider implementation.
"""

import asyncio
from typing import List, Optional
import openai
from openai import AsyncOpenAI

from .base import (
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


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout
        )
        
        # Default OpenAI models with current pricing (as of 2024)
        if not config.models:
            self.config.models = self._get_default_models()
    
    def _get_default_models(self) -> List[ModelConfig]:
        """Get default OpenAI model configurations."""
        return [
            ModelConfig(
                name="gpt-4o",
                input_cost_per_1k_tokens=0.005,
                output_cost_per_1k_tokens=0.015,
                max_tokens=4096,
                context_window=128000,
                capabilities=[ModelCapability.CHAT, ModelCapability.FUNCTION_CALLING, ModelCapability.VISION]
            ),
            ModelConfig(
                name="gpt-4o-mini",
                input_cost_per_1k_tokens=0.00015,
                output_cost_per_1k_tokens=0.0006,
                max_tokens=16384,
                context_window=128000,
                capabilities=[ModelCapability.CHAT, ModelCapability.FUNCTION_CALLING, ModelCapability.VISION]
            ),
            ModelConfig(
                name="gpt-4-turbo",
                input_cost_per_1k_tokens=0.01,
                output_cost_per_1k_tokens=0.03,
                max_tokens=4096,
                context_window=128000,
                capabilities=[ModelCapability.CHAT, ModelCapability.FUNCTION_CALLING, ModelCapability.VISION]
            ),
            ModelConfig(
                name="gpt-3.5-turbo",
                input_cost_per_1k_tokens=0.0005,
                output_cost_per_1k_tokens=0.0015,
                max_tokens=4096,
                context_window=16385,
                capabilities=[ModelCapability.CHAT, ModelCapability.FUNCTION_CALLING]
            )
        ]
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a response using OpenAI."""
        model = self.get_best_model_for_request(request)
        if not model:
            raise ModelUnavailableError("No suitable model available", self.name, "")
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=request.messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stream=request.stream
            )
            
            if request.stream:
                # Handle streaming response
                content = ""
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        content += chunk.choices[0].delta.content
                
                # For streaming, we need to estimate tokens
                input_tokens = self._estimate_tokens(request.messages)
                output_tokens = self._estimate_tokens([{"content": content}])
            else:
                content = response.choices[0].message.content or ""
                input_tokens = response.usage.prompt_tokens if response.usage else 0
                output_tokens = response.usage.completion_tokens if response.usage else 0
            
            total_tokens = input_tokens + output_tokens
            cost = self.calculate_cost(input_tokens, output_tokens, model)
            
            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost,
                provider=self.name,
                model=model,
                metadata={
                    "finish_reason": response.choices[0].finish_reason if not request.stream else "stop"
                }
            )
            
        except openai.RateLimitError as e:
            retry_after = getattr(e, 'retry_after', None)
            raise RateLimitError(str(e), self.name, retry_after)
        except openai.AuthenticationError as e:
            raise AuthenticationError(str(e), self.name)
        except openai.NotFoundError as e:
            raise ModelUnavailableError(str(e), self.name, model)
        except Exception as e:
            raise ProviderError(f"OpenAI API error: {str(e)}", self.name, retryable=True)
    
    async def is_available(self) -> bool:
        """Check if OpenAI is available."""
        try:
            # Simple test request to check availability
            await self.client.models.list()
            return True
        except Exception:
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available OpenAI model names."""
        return [model.name for model in self.config.models]
    
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a specific OpenAI model."""
        for model in self.config.models:
            if model.name == model_name:
                return model
        return None
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """Calculate cost for OpenAI token usage."""
        model_config = self.get_model_config(model_name)
        if not model_config:
            return 0.0
        
        input_cost = (input_tokens / 1000) * model_config.input_cost_per_1k_tokens
        output_cost = (output_tokens / 1000) * model_config.output_cost_per_1k_tokens
        
        return input_cost + output_cost
    
    def _estimate_tokens(self, messages: List[dict]) -> int:
        """Rough estimation of tokens for streaming responses."""
        # Simple estimation: ~4 characters per token
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4