#!/usr/bin/env python3
"""百家号文章发布：Markdown转换 → 封面图上传 → 单图封面绑定 → 发布/存草稿。

默认只预演；加 --execute 才真发布；加 --draft 存为草稿。
用法：
  python3 bjh_post.py 文章.md --title "标题" --cover 封面.jpg [--draft|--execute]
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


# opencli 的 eval 只接受位置参数，整篇正文 + 封面 base64 塞进去会超 ARG_MAX。
# 分块送：先按 CHUNK 把内容累到页面上的 window.__bjh_payload，最后一步再注入。
CHUNK = 20000


def push_payload(session: str, key: str, data: str) -> None:
    """把 data 分片追加到页面 window.__bjh_payload[key]。"""
    opencli_eval(session, f"window.__bjh_payload = window.__bjh_payload || {{}}; window.__bjh_payload[{json.dumps(key)}] = '';")
    for i in range(0, len(data), CHUNK):
        seg = data[i:i + CHUNK]
        r = opencli_eval(session, f"window.__bjh_payload[{json.dumps(key)}] += {json.dumps(seg)}; window.__bjh_payload[{json.dumps(key)}].length")
        if r is None:
            die(f"分片传输失败（{key} 第 {i // CHUNK + 1} 片）")


def post_article(title: str, text: str, cover_path: Path, draft_only: bool = False, execute: bool = False) -> dict:
    if not cover_path.exists():
        die(f"封面图不存在：{cover_path}")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    html = "".join(f"<p>{p}</p>" for p in paragraphs)

    print(f"平台：百家号\n标题：{title}\n正文：{len(text)} 字，{len(paragraphs)} 个段落\n封面：{cover_path}")
    if not (draft_only or execute):
        print("\n（预演结束，未碰页面。存草稿加 --draft，真发布加 --execute）")
        return {"ok": True, "dry_run": True}

    with open(cover_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    session = "social-baijiahao"
    print("[*] 打开百家号后台...")
    r = run_cmd(["opencli", "browser", session, "open", "https://baijiahao.baidu.com/builder/rc/edit?type=news", "--window", "foreground"], 40)
    if r.returncode != 0:
        die(f"无法打开百家号编辑页面：{r.stderr or r.stdout}")
    time.sleep(4)

    # 先把长内容分片送进页面（避免命令行参数超长），再用短 JS 注入
    print("[*] 分片传输正文与封面...")
    push_payload(session, "title", title)
    push_payload(session, "html", html)
    push_payload(session, "cover", b64)

    js_inject = """
    (() => {
        const P = window.__bjh_payload || {};
        if (!window.editor || !window.editor.__bjh_news_setTitle) return { ok: false, error: "未找到百家号编辑器接口，请确认百家号是否已登录" };
        window.editor.__bjh_news_setTitle(P.title);
        window.editor.setContent(P.html);

        const iframe = document.querySelector("#ueditor iframe");
        if (!iframe) return { ok: false, error: "未找到 ueditor iframe" };
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        doc.body.focus();

        const bin = atob(P.cover);
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const file = new File([arr], "cover.jpg", { type: "image/jpeg" });
        const dt = new DataTransfer();
        dt.items.add(file);
        doc.body.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));

        return { ok: true };
    })()
    """
    res = opencli_eval(session, js_inject)
    if isinstance(res, dict) and not res.get("ok"):
        run_cmd(["opencli", "browser", session, "close"], 15)
        die(f"内容注入失败：{res.get('error')}")
    time.sleep(5)

    # 封面选择
    js_cover = """
    (() => {
        const radio = document.querySelector("input[name='cover'][value='one']");
        if (radio && !radio.checked) radio.click();

        const selectBtn = document.querySelector(".FeEditorApp-_73a3a52aab7e3a36-content");
        selectBtn?.click();
        return "clicked cover";
    })()
    """
    opencli_eval(session, js_cover)
    time.sleep(2)

    # 确认封面并在发布前取消播客
    js_confirm_cover = """
    (() => {
        const modal = document.querySelector(".cheetah-modal-content");
        const confirmBtn = Array.from(modal ? modal.querySelectorAll("button") : []).find(b => b.textContent.includes("确定"));
        confirmBtn?.click();

        const podcastCb = Array.from(document.querySelectorAll("input[type='checkbox']")).find(c => c.closest("label")?.textContent?.includes("自动生成播客"));
        if (podcastCb && podcastCb.checked) podcastCb.click();

        return "done";
    })()
    """
    opencli_eval(session, js_confirm_cover)
    time.sleep(2)

    target_btn = "存草稿" if draft_only else "发布"
    js_action = f"""
    (() => {{
        const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "{target_btn}");
        if (btn) {{
            btn.click();
            return "clicked";
        }}
        return "no btn";
    }})()
    """
    res_act = opencli_eval(session, js_action)
    time.sleep(4)
    run_cmd(["opencli", "browser", session, "close"], 15)

    if res_act == "clicked":
        action_name = "草稿已保存" if draft_only else "已提交发布"
        print(f"\n✅ 百家号{action_name}：《{title}》")
        return {"ok": True, "title": title}
    else:
        die(f"百家号未找到操作按钮：{target_btn}")


def main() -> None:
    ap = argparse.ArgumentParser(description="百家号文章发布")
    ap.add_argument("markdown", help="Markdown 源文件路径")
    ap.add_argument("--title", required=True, help="文章标题")
    ap.add_argument("--cover", required=True, help="封面图片路径")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--draft", action="store_true", help="存为草稿")
    mode.add_argument("--execute", action="store_true", help="确认真实发布")
    args = ap.parse_args()

    md_file = Path(args.markdown).expanduser()
    if not md_file.exists():
        die(f"文件不存在：{md_file}")
    text = convert(md_file.read_text(encoding="utf-8"))
    cover = Path(args.cover).expanduser()

    post_article(args.title, text, cover, draft_only=args.draft, execute=args.execute)


if __name__ == "__main__":
    main()
