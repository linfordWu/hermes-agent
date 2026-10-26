import pytest

from agent.gemini_native_adapter import translate_gemini_response, translate_stream_event


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [("MAX_TOKENS", "length"), ("SAFETY", "content_filter")],
)
def test_non_stop_native_response_does_not_turn_function_call_into_tool_turn(finish_reason, expected):
    response = translate_gemini_response(
        {
            "candidates": [{
                "content": {"role": "model", "parts": [{
                    "functionCall": {"name": "write_file", "args": {"path": "x", "content": "y"}}
                }]},
                "finishReason": finish_reason,
            }]
        },
        model="gemini-2.5-flash",
    )

    choice = response.choices[0]
    assert choice.finish_reason == expected
    assert choice.message.tool_calls


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [("MAX_TOKENS", "length"), ("SAFETY", "content_filter")],
)
def test_non_stop_native_stream_event_preserves_finish_reason(finish_reason, expected):
    chunks = translate_stream_event(
        {
            "candidates": [{
                "content": {"role": "model", "parts": [{
                    "functionCall": {"name": "write_file", "args": {"path": "x", "content": "y"}}
                }]},
                "finishReason": finish_reason,
            }]
        },
        model="gemini-2.5-flash",
        tool_call_indices={},
    )

    assert chunks[-1].choices[0].finish_reason == expected


def test_stop_native_response_keeps_function_call_finish_reason():
    response = translate_gemini_response(
        {
            "candidates": [{
                "content": {"role": "model", "parts": [{
                    "functionCall": {"name": "write_file", "args": {"path": "x", "content": "y"}}
                }]},
                "finishReason": "STOP",
            }]
        },
        model="gemini-2.5-flash",
    )

    assert response.choices[0].finish_reason == "tool_calls"
