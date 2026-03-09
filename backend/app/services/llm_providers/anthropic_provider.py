"""
Anthropic LLM Provider implementation.
"""

from typing import List, Optional
import anthropic
from anthropic import AsyncAnthropic

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


class AnthropicProvider(LLMProvider):
    """Anthropic LLM provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout
        )
        
        # Default Anthropic models with current pricing (as of 2024)
        if not config.models:
            self.config.models = self._get_default_models()
    
    def _get_default_models(self) -> List[ModelConfig]:
        """Get default Anthropic model configurations."""
        return [
            ModelConfig(
                name="claude-3-5-sonnet-20241022",
                input_cost_per_1k_tokens=0.003,
                output_cost_per_1k_tokens=0.015,
                max_tokens=8192,
                context_window=200000,
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.CODE]
            ),
            ModelConfig(
                name="claude-3-5-haiku-20241022",
                input_cost_per_1k_tokens=0.001,
                output_cost_per_1k_tokens=0.005,
                max_tokens=8192,
                context_window=200000,
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.CODE]
            ),
            ModelConfig(
                name="claude-3-opus-20240229",
                input_cost_per_1k_tokens=0.015,
                output_cost_per_1k_tokens=0.075,
                max_tokens=4096,
                context_window=200000,
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.CODE]
            ),
            ModelConfig(
                name="claude-3-sonnet-20240229",
                input_cost_per_1k_tokens=0.003,
                output_cost_per_1k_tokens=0.015,
                max_tokens=4096,
                context_window=200000,
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION]
            ),
            ModelConfig(
                name="claude-3-haiku-20240307",
                input_cost_per_1k_tokens=0.00025,
                output_cost_per_1k_tokens=0.00125,
                max_tokens=4096,
                context_window=200000,
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION]
            )
        ]
    
    def _convert_messages(self, messages: List[dict]) -> tuple[str, List[dict]]:
        """Convert OpenAI format messages to Anthropic format."""
        system_message = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                system_message = content
            elif role in ["user", "assistant"]:
                anthropic_messages.append({
                    "role": role,
                    "content": content
                })
        
        return system_message, anthropic_messages
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a response using Anthropic."""
        model = self.get_best_model_for_request(request)
        if not model:
            raise ModelUnavailableError("No suitable model available", self.name, "")
        
        try:
            system_message, anthropic_messages = self._convert_messages(request.messages)
            
            kwargs = {
                "model": model,
                "messages": anthropic_messages,
                "max_tokens": request.max_tokens or 1024,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": request.stream
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            response = await self.client.messages.create(**kwargs)
            
            if request.stream:
                # Handle streaming response
                content = ""
                async for chunk in response:
                    if chunk.type == "content_block_delta":
                        content += chunk.delta.text
                
                # For streaming, we need to estimate tokens
                input_tokens = self._estimate_tokens(request.messages)
                output_tokens = self._estimate_tokens([{"content": content}])
            else:
                content = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens if response.usage else 0
                output_tokens = response.usage.output_tokens if response.usage else 0
            
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
                    "stop_reason": response.stop_reason if not request.stream else "end_turn"
                }
            )
            
        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e), self.name)
        except anthropic.AuthenticationError as e:
            raise AuthenticationError(str(e), self.name)
        except anthropic.NotFoundError as e:
            raise ModelUnavailableError(str(e), self.name, model)
        except Exception as e:
            raise ProviderError(f"Anthropic API error: {str(e)}", self.name, retryable=True)
    
    async def generate_response_stream(self, request: LLMRequest) -> "AsyncIterator[str]":
        """Stream response tokens from Anthropic."""
        from typing import AsyncIterator

        model = self.get_best_model_for_request(request)
        if not model:
            raise ModelUnavailableError("No suitable model available", self.name, "")

        try:
            system_message, anthropic_messages = self._convert_messages(request.messages)

            kwargs = {
                "model": model,
                "messages": anthropic_messages,
                "max_tokens": request.max_tokens or 1024,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
            }

            if system_message:
                kwargs["system"] = system_message

            response = await self.client.messages.create(**kwargs)

            async for chunk in response:
                if chunk.type == "content_block_delta":
                    yield chunk.delta.text

        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e), self.name)
        except anthropic.AuthenticationError as e:
            raise AuthenticationError(str(e), self.name)
        except anthropic.NotFoundError as e:
            raise ModelUnavailableError(str(e), self.name, model)
        except Exception as e:
            raise ProviderError(f"Anthropic streaming error: {str(e)}", self.name, retryable=True)

    async def is_available(self) -> bool:
        """Check if Anthropic is available."""
        try:
            # Simple test to check availability
            await self.client.messages.create(
                model="claude-3-haiku-20240307",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1
            )
            return True
        except anthropic.AuthenticationError:
            return False
        except Exception:
            # Other errors might be temporary
            return True
    
    def get_available_models(self) -> List[str]:
        """Get list of available Anthropic model names."""
        return [model.name for model in self.config.models]
    
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a specific Anthropic model."""
        for model in self.config.models:
            if model.name == model_name:
                return model
        return None
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """Calculate cost for Anthropic token usage."""
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