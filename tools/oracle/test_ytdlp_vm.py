#!/usr/bin/env python3
"""Quick yt-dlp extraction probe for VM diagnostics."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yt_dlp

from cadence.sources.youtube import YtDlpConfig, build_ytdl_opts

ACCEPTANCE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
HARD_ACCEPTANCE_URL = "https://www.youtube.com/watch?v=8xg3vE8Ie_E"
POT_PROVIDER_PING_URL = "http://127.0.0.1:4416/ping"
EXTRACT_TIMEOUT_SEC = 120
WARP_PROXY = os.environ.get("YTDLP_PROXY", "socks5h://127.0.0.1:1080")
WARP_EGRESS_CHECK_URL = "https://ifconfig.me"
REPO_ROOT = Path(__file__).resolve().parent

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


def production_config() -> YtDlpConfig:
    cookie_file = os.environ.get("YTDLP_COOKIE_FILE") or None
    proxy = os.environ.get("YTDLP_PROXY") or WARP_PROXY
    impersonate_raw = os.environ.get("YTDLP_IMPERSONATE")
    if impersonate_raw is None:
        impersonate: str | None = "chrome"
    elif impersonate_raw == "":
        impersonate = None
    else:
        impersonate = impersonate_raw
    return YtDlpConfig(
        cookie_file=cookie_file,
        proxy=proxy,
        impersonate=impersonate,
    )


def ensure_deno_on_path() -> None:
    deno_bin = Path.home() / ".deno" / "bin"
    if (deno_bin / "deno").is_file():
        path = os.environ.get("PATH", "")
        if str(deno_bin) not in path.split(os.pathsep):
            os.environ["PATH"] = f"{deno_bin}{os.pathsep}{path}"


def subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def pot_plugin_installed() -> bool:
    return importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil_http") is not None


def pot_provider_reachable() -> bool:
    request = urllib.request.Request(POT_PROVIDER_PING_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        return exc.code == 200
    except OSError:
        return False


def warp_proxy_reachable() -> bool:
    request = urllib.request.Request(WARP_EGRESS_CHECK_URL, method="GET")
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": WARP_PROXY, "https": WARP_PROXY}),
        )
        with opener.open(request, timeout=15) as response:
            return response.status == 200
    except OSError:
        return False


def safe_print(text: str) -> None:
    """Print without crashing on Windows consoles that lack Unicode support."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def try_case(name: str, *, url: str) -> bool:
    safe_print(f"=== {name} ===")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _EXTRACT_SCRIPT, url],
            capture_output=True,
            text=True,
            timeout=EXTRACT_TIMEOUT_SEC,
            env=subprocess_env(),
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        safe_print(f"FAIL: timed out after {EXTRACT_TIMEOUT_SEC}s")
        return False
    if proc.returncode == 0:
        title = proc.stdout.strip() or "<no title>"
        safe_print(f"OK: {title}")
        return True
    detail = (proc.stderr or proc.stdout).strip().splitlines()
    safe_print(f"FAIL: {detail[-1] if detail else 'unknown error'}")
    return False


def main() -> int:
    ensure_deno_on_path()
    failures = 0
    prod_opts = build_ytdl_opts(production_config())
    safe_print(f"yt-dlp {yt_dlp.version.__version__}")
    safe_print(f"deno_on_path: {shutil.which('deno') or 'missing'}")
    safe_print(f"pot_plugin_installed: {pot_plugin_installed()}")
    safe_print(f"ytdlp_proxy: {prod_opts.get('proxy', '<unset>')}")
    safe_print(f"ytdlp_impersonate: {prod_opts.get('impersonate', '<unset>')}")
    safe_print(
        "ytdlp_player_client: "
        f"{prod_opts.get('extractor_args', {}).get('youtube', {}).get('player_client', [])}",
    )

    safe_print("=== pot_provider_reachable ===")
    if pot_provider_reachable():
        safe_print("OK: POT provider reachable")
    else:
        safe_print("FAIL: POT provider not reachable at 127.0.0.1:4416/ping")
        failures += 1

    safe_print("=== warp_proxy_reachable ===")
    if warp_proxy_reachable():
        safe_print(f"OK: WARP proxy reachable via {WARP_PROXY}")
    else:
        safe_print(f"FAIL: WARP proxy not reachable at {WARP_PROXY}")
        failures += 1

    if not pot_plugin_installed():
        safe_print("=== with_pot_plugin ===")
        safe_print("FAIL: bgutil yt-dlp plugin not installed")
        failures += 1
    elif not pot_provider_reachable():
        safe_print("=== with_pot_plugin ===")
        safe_print("FAIL: POT provider not running")
        failures += 1
    elif not try_case("with_pot_plugin", url=ACCEPTANCE_URL):
        failures += 1

    if try_case("hard_acceptance", url=HARD_ACCEPTANCE_URL):
        safe_print("INFO: Love Story extraction succeeded (major-label hard case)")
    else:
        safe_print(
            "INFO: Love Story still failing — common on datacenter/WARP IPs even with POT; "
            "not counted as a hard failure",
        )

    safe_print("=== plugin_missing_control ===")
    if pot_plugin_installed():
        safe_print("INFO: plugin present (expected after POT install)")
    else:
        safe_print("INFO: plugin absent (expected before POT install)")

    if failures:
        safe_print(f"SUMMARY: {failures} check(s) failed")
        return 1
    safe_print("SUMMARY: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
