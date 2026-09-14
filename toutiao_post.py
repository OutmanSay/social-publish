#!/usr/bin/env python3
"""今日头条（头条号）文章发布：Markdown转换 → 封面图压制 → 后台静默发文 → 开启广告收益。

默认只预演；加 --execute 才真发布。
用法：
  python3 toutiao_post.py 文章.md --title "标题（≤30字）" --cover 封面.jpg [--execute]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from md2plain import convert  # noqa: E402

OPENCLI = shutil_which = "opencli"
MAX_TITLE = 30


def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def run_cmd(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def opencli_eval(session: str, js_code: str) -> any:
    r = run_cmd(["opencli", "browser", session, "eval", js_code], timeout=30)
    try:
        return json.loads(r.stdout)
    except Exception:
        return r.stdout.strip()


def post_article(title: str, text: str, cover_path: Path, execute: bool = False) -> dict:
    if len(title) > MAX_TITLE:
        die(f"标题共 {len(title)} 字，超过头条号 {MAX_TITLE} 字上限")
    if not cover_path.exists():
        die(f"封面图不存在：{cover_path}")

    # 将段落切分成 HTML
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    html = "".join(f"<p>{p}</p>" for p in paragraphs)

    print(f"平台：今日头条（头条号）\n标题：{title} ({len(title)}/{MAX_TITLE}字)\n正文：{len(text)} 字，{len(paragraphs)} 个段落\n封面：{cover_path}")
    if not execute:
        print("\n（预演结束，未碰页面。真发布加 --execute）")
        return {"ok": True, "dry_run": True}

    with open(cover_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    session = "social-toutiao"
    print("[*] 打开头条号后台...")
    r = run_cmd(["opencli", "browser", session, "open", "https://mp.toutiao.com/profile_v4/graphic/publish", "--window", "background"], 40)
    if r.returncode != 0:
        die(f"无法打开头条号创作页面：{r.stderr or r.stdout}")
    time.sleep(4)

    js_inject = f"""
    (() => {{
        const ta = document.querySelector("textarea[placeholder*='标题']");
        if (!ta) return {{ ok: false, error: "未找到标题输入框，请确认头条号是否已登录" }};
        ta.focus();
        document.execCommand("selectAll", false, null);
        document.execCommand("insertText", false, {json.dumps(title)});
        ta.dispatchEvent(new Event("input", {{ bubbles: true }}));

        const pm = document.querySelector(".ProseMirror");
        if (!pm) return {{ ok: false, error: "未找到 ProseMirror 编辑器" }};
        pm.focus();
        document.execCommand("selectAll", false, null);
        document.execCommand("delete", false, null);

        // 粘贴文本
        const dt = new DataTransfer();
        dt.setData("text/html", {json.dumps(html)});
        pm.dispatchEvent(new ClipboardEvent("paste", {{ clipboardData: dt, bubbles: true, cancelable: true }}));

        // 粘贴封面图片
        const bin = atob("{b64}");
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const file = new File([arr], "cover.jpg", {{ type: "image/jpeg" }});
        const dtImg = new DataTransfer();
        dtImg.items.add(file);
        pm.dispatchEvent(new ClipboardEvent("paste", {{ clipboardData: dtImg, bubbles: true, cancelable: true }}));

        return {{ ok: true }};
    }})()
    """
    res = opencli_eval(session, js_inject)
    if isinstance(res, dict) and not res.get("ok"):
        run_cmd(["opencli", "browser", session, "close"], 15)
        die(f"内容注入失败：{res.get('error')}")
    time.sleep(5)

    # 选项设置（单图封面 + 开启广告分成）
    js_options = """
    (() => {
        const radio = document.querySelector("input[value='2']"); // 单图
        if (radio) radio.click();
        const adRadio = document.querySelector("input[value='3']"); // 投放广告赚收益
        if (adRadio) adRadio.click();
        return "options set";
    })()
    """
    opencli_eval(session, js_options)
    time.sleep(2)

    # 点击发布
    js_pub = """
    (() => {
        const btn = document.querySelector(".publish-btn-last");
        if (!btn) return "no btn";
        btn.click();
        return "clicked";
    })()
    """
    opencli_eval(session, js_pub)
    time.sleep(3)

    # 确认弹窗
    js_confirm = """
    (() => {
        const btns = Array.from(document.querySelectorAll("button"));
        const confirmBtn = btns.find(b => b.textContent.trim() === "确认发布");
        if (confirmBtn) {
            confirmBtn.click();
            return "confirmed";
        }
        return "no confirm btn";
    })()
    """
    confirm_res = opencli_eval(session, js_confirm)
    time.sleep(4)
    run_cmd(["opencli", "browser", session, "close"], 15)

    if confirm_res == "confirmed":
        print(f"\n✅ 今日头条发布成功：《{title}》")
        return {"ok": True, "title": title}
    else:
        die(f"头条确认发布未触发：{confirm_res}")


def main() -> None:
    ap = argparse.ArgumentParser(description="今日头条文章发布")
    ap.add_argument("markdown", help="Markdown 源文件路径")
    ap.add_argument("--title", required=True, help="文章标题（≤30字）")
    ap.add_argument("--cover", required=True, help="封面图片路径")
    ap.add_argument("--execute", action="store_true", help="确认真实发布")
    args = ap.parse_args()

    md_file = Path(args.markdown).expanduser()
    if not md_file.exists():
        die(f"文件不存在：{md_file}")
    text = convert(md_file.read_text(encoding="utf-8"))
    cover = Path(args.cover).expanduser()

    post_article(args.title, text, cover, execute=args.execute)


if __name__ == "__main__":
    main()
