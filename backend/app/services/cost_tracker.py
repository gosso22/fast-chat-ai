"""
Cost tracking and monitoring service for LLM usage.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict
import logging

from app.services.llm_providers.base import LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """Record of LLM usage."""
    timestamp: datetime
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class UsageSummary:
    """Summary of usage statistics."""
    total_requests: int
    total_tokens: int
    total_cost: float
    provider_breakdown: Dict[str, Dict[str, float]]  # provider -> {tokens, cost, requests}
    model_breakdown: Dict[str, Dict[str, float]]     # model -> {tokens, cost, requests}
    time_period: str


class CostTracker:
    """Service for tracking and monitoring LLM costs."""
    
    def __init__(self):
        self.usage_records: List[UsageRecord] = []
        self.daily_costs: Dict[str, float] = defaultdict(float)  # date -> cost
        self.monthly_costs: Dict[str, float] = defaultdict(float)  # month -> cost
        self.provider_costs: Dict[str, float] = defaultdict(float)  # provider -> cost
        self.model_costs: Dict[str, float] = defaultdict(float)  # model -> cost
        self._lock = asyncio.Lock()
    
    async def record_usage(self, response: LLMResponse, conversation_id: Optional[str] = None, 
                          user_id: Optional[str] = None) -> None:
        """Record usage from an LLM response."""
        async with self._lock:
            record = UsageRecord(
                timestamp=response.timestamp,
                provider=response.provider,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=response.total_tokens,
                cost=response.cost,
                conversation_id=conversation_id,
                user_id=user_id
            )
            
            self.usage_records.append(record)
            
            # Update aggregated costs
            date_key = response.timestamp.strftime("%Y-%m-%d")
            month_key = response.timestamp.strftime("%Y-%m")
            
            self.daily_costs[date_key] += response.cost
            self.monthly_costs[month_key] += response.cost
            self.provider_costs[response.provider] += response.cost
            self.model_costs[response.model] += response.cost
            
            logger.info(f"Recorded usage: {response.provider}/{response.model} - "
                       f"${response.cost:.6f} ({response.total_tokens} tokens)")
    
    async def get_daily_cost(self, date: Optional[datetime] = None) -> float:
        """Get total cost for a specific date."""
        if date is None:
            date = datetime.utcnow()
        
        date_key = date.strftime("%Y-%m-%d")
        return self.daily_costs.get(date_key, 0.0)
    
    async def get_monthly_cost(self, date: Optional[datetime] = None) -> float:
        """Get total cost for a specific month."""
        if date is None:
            date = datetime.utcnow()
        
        month_key = date.strftime("%Y-%m")
        return self.monthly_costs.get(month_key, 0.0)
    
    async def get_provider_costs(self) -> Dict[str, float]:
        """Get costs broken down by provider."""
        return dict(self.provider_costs)
    
    async def get_model_costs(self) -> Dict[str, float]:
        """Get costs broken down by model."""
        return dict(self.model_costs)
    
    async def get_usage_summary(self, start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> UsageSummary:
        """Get usage summary for a time period."""
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=30)  # Default to last 30 days
        
        # Filter records by date range
        filtered_records = [
            record for record in self.usage_records
            if start_date <= record.timestamp <= end_date
        ]
        
        if not filtered_records:
            return UsageSummary(
                total_requests=0,
                total_tokens=0,
                total_cost=0.0,
                provider_breakdown={},
                model_breakdown={},
                time_period=f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            )
        
        # Calculate totals
        total_requests = len(filtered_records)
        total_tokens = sum(record.total_tokens for record in filtered_records)
        total_cost = sum(record.cost for record in filtered_records)
        
        # Provider breakdown
        provider_breakdown = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "requests": 0})
        for record in filtered_records:
            provider_breakdown[record.provider]["tokens"] += record.total_tokens
            provider_breakdown[record.provider]["cost"] += record.cost
            provider_breakdown[record.provider]["requests"] += 1
        
        # Model breakdown
        model_breakdown = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "requests": 0})
        for record in filtered_records:
            model_breakdown[record.model]["tokens"] += record.total_tokens
            model_breakdown[record.model]["cost"] += record.cost
            model_breakdown[record.model]["requests"] += 1
        
        return UsageSummary(
            total_requests=total_requests,
            total_tokens=total_tokens,
            total_cost=total_cost,
            provider_breakdown=dict(provider_breakdown),
            model_breakdown=dict(model_breakdown),
            time_period=f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )
    
    async def get_cost_trends(self, days: int = 30) -> Dict[str, float]:
        """Get daily cost trends for the last N days."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        trends = {}
        current_date = start_date
        
        while current_date <= end_date:
            date_key = current_date.strftime("%Y-%m-%d")
            trends[date_key] = self.daily_costs.get(date_key, 0.0)
            current_date += timedelta(days=1)
        
        return trends
    
    async def check_cost_alerts(self, daily_limit: float = 10.0, 
                               monthly_limit: float = 100.0) -> List[str]:
        """Check for cost alerts and return warning messages."""
        alerts = []
        
        today_cost = await self.get_daily_cost()
        if today_cost >= daily_limit:
            alerts.append(f"Daily cost limit exceeded: ${today_cost:.2f} >= ${daily_limit:.2f}")
        elif today_cost >= daily_limit * 0.8:
            alerts.append(f"Daily cost warning: ${today_cost:.2f} (80% of ${daily_limit:.2f} limit)")
        
        monthly_cost = await self.get_monthly_cost()
        if monthly_cost >= monthly_limit:
            alerts.append(f"Monthly cost limit exceeded: ${monthly_cost:.2f} >= ${monthly_limit:.2f}")
        elif monthly_cost >= monthly_limit * 0.8:
            alerts.append(f"Monthly cost warning: ${monthly_cost:.2f} (80% of ${monthly_limit:.2f} limit)")
        
        return alerts
    
    async def get_most_expensive_requests(self, limit: int = 10) -> List[UsageRecord]:
        """Get the most expensive requests."""
        sorted_records = sorted(self.usage_records, key=lambda r: r.cost, reverse=True)
        return sorted_records[:limit]
    
    async def get_provider_efficiency(self) -> Dict[str, Dict[str, float]]:
        """Get efficiency metrics for each provider (cost per token)."""
        efficiency = {}
        
        for provider in self.provider_costs.keys():
            provider_records = [r for r in self.usage_records if r.provider == provider]
            if not provider_records:
                continue
            
            total_tokens = sum(r.total_tokens for r in provider_records)
            total_cost = sum(r.cost for r in provider_records)
            avg_cost_per_token = total_cost / total_tokens if total_tokens > 0 else 0
            
            efficiency[provider] = {
                "cost_per_token": avg_cost_per_token,
                "total_requests": len(provider_records),
                "total_tokens": total_tokens,
                "total_cost": total_cost
            }
        
        return efficiency
    
    async def clear_old_records(self, days_to_keep: int = 90) -> int:
        """Clear old usage records to manage memory."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        async with self._lock:
            old_count = len(self.usage_records)
            self.usage_records = [
                record for record in self.usage_records 
                if record.timestamp >= cutoff_date
            ]
            new_count = len(self.usage_records)
            removed_count = old_count - new_count
            
            if removed_count > 0:
                logger.info(f"Cleared {removed_count} old usage records")
            
            return removed_count


# Global cost tracker instance
cost_tracker = CostTracker()