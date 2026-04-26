"""Prompt loading and formatting utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def get_news_system(prompts: dict[str, str]) -> str:
    """Render the news agent system prompt with today's date and cutoff."""
    now_utc = datetime.now(timezone.utc)
    today_s = now_utc.strftime("%Y-%m-%d")
    cutoff_s = (now_utc - timedelta(days=30)).strftime("%Y-%m-%d")
    template = prompts.get("news_system", "")
    return template.format(today_s=today_s, cutoff_s=cutoff_s)


def get_news_cutoff_date() -> str:
    now_utc = datetime.now(timezone.utc)
    return (now_utc - timedelta(days=30)).strftime("%Y-%m-%d")


def get_base_rate_system(prompts: dict[str, str]) -> str:
    return prompts.get("baserate_system", "")


def get_bull_debate_system(prompts: dict[str, str]) -> str:
    s = (prompts.get("bull_debate_system") or "").strip()
    if s:
        return s
    return (prompts.get("bull_r1_system") or "").strip()


def get_bear_debate_system(prompts: dict[str, str]) -> str:
    s = (prompts.get("bear_debate_system") or "").strip()
    if s:
        return s
    return (prompts.get("bear_r1_system") or "").strip()


def get_judge_system(prompts: dict[str, str]) -> str:
    return prompts.get("judge_system", "")


def get_triage_system(prompts: dict[str, str]) -> str:
    return prompts.get("triage_system", "")


def get_simple_agent_system(prompts: dict[str, str]) -> str:
    return prompts.get("simple_agent_system", "")
