"""Structured-output kwargs must survive the auxiliary Codex Responses adapter."""

from types import SimpleNamespace

import pytest

from agent.auxiliary_client import _CodexCompletionsAdapter


def _adapter():
    return _CodexCompletionsAdapter(
        SimpleNamespace(base_url="https://chatgpt.com/backend-api/codex/"), "gpt-5.6-codex"
    )


def _json_schema(name="reply"):
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "description": "A constrained response",
            "schema": {
                "type": "object",
                "properties": {"word": {"type": "string", "enum": ["PONG"]}},
                "required": ["word"],
                "additionalProperties": False,
            },
        },
    }


@pytest.mark.parametrize("location", ["extra_body", "top_level"])
def test_codex_aux_maps_json_schema_to_responses_text_format(location):
    response_format = _json_schema()
    kwargs = {"messages": [{"role": "user", "content": "say pong"}]}
    if location == "extra_body":
        kwargs["extra_body"] = {"response_format": response_format}
    else:
        kwargs["response_format"] = response_format

    built, _, _ = _adapter()._build_responses_kwargs(kwargs)

    assert built["text"]["format"] == {
        "type": "json_schema",
        "name": "reply",
        "strict": True,
        "description": "A constrained response",
        "schema": response_format["json_schema"]["schema"],
    }
    assert "response_format" not in built


def test_codex_aux_extra_body_response_format_overrides_top_level():
    kwargs = {
        "messages": [{"role": "user", "content": "say pong"}],
        "response_format": _json_schema("top_level"),
        "extra_body": {"response_format": _json_schema("extra_body")},
    }

    built, _, _ = _adapter()._build_responses_kwargs(kwargs)

    assert built["text"]["format"]["name"] == "extra_body"


def test_codex_aux_maps_json_object_mode():
    built, _, _ = _adapter()._build_responses_kwargs({
        "messages": [{"role": "user", "content": "return JSON"}],
        "extra_body": {"response_format": {"type": "json_object"}},
    })

    assert built["text"]["format"] == {"type": "json_object"}


def test_codex_aux_ignores_unrecognized_response_format():
    built, _, _ = _adapter()._build_responses_kwargs({
        "messages": [{"role": "user", "content": "hello"}],
        "extra_body": {"response_format": {"type": "unsupported"}},
    })

    assert "text" not in built
