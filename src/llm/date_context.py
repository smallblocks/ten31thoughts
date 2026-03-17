"""
Ten31 Thoughts - Date Context Injection
Ensures every LLM prompt knows today's date and treats all database content as real.

The problem: LLMs with training cutoffs before 2025-2026 will treat references to
dates in that range as fictional or hypothetical. This module injects a reality
anchor into every system prompt.
"""

from datetime import datetime, timezone


def get_date_context() -> str:
    """
    Returns a date context string to prepend to every system prompt.
    This tells the LLM what today's date is and that all content is real.
    """
    now = datetime.now(timezone.utc)
    return (
        f"TODAY'S DATE: {now.strftime('%A, %B %d, %Y')} (UTC)\n"
        f"CURRENT YEAR: {now.year}\n"
        f"\n"
        f"CRITICAL: All content you are analyzing is REAL. It is not fictional, "
        f"hypothetical, or from a simulated scenario. Every transcript, newsletter, "
        f"date, price, event, and data point in the database reflects actual events "
        f"that have occurred or are occurring in the real world. Do NOT describe any "
        f"content as 'fictional,' 'hypothetical,' 'from a future scenario,' or "
        f"exhibiting 'temporal confusion.' If a transcript references a date that is "
        f"recent or current relative to today ({now.strftime('%Y-%m-%d')}), treat it "
        f"as a real event.\n"
        f"\n"
    )


def inject_date_context(system_prompt: str) -> str:
    """Prepend date context to any system prompt."""
    return get_date_context() + system_prompt
