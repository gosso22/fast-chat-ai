"""
Service for generating conversation titles from message content using LLM.
"""

import logging
import re
from typing import Optional

from .llm_providers.manager import LLMProviderManager
from .llm_providers.base import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

TITLE_PROMPT = (
    "Generate a concise title (3-6 words) for a conversation that starts with the following message. "
    "Return ONLY the title, no quotes, no punctuation at the end, no explanation."
)


def _clean_title(raw: str) -> str:
    """Clean LLM output to a usable title."""
    title = raw.strip().strip('"\'').strip()
    # Remove trailing punctuation
    title = re.sub(r'[.!?]+$', '', title)
    # Collapse whitespace
    title = ' '.join(title.split())
    # Cap length
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def _fallback_title(message: str) -> str:
    """Generate a simple title by truncating the first message."""
    clean = ' '.join(message.split())
    if len(clean) <= 50:
        return clean
    return clean[:47] + "..."


async def generate_title(
    message: str,
    llm_manager: LLMProviderManager,
) -> str:
    """
    Generate a short conversation title from the first user message.

    Uses a lightweight LLM call with low temperature and token limits.
    Falls back to message truncation if the LLM call fails.
    """
    try:
        request = LLMRequest(
            messages=[
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user", "content": message[:500]},  # limit input size
            ],
            max_tokens=30,
            temperature=0.3,
        )

        response: LLMResponse = await llm_manager.generate_response(request)
        title = _clean_title(response.content)

        if not title:
            logger.warning("LLM returned empty title, using fallback")
            return _fallback_title(message)

        logger.info(f"Generated conversation title: {title}")
        return title

    except Exception as e:
        logger.warning(f"Title generation failed, using fallback: {e}")
        return _fallback_title(message)
