"""Command-line identity helpers for gateway process discovery."""


_GATEWAY_ENTRYPOINTS = {"hermes-gateway", "hermes-gateway.exe"}


def is_gateway_dedicated_entrypoint(tokens: list[str]) -> bool:
    """Match gateway-dedicated executable or Python script tokens in executable position.

    Process arguments may mention the systemd unit without being a gateway (for example,
    ``journalctl -u hermes-gateway``). Only argv[0] or the script operand of a Python interpreter
    identifies this dedicated entrypoint.
    """
    if not tokens:
        return False
    basenames = [token.lower().replace("\\", "/").rsplit("/", 1)[-1] for token in tokens]
    if basenames[0] in _GATEWAY_ENTRYPOINTS:
        return True
    executable = basenames[0].removesuffix(".exe")
    if executable not in {"python", "pythonw", "py"} and not executable.startswith(
        ("python2", "python3", "pythonw2", "pythonw3")
    ):
        return False

    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in ("-c", "-m"):
            return False
        if token in ("-W", "-X", "-Q", "--check-hash-based-pycs"):
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return basenames[i] in _GATEWAY_ENTRYPOINTS
    return False
