#!/usr/bin/env python3
"""Read-only social publishing checks and Browser Bridge based auth refresh."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.abspath(__file__))
OPENCLI = shutil.which("opencli") or os.path.expanduser("~/.local/bin/opencli")
PYTHON = sys.executable
URLS = {
    "weibo": "https://weibo.com",
    "twitter": "https://x.com/compose/post",
    "jike": "https://web.okjike.com",
    "zhihu": "https://www.zhihu.com",
    "weixin": "https://mp.weixin.qq.com",
}


def run(command: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return 124, (output + "\ncommand timed out").strip()
    except OSError as exc:
        return 127, f"{type(exc).__name__}: {exc}"


def excerpt(text: str, limit: int = 500) -> str:
    return " ".join(text.split())[:limit]


def classify(returncode: int, output: str) -> str:
    value = output.lower()
    if returncode == 124 or "timed out" in value:
        return "timeout"
    if "selector not found" in value or "composer" in value:
        return "adapter"
    if (
        "未登录" in output
        or "需要已登录" in output
        or "not_logged_in" in value
        or "logged_in: false" in value
        or "auth_required" in value
    ):
        return "auth"
    if "cookie" in value or "登录态" in output:
        return "auth"
    if returncode == 127:
        return "missing_dependency"
    return "unknown"


def check_platform(platform: str, deep: bool = False) -> dict:
    if platform == "weibo":
        command = [PYTHON, os.path.join(ROOT, "weibo_post.py"), "--check"]
    elif platform in {"twitter", "jike", "zhihu"}:
        command = [OPENCLI, platform, "whoami"]
    elif platform == "weixin":
        command = [OPENCLI, "weixin", "drafts"]
    else:
        return {"ok": False, "category": "unsupported", "detail": platform}

    returncode, output = run(command)
    ok = returncode == 0
    result = {
        "ok": ok,
        "category": "ok" if ok else classify(returncode, output),
        "detail": excerpt(output),
    }
    if ok and platform == "twitter" and deep:
        result = check_twitter_composer()
    return result


def bridge_open(platform: str, wait_seconds: int = 5) -> dict:
    """Open a background tab through the connected Chrome extension, never CUA."""
    session = f"social-publish-{platform}"
    returncode, output = run(
        [OPENCLI, "browser", session, "open", URLS[platform], "--window", "background"],
        timeout=30,
    )
    if returncode == 0:
        time.sleep(wait_seconds)
    close_rc, close_output = run([OPENCLI, "browser", session, "close"], timeout=15)
    detail = excerpt(output)
    if close_rc != 0:
        detail = f"{detail}; close: {excerpt(close_output)}"
    return {
        "ok": returncode == 0,
        "category": "ok" if returncode == 0 else classify(returncode, output),
        "detail": detail,
    }


def check_twitter_composer() -> dict:
    session = "social-publish-twitter-check"
    returncode, output = run(
        [OPENCLI, "browser", session, "open", URLS["twitter"], "--window", "background"],
        timeout=30,
    )
    if returncode == 0:
        time.sleep(3)
        returncode, output = run(
            [OPENCLI, "browser", session, "find", "--css", '[data-testid="tweetTextarea_0"]'],
            timeout=20,
        )
        if returncode == 0:
            try:
                returncode = 0 if json.loads(output).get("matches_n", 0) > 0 else 1
            except json.JSONDecodeError:
                returncode = 1
    run([OPENCLI, "browser", session, "close"], timeout=15)
    return {
        "ok": returncode == 0,
        "category": "ok" if returncode == 0 else "adapter",
        "detail": excerpt(output) if output else "X composer was not found",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform", action="append", choices=["all", *URLS], default=[],
        help="Repeat for multiple platforms; default: weibo, twitter, jike",
    )
    parser.add_argument("--repair", action="store_true", help="Refresh failed auth in a background Browser Bridge tab")
    parser.add_argument("--deep", action="store_true", help="Also verify that the X composer DOM is ready")
    args = parser.parse_args()

    requested = args.platform or ["weibo", "twitter", "jike"]
    platforms = list(URLS) if "all" in requested else list(dict.fromkeys(requested))
    results = {}
    for platform in platforms:
        status = check_platform(platform, deep=args.deep)
        if args.repair and not status["ok"] and status["category"] in {"auth", "adapter"}:
            refresh = bridge_open(platform)
            status = check_platform(platform, deep=args.deep)
            status["repair"] = refresh
        results[platform] = status

    output = {"ok": all(item["ok"] for item in results.values()), "platforms": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
