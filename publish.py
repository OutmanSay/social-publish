#!/usr/bin/env python3
"""Deterministic, confirmation-gated publisher for Weibo, X and Jike."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
OPENCLI = shutil.which("opencli") or os.path.expanduser("~/.local/bin/opencli")
PYTHON = sys.executable
STATUS_URL = re.compile(r"https://x\.com/[^\s/]+/status/\d+")


def weighted_length(text: str) -> int:
    return sum(1 if ord(char) < 0x1100 else 2 for char in text)


def hard_split(text: str, limit: int) -> list[str]:
    parts, current, weight = [], [], 0
    for char in text:
        char_weight = 1 if ord(char) < 0x1100 else 2
        if current and weight + char_weight > limit:
            parts.append("".join(current).strip())
            current, weight = [], 0
        current.append(char)
        weight += char_weight
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def split_for_x(text: str, limit: int = 260) -> list[str]:
    if weighted_length(text) <= limit:
        return [text.strip()]
    chunks = re.split(r"(?<=[。！？!?；;])|\n{2,}", text.strip())
    parts, current = [], ""
    for raw in chunks:
        chunk = raw.strip()
        if not chunk:
            continue
        candidate = f"{current}\n\n{chunk}" if current else chunk
        if weighted_length(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if weighted_length(chunk) <= limit:
            current = chunk
        else:
            parts.extend(hard_split(chunk, limit))
    if current:
        parts.append(current)
    return parts


def run(command: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return 124, (output + "\ncommand timed out").strip()


def command_succeeded(returncode: int, output: str) -> bool:
    if returncode != 0:
        return False
    try:
        payload = json.loads(output)
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("ok") is False:
                return False
            if str(item.get("status", "")).lower() in {"failed", "error"}:
                return False
        return True
    except json.JSONDecodeError:
        value = output.lower()
        return "ok: false" not in value and "status: failed" not in value


def preflight(platforms: list[str]) -> tuple[int, str]:
    command = [PYTHON, os.path.join(ROOT, "preflight.py"), "--repair", "--deep"]
    for platform in platforms:
        command.extend(["--platform", platform])
    return run(command, timeout=120)


def retryable_composer_failure(output: str) -> bool:
    value = output.lower()
    return "selector not found" in value or "composer text area" in value


def twitter_command(command: list[str]) -> tuple[int, str]:
    # opencli 默认 60s 命令上限对 post 不够用(2026-09-13 实测:帖子已发出、命令仍报 TIMEOUT,
    # 上层会误判为失败)。post 没有 --timeout 参数,只能走这个全局环境变量。
    os.environ["OPENCLI_BROWSER_COMMAND_TIMEOUT"] = "180"
    returncode, output = run(command, timeout=210)
    if not command_succeeded(returncode, output) and retryable_composer_failure(output):
        # Safe to retry: these failures happen before text insertion / Post click.
        run([PYTHON, os.path.join(ROOT, "preflight.py"), "--platform", "twitter", "--repair", "--deep"], timeout=90)
        returncode, output = run(command, timeout=210)
    return returncode, output


def shrink_images(images: list[str]) -> list[str]:
    # 即刻适配器单图 >~700KB 必崩 sendCommand（base64 过 bridge 超限，2026-09-13 实测），统一压成 ≤~500KB jpg
    import tempfile
    out_dir = tempfile.mkdtemp(prefix="social_img_")
    shrunk = []
    for index, image in enumerate(images):
        for quality, edge in ((70, 1600), (60, 1280), (50, 1080)):
            target = os.path.join(out_dir, f"img{index}-{quality}.jpg")
            run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), "-Z", str(edge), image, "--out", target])
            if os.path.exists(target) and os.path.getsize(target) <= 500_000:
                break
        shrunk.append(target)
    return shrunk


def publish_weibo(text: str, images: list[str], execute: bool = True) -> dict:
    command = [PYTHON, os.path.join(ROOT, "weibo_post.py"), text]
    for image in images:
        command += ["--image", image]
    if execute:
        command.append("--execute")
    returncode, output = run(command, timeout=45 + 60 * len(images))
    return {"ok": command_succeeded(returncode, output), "output": output}


def publish_jike(text: str, images: list[str], execute: bool = True) -> dict:
    command = [OPENCLI, "jike", "create", text, "-f", "json"]
    if images:
        command += ["--images", ",".join(images)]
    if not execute:
        command += ["--dry-run", "true"]   # 本机补丁：填好图文、核验后清空，不发送
    returncode, output = run(command, timeout=120 + 60 * len(images))  # 实测 1 图 128s
    return {"ok": command_succeeded(returncode, output), "output": output}


def publish_twitter(text: str) -> dict:
    # 用 persistent 会话复用同一窗口发 Thread(解决 2026-08-12:ephemeral 每条一窗,
    # 关窗触发 x.com beforeunload 弹窗,对话框无人应答使 opencli 命令挂起,驱动发布的模型卡死)。
    # 全部发完后窗口保留为后台 tab,下次发布直接复用;不要手动 close,关窗仍可能触发弹窗。
    parts = split_for_x(text)
    outputs, parent_url = [], None
    for index, part in enumerate(parts):
        if index == 0:
            command = [OPENCLI, "twitter", "post", part, "-f", "json", "--window", "background",
                       "--site-session", "persistent", "--keep-tab", "true"]
        else:
            if not parent_url:
                return {"ok": False, "parts": parts, "outputs": outputs, "error": "First X post returned no status URL; stopped to avoid an unthreaded duplicate."}
            command = [OPENCLI, "twitter", "reply", parent_url, part, "-f", "json", "--window", "background",
                       "--site-session", "persistent", "--keep-tab", "true"]
        returncode, output = twitter_command(command)
        outputs.append(output)
        if not command_succeeded(returncode, output):
            return {"ok": False, "parts": parts, "outputs": outputs, "error": f"X part {index + 1} failed"}
        urls = STATUS_URL.findall(output)
        if urls:
            parent_url = urls[-1]
    return {"ok": True, "parts": parts, "outputs": outputs, "url": parent_url}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", action="append", choices=["weibo", "twitter", "jike"], required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--content-file")
    parser.add_argument("--image", action="append", default=[], help="配图路径，可多次；微博、即刻都会带上")
    parser.add_argument("--rehearse", action="store_true",
                        help="彩排：微博真上传图片拿 pid、即刻真填图文后清空，都不发帖")
    parser.add_argument("--execute", action="store_true", help="Required for irreversible publishing")
    parser.add_argument("--skip-preflight", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    platforms = list(dict.fromkeys(args.platform))
    if args.text is not None:
        text = args.text
    else:
        with open(args.content_file, encoding="utf-8") as handle:
            text = handle.read()
    text = text.strip()
    if not text:
        print(json.dumps({"ok": False, "error": "Content is empty"}, ensure_ascii=False))
        return 1

    plan = {
        "ok": True, "dry_run": not args.execute, "platforms": platforms,
        "length": len(text), "twitter_parts": split_for_x(text) if "twitter" in platforms else [],
        "images": args.image,
    }
    missing = [image for image in args.image if not os.path.exists(image)]
    if missing:
        print(json.dumps({"ok": False, "error": f"配图不存在：{missing}（不许去掉配图继续发）"}, ensure_ascii=False))
        return 1
    args.image = shrink_images(args.image)
    if args.rehearse and not args.execute:
        rehearsers = {"weibo": publish_weibo, "jike": publish_jike}
        results = {p: rehearsers[p](text, args.image, execute=False) for p in platforms if p in rehearsers}
        print(json.dumps({"ok": all(r["ok"] for r in results.values()), "rehearse": True, "results": results},
                         ensure_ascii=False, indent=2))
        return 0 if all(r["ok"] for r in results.values()) else 1
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if not args.skip_preflight:
        returncode, output = preflight(platforms)
        if returncode != 0:
            print(json.dumps({"ok": False, "stage": "preflight", "detail": output}, ensure_ascii=False, indent=2))
            return 1

    publishers = {"weibo": lambda t: publish_weibo(t, args.image), "twitter": publish_twitter,
                  "jike": lambda t: publish_jike(t, args.image)}
    results = {platform: publishers[platform](text) for platform in platforms}
    response = {"ok": all(item["ok"] for item in results.values()), "results": results}
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
