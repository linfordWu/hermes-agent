import pytest

from agent.anthropic_adapter import _is_stream_unavailable_error, _is_stream_unsupported_error


@pytest.mark.parametrize("message", [
    "Incomplete upstream response: upstream said adaptive thinking is not supported on this model",
    "For 'integer' type, properties maximum, minimum are not supported",
    "Native history replay not supported: native stderr: Error: --input-format stream-json",
])
def test_unrelated_unsupported_error_does_not_disable_streaming(message):
    error = RuntimeError(message)

    assert not _is_stream_unsupported_error(error)
    assert not _is_stream_unavailable_error(error)


@pytest.mark.parametrize("message", [
    "Streaming is not supported for this model",
    "stream not supported for this provider",
    "Stream mode is not supported",
])
def test_explicit_stream_unsupported_error_is_still_recognized(message):
    error = RuntimeError(message)

    assert _is_stream_unsupported_error(error)
    assert _is_stream_unavailable_error(error)
