"""
Google AI LLM Provider implementation.
"""

from typing import List, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

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


class GoogleProvider(LLMProvider):
    """Google AI LLM provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        genai.configure(api_key=config.api_key)
        
        # Default Google AI models with current pricing (as of 2024)
        if not config.models:
            self.config.models = self._get_default_models()
    
    def _get_default_models(self) -> List[ModelConfig]:
        """Get default Google AI model configurations."""
        return [
            ModelConfig(
                name="gemini-1.5-pro",
                input_cost_per_1k_tokens=0.00125,
                output_cost_per_1k_tokens=0.005,
                max_tokens=8192,
                context_window=2000000,  # 2M tokens
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.CODE]
            ),
            ModelConfig(
                name="gemini-1.5-flash",
                input_cost_per_1k_tokens=0.000075,
                output_cost_per_1k_tokens=0.0003,
                max_tokens=8192,
                context_window=1000000,  # 1M tokens
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.CODE]
            ),
            ModelConfig(
                name="gemini-1.0-pro",
                input_cost_per_1k_tokens=0.0005,
                output_cost_per_1k_tokens=0.0015,
                max_tokens=2048,
                context_window=30720,
                capabilities=[ModelCapability.CHAT, ModelCapability.CODE]
            )
        ]
    
    def _convert_messages(self, messages: List[dict]) -> List[dict]:
        """Convert OpenAI format messages to Google AI format."""
        google_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Google AI uses "user" and "model" roles
            if role == "user":
                google_messages.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                google_messages.append({"role": "model", "parts": [content]})
            elif role == "system":
                # System messages are typically prepended to the first user message
                if google_messages and google_messages[0]["role"] == "user":
                    google_messages[0]["parts"][0] = f"{content}\n\n{google_messages[0]['parts'][0]}"
                else:
                    google_messages.insert(0, {"role": "user", "parts": [content]})
        
        return google_messages
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        """Generate a response using Google AI."""
        model_name = self.get_best_model_for_request(request)
        if not model_name:
            raise ModelUnavailableError("No suitable model available", self.name, "")
        
        try:
            model = genai.GenerativeModel(model_name)
            google_messages = self._convert_messages(request.messages)
            
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
            )
            
            # Configure safety settings (less restrictive for general use)
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
            
            if request.stream:
                # Handle streaming response
                response = await model.generate_content_async(
                    google_messages,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                    stream=True
                )
                
                content = ""
                async for chunk in response:
                    if chunk.text:
                        content += chunk.text
                
                # For streaming, we need to estimate tokens
                input_tokens = self._estimate_tokens(request.messages)
                output_tokens = self._estimate_tokens([{"content": content}])
            else:
                response = await model.generate_content_async(
                    google_messages,
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
                
                content = response.text if response.text else ""
                
                # Google AI provides token counts
                input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
                output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            
            total_tokens = input_tokens + output_tokens
            cost = self.calculate_cost(input_tokens, output_tokens, model_name)
            
            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost,
                provider=self.name,
                model=model_name,
                metadata={
                    "finish_reason": response.candidates[0].finish_reason.name if not request.stream and response.candidates else "STOP"
                }
            )
            
        except Exception as e:
            error_str = str(e).lower()
            
            if "quota" in error_str or "rate limit" in error_str:
                raise RateLimitError(str(e), self.name)
            elif "api key" in error_str or "authentication" in error_str:
                raise AuthenticationError(str(e), self.name)
            elif "not found" in error_str or "model" in error_str:
                raise ModelUnavailableError(str(e), self.name, model_name)
            else:
                raise ProviderError(f"Google AI API error: {str(e)}", self.name, retryable=True)
    
    async def is_available(self) -> bool:
        """Check if Google AI is available."""
        try:
            # Simple test to check availability
            model = genai.GenerativeModel("gemini-1.0-pro")
            response = await model.generate_content_async("Hi", 
                generation_config=genai.types.GenerationConfig(max_output_tokens=1))
            return True
        except Exception:
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available Google AI model names."""
        return [model.name for model in self.config.models]
    
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a specific Google AI model."""
        for model in self.config.models:
            if model.name == model_name:
                return model
        return None
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """Calculate cost for Google AI token usage."""
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