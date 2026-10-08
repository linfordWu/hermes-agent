"""Disabled reasoning uses each Gemini family’s supported request vocabulary.

``includeThoughts: False`` only hides thought parts; the model still reasons
internally and bills thought tokens against maxOutputTokens, starving small
budgets (title generation's 64 tokens). Gemini 2.5 uses ``thinkingBudget: 0``;
Gemini 3 uses its lowest supported ``thinkingLevel`` instead of deprecated
numeric budgets.
"""

import pytest

from agent.transports.chat_completions import (
    _build_gemini_thinking_config,
    _snake_case_gemini_thinking_config,
)


@pytest.mark.parametrize(
    "model,expected_config",
    [
        ("gemini-2.5-flash", {"thinkingBudget": 0}),
        ("gemini-3.6-flash", {"thinkingLevel": "minimal"}),
        ("gemini-3.1-flash-lite", {"thinkingLevel": "minimal"}),
        ("gemini-3.8-flash", {"thinkingLevel": "low"}),
        ("gemini-3.7-flash", {"thinkingLevel": "low"}),
        ("gemini-3.1-pro", {"thinkingLevel": "low"}),
        ("gemini-flash-latest", {"thinkingLevel": "low"}),
        ("gemini-1.5-flash", {}),  # pre-2.5: neither field is documented
    ],
)
def test_disabled_reasoning_uses_family_supported_config(model, expected_config):
    for reasoning in ({"enabled": False}, {"effort": "none"}):
        config = _build_gemini_thinking_config(model, reasoning)
        assert config == {"includeThoughts": False, **expected_config}


def test_enabled_reasoning_never_zeroes_budget_and_non_gemini_gets_nothing():
    # Enabled reasoning must not be silently strangled by a zero budget.
    for reasoning in ({"enabled": True}, {"effort": "medium"}):
        config = _build_gemini_thinking_config("gemini-2.5-flash", reasoning)
        assert config is not None
        assert config.get("includeThoughts") is True
        assert "thinkingBudget" not in config
    # Non-Gemini models on the same provider 400 on the field entirely (#17426).
    assert _build_gemini_thinking_config("gpt-4o", {"enabled": False}) is None
    assert _build_gemini_thinking_config("gemma-2b", {"enabled": False}) is None


def test_snake_case_translation_carries_thinking_budget():
    translated = _snake_case_gemini_thinking_config({"includeThoughts": False, "thinkingBudget": 0})
    assert translated == {"include_thoughts": False, "thinking_budget": 0}
    translated = _snake_case_gemini_thinking_config({"includeThoughts": False})
    assert translated == {"include_thoughts": False}
    translated = _snake_case_gemini_thinking_config({"includeThoughts": False, "thinkingLevel": "low"})
    assert translated == {"include_thoughts": False, "thinking_level": "low"}
