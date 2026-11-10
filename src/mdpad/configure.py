"""Command-line helper to write the server-side LLM provider base URL and API
key into a local ``.env`` file, so they never need to live in source or git
history.

Usage::

    uv run mdpad-configure --base-url https://host/v1 --api-key sk-...
    uv run mdpad-configure            # prompts interactively instead
"""

from __future__ import annotations

import argparse
import os
from getpass import getpass
from pathlib import Path

_KEYS = ("MDPAD_BASE_URL", "MDPAD_API_KEY")


def _read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _write_env(path: Path, env: dict[str, str]) -> None:
    # Owner-only permissions: this file holds a plaintext API key.
    data = "".join(f"{k}={v}\n" for k, v in env.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(path, 0o600)  # tighten if the file already existed with looser perms
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception:
        os.close(fd)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure mdpad's server-side LLM provider (.env).")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL, e.g. https://host/v1")
    parser.add_argument("--api-key", help="API key for that endpoint")
    parser.add_argument("--env-file", default=".env", help="Path to the .env file to write (default: ./.env)")
    args = parser.parse_args()

    path = Path(args.env_file)
    env = _read_env(path)

    base_url = args.base_url
    if base_url is None:
        current = env.get("MDPAD_BASE_URL", "")
        base_url = input(f"Base URL [{current}]: ").strip() or current

    api_key = args.api_key
    if api_key is None:
        prompt = "API key (leave blank to keep current): "
        api_key = getpass(prompt).strip() or env.get("MDPAD_API_KEY", "")

    env["MDPAD_BASE_URL"] = base_url
    env["MDPAD_API_KEY"] = api_key
    _write_env(path, env)
    print(f"Wrote {path.resolve()}")


if __name__ == "__main__":
    main()
