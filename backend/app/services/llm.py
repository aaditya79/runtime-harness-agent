"""LLM call factory.

The Streamlit app picks Anthropic if a key is present, then falls back to
OpenAI. We mirror that here so the existing nba_agent / nba_multi_agent /
nba_cot_baseline modules can be driven with the user's keys without touching
any of those files.
"""

from __future__ import annotations

from typing import Callable

from app.config import resolve_api_key


def get_llm_callable() -> tuple[Callable | None, str]:
    """Return (callable, label) where callable accepts a list[messages]."""
    anthropic_key = resolve_api_key("ANTHROPIC_API_KEY")
    if anthropic_key:
        def call_anthropic(messages):
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            system_msg = ""
            conv = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    conv.append(msg)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system_msg if system_msg else "You are an NBA betting analyst.",
                messages=conv,
            )
            return response.content[0].text

        return call_anthropic, "Claude Haiku 4.5"

    openai_key = resolve_api_key("OPENAI_API_KEY")
    if openai_key:
        def call_openai(messages):
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
            )
            return response.choices[0].message.content

        return call_openai, "GPT-4o"

    return None, "No model configured"
