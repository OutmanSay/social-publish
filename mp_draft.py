#!/usr/bin/env python3
"""公众号草稿一条命令：纯文本转换 → 补丁自检 → preflight → 建草稿 → 验封面。

默认只预演；加 --execute 才真建草稿。任何一步不过就非零退出，不降级。

python3 mp_draft.py 文章.md --title 标题 --summary 摘要 --cover 封面.png [--execute]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from md2plain import convert  # noqa: E402
from md2wechat import THEMES, md_to_wechat_html  # noqa: E402

from apply_patches import opencli_root  # noqa: E402

ADAPTER = opencli_root() / "clis/weixin/create-draft.js"
PATCH = HERE / "patches/opencli/weixin/create-draft.js"
INCOMPLETE = "请补充封面图"


def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def drafts():
    r = run(["opencli", "weixin", "drafts", "-f", "json", "--trace", "retain-on-failure"], 120)
    if r.returncode != 0:
        if "EMPTY_RESULT" in (r.stdout + r.stderr):
            return []
        die(f"读取草稿箱失败：{r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def ensure_patch():
    if "DataTransfer" in ADAPTER.read_text():
        return
    if not PATCH.exists():
        die(f"create-draft.js 不含封面上传补丁，备份也不在 {PATCH}")
    shutil.copy(PATCH, ADAPTER)
    run(["opencli", "daemon", "restart"], 60)
    print("🔧 已恢复 create-draft.js 封面补丁并重启 daemon")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown")
    ap.add_argument("--title", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--cover", required=True)
    ap.add_argument("--author", default=os.environ.get("MP_AUTHOR", ""))
    ap.add_argument("--theme", default="minimal-green", choices=list(THEMES), help="排版主题")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    if len(a.title) > 64:
        die(f"标题 {len(a.title)} 字，超过 64")
    if not a.author:
        die("作者不能空：传 --author 或设 MP_AUTHOR")
    if len(a.author) > 8:
        die("作者超过 8 字")
    cover = Path(a.cover).expanduser()
    if not cover.exists():
        die(f"封面不存在：{cover}（先用 gpt-image-2.5-sunburst 生成，不许省略封面）")

    raw_md = Path(a.markdown).expanduser().read_text(encoding="utf-8")
    if re.search(r"!\[[^\]]*\]\(", raw_md):
        die("正文含 Markdown 图片：本机图片进不了公众号正文（要先走微信上传接口），先删掉或改成文字")
    rich_html = md_to_wechat_html(raw_md, theme_name=a.theme)
    text = convert(raw_md)  # 只用于预览

    work = Path(tempfile.mkdtemp(prefix="mp_draft_"))
    body = work / "body.html"
    body.write_text(rich_html, encoding="utf-8")
    jpg = work / "cover.jpg"
    r = run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "65", "-Z", "1200", str(cover), "--out", str(jpg)], 60)
    if r.returncode != 0:
        die(f"封面压缩失败：{r.stderr.strip()[:200]}")

    print(f"正文 {len(text)} 字，HTML {len(rich_html)} 字符（主题 {a.theme}）→ {body}\n封面 {jpg.stat().st_size // 1024}KB → {jpg}")
    print("---- 正文前 6 行 ----\n" + "\n".join(text.splitlines()[:6]))
    if not a.execute:
        print("\n（预演结束，未建草稿。确认后加 --execute）")
        return

    ensure_patch()
    r = run([sys.executable, str(HERE / "preflight.py"), "--platform", "weixin", "--deep"], 180)
    if r.returncode != 0:
        die("公众号登录态失效，先跑 preflight.py --platform weixin --repair --deep")

    norm = lambda s: re.sub(r"\\([_*\\#])", r"\1", s).strip(' "\'')
    before = {(norm(d["Title"]), d["Time"]) for d in drafts()}
    r = run(["opencli", "weixin", "create-draft", rich_html, "--title", a.title, "--author", a.author,
             "--summary", a.summary, "--cover-image", str(jpg), "--timeout", "240", "--trace", "retain-on-failure", "-f", "json"], 300)
    if r.returncode != 0:
        die(f"create-draft 失败（不许去掉封面重试）：{(r.stderr or r.stdout).strip()[:400]}")

    after = drafts()
    new = [d for d in after if norm(d["Title"]) == a.title and (norm(d["Title"]), d["Time"]) not in before]
    if not new:
        die("草稿箱里没找到新草稿，保存可能没成功，去后台确认，别重复建")
    if INCOMPLETE in new[0]["Time"]:
        die(f"草稿已建但封面没设上（{new[0]['Time']}），不许报告成功")

    print(f"\n✅ 草稿已建，封面已设：{a.title}（{new[0]['Time']}）")
    old = [d["Time"] for d in after if norm(d["Title"]) == a.title and d is not new[0]]
    if old:
        print("⚠️ 草稿箱还有同名旧稿，请手动删除：" + "；".join(old))
    print("下一步：提醒用手机「公众号助手」App 点发表。")


if __name__ == "__main__":
    main()
