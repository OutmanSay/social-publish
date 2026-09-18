#!/usr/bin/env python3
"""Deterministic, confirmation-gated publisher for supported social platforms."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
OPENCLI = shutil.which("opencli") or os.path.expanduser("~/.local/bin/opencli")
PYTHON = sys.executable
TWITTER_DISABLED_ERROR = """❌ publish.py 的 X 直发路径已停用（两处 --window background + split_for_x 用 \\n\\n 拼段落，与 X 的 insertText 注入能力冲突，必然失败）。
请用 x_thread/publish_thread.py —— 用法见 SKILL.md「X thread 发布」节。"""


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


def publish_toutiao(text: str, images: list[str], title: str = "", execute: bool = True) -> dict:
    import tempfile
    cover = images[0] if images else ""
    if not cover:
        return {"ok": False, "error": "今日头条发布需要至少一张封面图"}
    if not title:
        first_line = text.strip().splitlines()[0].strip()
        title = first_line[:28]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(text)
        tmp_path = tf.name
    command = [PYTHON, os.path.join(ROOT, "toutiao_post.py"), tmp_path, "--title", title, "--cover", cover]
    if execute:
        command.append("--execute")
    returncode, output = run(command, timeout=90)
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return {"ok": command_succeeded(returncode, output), "output": output}


def publish_baijiahao(text: str, images: list[str], title: str = "", execute: bool = True) -> dict:
    import tempfile
    cover = images[0] if images else ""
    if not cover:
        return {"ok": False, "error": "百家号发布需要至少一张封面图"}
    if not title:
        first_line = text.strip().splitlines()[0].strip()
        title = first_line[:30]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(text)
        tmp_path = tf.name
    command = [PYTHON, os.path.join(ROOT, "bjh_post.py"), tmp_path, "--title", title, "--cover", cover]
    if execute:
        command.append("--execute")
    returncode, output = run(command, timeout=90)
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return {"ok": command_succeeded(returncode, output), "output": output}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", action="append", choices=["weibo", "twitter", "jike", "toutiao", "baijiahao"], required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--content-file")
    parser.add_argument("--title", default="", help="文章标题（头条/百家号必填或自动提取）")
    parser.add_argument("--image", action="append", default=[], help="配图路径，可多次；微博、即刻、头条、百家号都会带上")
    parser.add_argument("--rehearse", action="store_true",
                        help="彩排：微博真上传图片拿 pid、即刻真填图文后清空，都不发帖")
    parser.add_argument("--execute", action="store_true", help="Required for irreversible publishing")
    parser.add_argument("--skip-preflight", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    platforms = list(dict.fromkeys(args.platform))
    if "twitter" in platforms:
        print(TWITTER_DISABLED_ERROR)
        return 2

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
        "length": len(text),
        "images": args.image,
    }
    missing = [image for image in args.image if not os.path.exists(image)]
    if missing:
        print(json.dumps({"ok": False, "error": f"配图不存在：{missing}（不许去掉配图继续发）"}, ensure_ascii=False))
        return 1
    args.image = shrink_images(args.image)
    if args.rehearse and not args.execute:
        rehearsers = {
            "weibo": publish_weibo,
            "jike": publish_jike,
            "toutiao": lambda t, img, execute=False: publish_toutiao(t, img, title=args.title, execute=False),
            "baijiahao": lambda t, img, execute=False: publish_baijiahao(t, img, title=args.title, execute=False),
        }
        results = {p: rehearsers[p](text, args.image, execute=False) for p in platforms if p in rehearsers}
        print(json.dumps({"ok": all(r["ok"] for r in results.values()), "rehearse": True, "results": results},
                         ensure_ascii=False, indent=2))
        return 0 if all(r["ok"] for r in results.values()) else 1
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if not args.skip_preflight:
        returncode, output = preflight([p for p in platforms if p in {"weibo", "jike"}])
        if returncode != 0:
            print(json.dumps({"ok": False, "stage": "preflight", "detail": output}, ensure_ascii=False, indent=2))
            return 1

    publishers = {
        "weibo": lambda t: publish_weibo(t, args.image),
        "jike": lambda t: publish_jike(t, args.image),
        "toutiao": lambda t: publish_toutiao(t, args.image, title=args.title, execute=True),
        "baijiahao": lambda t: publish_baijiahao(t, args.image, title=args.title, execute=True),
    }
    results = {platform: publishers[platform](text) for platform in platforms}
    response = {"ok": all(item["ok"] for item in results.values()), "results": results}
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
