#!/usr/bin/env python3
"""Smoke-test YouTube extraction for specific URLs using production opts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

CASES: list[tuple[str, str]] = [
    ("Rick Astley", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("Hollywood Action", "https://www.youtube.com/watch?v=yAtew9dZX_E"),
    ("Love Story", "https://www.youtube.com/watch?v=8xg3vE8Ie_E"),
    ("IxxstCcJlsc", "https://www.youtube.com/watch?v=IxxstCcJlsc"),
]

_EXTRACT_SCRIPT = """
import os
import sys
from cadence.sources.youtube import YtDlpConfig, _extract_with_fallback

impersonate_raw = os.environ.get("YTDLP_IMPERSONATE")
if impersonate_raw is None:
    impersonate = "chrome"
elif impersonate_raw == "":
    impersonate = None
else:
    impersonate = impersonate_raw

cfg = YtDlpConfig(
    cookie_file=os.environ.get("YTDLP_COOKIE_FILE") or None,
    proxy=os.environ.get("YTDLP_PROXY") or None,
    impersonate=impersonate,
)
track = _extract_with_fallback(cfg, sys.argv[1], search=False)
print(track.title)
"""


def ensure_deno_on_path() -> None:
    deno_bin = Path.home() / ".deno" / "bin"
    if (deno_bin / "deno").is_file():
        path = os.environ.get("PATH", "")
        if str(deno_bin) not in path.split(os.pathsep):
            os.environ["PATH"] = f"{deno_bin}{os.pathsep}{path}"


def subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    deno = Path.home() / ".deno" / "bin"
    if (deno / "deno").is_file():
        env["PATH"] = f"{deno}{os.pathsep}{env.get('PATH', '')}"
    return env


def main() -> int:
    ensure_deno_on_path()
    failures = 0
    for label, url in CASES:
        print(f"=== {label} ===", flush=True)
        print(f"url: {url}")
        proc = subprocess.Popen(
            [sys.executable, "-c", _EXTRACT_SCRIPT, url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=subprocess_env(),
            cwd=REPO_ROOT,
        )
        try:
            stdout, stderr = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            print("FAIL: timed out after 120s", flush=True)
            failures += 1
            print()
            continue
        if proc.returncode == 0:
            print(f"OK: {stdout.strip()}")
            print("stream_url: yes")
        else:
            detail = (stderr or stdout).strip().splitlines()
            last = detail[-1] if detail else "unknown error"
            print(f"FAIL: {last}")
            if len(detail) > 1:
                print(f"detail: {detail[-2]}")
            failures += 1
        print()
    if failures:
        print(f"SUMMARY: {failures}/{len(CASES)} failed")
        return 1
    print("SUMMARY: all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
