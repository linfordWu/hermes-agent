"""Warning output should only use ANSI color when stderr supports it."""

import io
from types import SimpleNamespace


class _TTYStream(io.StringIO):
    def isatty(self):
        return True


def _prepare_warnings(monkeypatch):
    from hermes_cli import config
    import hermes_constants

    monkeypatch.setattr(
        config,
        "validate_config_structure",
        lambda _config: [SimpleNamespace(severity="warning", message="bad config")],
    )
    monkeypatch.setattr(config, "load_env", lambda: {"MESSAGING_CWD": "/tmp/project"})
    monkeypatch.setattr(hermes_constants, "display_hermes_home", lambda: "/tmp/home")
    return config


def test_config_and_deprecation_warnings_are_plain_on_non_tty_stderr(monkeypatch):
    config = _prepare_warnings(monkeypatch)
    stream = io.StringIO()
    monkeypatch.setattr(config.sys, "stderr", stream)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    config.print_config_warnings({})
    config.warn_deprecated_cwd_env_vars()

    output = stream.getvalue()
    assert "bad config" in output
    assert "MESSAGING_CWD=/tmp/project" in output
    assert "\x1b[" not in output


def test_config_warnings_keep_color_on_tty(monkeypatch):
    config = _prepare_warnings(monkeypatch)
    stream = _TTYStream()
    monkeypatch.setattr(config.sys, "stderr", stream)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    config.print_config_warnings({})

    assert "\x1b[33m" in stream.getvalue()


def test_no_color_disables_stderr_color_even_on_tty(monkeypatch):
    config = _prepare_warnings(monkeypatch)
    stream = _TTYStream()
    monkeypatch.setattr(config.sys, "stderr", stream)
    monkeypatch.setenv("NO_COLOR", "")

    config.print_config_warnings({})

    assert "\x1b[" not in stream.getvalue()
