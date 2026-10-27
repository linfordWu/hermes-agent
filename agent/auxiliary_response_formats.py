"""Structured-output translation for the auxiliary Codex Responses adapter."""

from typing import Any


def _translate_anthropic_response_format(anthropic_kwargs: dict[str, Any], response_format: Any) -> None:
    """Merge an OpenAI response format into Anthropic ``output_config``."""
    if not isinstance(response_format, dict):
        return
    format_type = response_format.get("type")
    if format_type == "json_schema":
        json_schema = response_format.get("json_schema")
        if not isinstance(json_schema, dict) or "schema" not in json_schema:
            return
        schema = json_schema["schema"]
    elif format_type == "json_object":
        # Anthropic SDK has no schema-less JSON mode; only ``json_schema``.
        schema = {"type": "object"}
    else:
        return
    output_config = anthropic_kwargs.get("output_config")
    if not isinstance(output_config, dict):
        output_config = {}
        anthropic_kwargs["output_config"] = output_config
    output_config["format"] = {"type": "json_schema", "schema": schema}


def apply_codex_aux_response_format(
    responses_kwargs: dict[str, Any], top_level: Any, extra_body: Any,
) -> None:
    """Translate Chat Completions ``response_format`` into Responses ``text.format``.

    The extra-body value takes precedence when both input shapes are present. Unsupported
    formats are left alone to preserve the adapter's existing behavior for unknown values.
    """
    text_format = _responses_text_format(top_level)
    if isinstance(extra_body, dict):
        text_format = _responses_text_format(extra_body.get("response_format")) or text_format
    if text_format is not None:
        responses_kwargs["text"] = {**(responses_kwargs.get("text") or {}), "format": text_format}


def _responses_text_format(response_format: Any) -> dict[str, Any] | None:
    """Build the Responses format payload from a Chat Completions format object."""
    if not isinstance(response_format, dict):
        return None
    format_type = response_format.get("type")
    if format_type == "json_object":
        return {"type": "json_object"}
    if format_type != "json_schema":
        return None
    schema_config = response_format.get("json_schema")
    if not isinstance(schema_config, dict):
        return None
    name = schema_config.get("name")
    schema = schema_config.get("schema")
    if not isinstance(name, str) or not name or not isinstance(schema, dict):
        return None
    result: dict[str, Any] = {"type": "json_schema", "name": name, "schema": schema}
    description = schema_config.get("description")
    if isinstance(description, str):
        result["description"] = description
    strict = schema_config.get("strict")
    if isinstance(strict, bool):
        result["strict"] = strict
    return result
