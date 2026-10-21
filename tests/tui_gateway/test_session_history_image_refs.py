"""Persisted image directives are shared by the gateway and TUI gateway transcript paths."""

from agent.context_references import build_persist_message_with_image_refs
from tui_gateway import server


def test_build_persist_message_with_image_refs_without_images_returns_text():
    assert build_persist_message_with_image_refs("what is this?", []) == "what is this?"
    assert build_persist_message_with_image_refs("", []) == ""


def test_build_persist_message_with_image_refs_appends_existing_paths(tmp_path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"png")

    assert build_persist_message_with_image_refs("what is in this photo?", [str(image)]) == (
        f"what is in this photo?\n@image:{image}"
    )


def test_build_persist_message_with_image_refs_skips_missing_paths(tmp_path):
    existing = tmp_path / "a.png"
    existing.write_bytes(b"png")
    missing = str(tmp_path / "gone.png")

    assert build_persist_message_with_image_refs("compare them", [str(existing), missing]) == (
        f"compare them\n@image:{existing}"
    )


def test_build_persist_message_with_image_refs_without_text_is_refs_only(tmp_path):
    image = tmp_path / "only.png"
    image.write_bytes(b"png")

    assert build_persist_message_with_image_refs("", [str(image)]) == f"@image:{image}"


def test_build_persist_message_quotes_paths_containing_spaces(tmp_path):
    image_dir = tmp_path / "Application Support" / "Hermes" / "composer-images"
    image_dir.mkdir(parents=True)
    image = image_dir / "cat.png"
    image.write_bytes(b"png")

    assert build_persist_message_with_image_refs("what is this?", [str(image)]) == (
        f"what is this?\n@image:`{image}`"
    )


def test_persist_user_message_mirrors_the_shape_sent_to_the_model(tmp_path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"png")
    image_part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    native_parts = [{"type": "text", "text": "api-only text"}, image_part]

    override = server._build_persist_user_message("what is this?", [str(image)], native_parts)

    assert override == [{"type": "text", "text": f"what is this?\n@image:{image}"}, image_part]


def test_persist_user_message_stays_a_string_for_text_mode(tmp_path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"png")

    override = server._build_persist_user_message("what is this?", [str(image)], "enriched api-only text")

    assert override == f"what is this?\n@image:{image}"
