#!/usr/bin/env python3
"""小红书图文一条命令：补丁自检 → 正文转纯文本 → 压封面 → 发布/存草稿 → 草稿箱核验。

三档，互斥：
  （不加）     只预演：打印将要发的内容，不碰页面
  --draft      存进创作平台草稿箱并核验图片数（测试用，事后 draft-delete 删掉）
  --execute    真发布（用户确认过正文后才可用）

python3 xhs_note.py 文章.md --title 标题 --cover 封面.png [--cards "卡1|||卡2"] [--draft|--execute]

图片顺序：封面图固定首图，后面是 --cards 本地渲染的文字卡（render_cards.py，
不用小红书自带「文字配图」，所以没有顺序限制、字也不会糊）。卡内第一行是卡片标题，换行用 \\n。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from md2plain import convert  # noqa: E402

from apply_patches import opencli_root  # noqa: E402

ADAPTER = opencli_root() / "clis/xiaohongshu/publish.js"
PATCH = HERE / "patches/opencli/xiaohongshu/publish.js"
MARK = "fileChooserOpened'))"
MAX_BODY = 1000


def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, timeout=400):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure_patch():
    if MARK in ADAPTER.read_text():
        return
    if not PATCH.exists():
        die(f"publish.js 不含图片上传补丁，备份也不在 {PATCH}")
    shutil.copy(PATCH, ADAPTER)
    run(["opencli", "daemon", "restart"], 60)
    print("🔧 已恢复小红书图片上传补丁并重启 daemon")


def drafts():
    r = run(["opencli", "xiaohongshu", "drafts", "-f", "json"], 120)
    if r.returncode != 0:
        die(f"读取草稿箱失败：{r.stderr.strip()[:300]}")
    return json.loads(r.stdout or "[]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown")
    ap.add_argument("--title", required=True)
    ap.add_argument("--cover", required=True)
    ap.add_argument("--cards", default="")
    ap.add_argument("--card-style", default="简约")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--draft", action="store_true")
    mode.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    if len(a.title) > 20:
        die(f"标题 {len(a.title)} 字，小红书上限 20")
    cover = Path(a.cover).expanduser()
    if not cover.exists():
        die(f"封面不存在：{cover}（先用 gpt-image-2.5-sunburst 生成，不许省略封面）")

    body = convert(Path(a.markdown).expanduser().read_text(encoding="utf-8")).strip()
    # 自动清除引流外链与尾部引导语（小红书禁带外链）
    body = re.sub(r"https?://[^\s]+", "", body).strip()
    body = re.sub(r"(完整[^\n]*：?\s*$)|(阅读原文[^\n]*$)", "", body).strip()
    if len(body) > MAX_BODY:
        die(f"正文 {len(body)} 字，超过小红书 {MAX_BODY} 字上限。改写成精简版 .md 再跑，别硬截断")
    if re.search(r"^#|^>|\*\*|\]\(", body, re.M):
        die("正文仍有 Markdown 残留")
    cards = [c.strip() for c in a.cards.split("|||") if c.strip()]
    if not cards:
        die("小红书铁律：必须提供 --cards 渲染 2~3 张本地文字卡，禁止只发单图封面")

    work = Path(tempfile.mkdtemp(prefix="xhs_"))
    jpg = work / "cover.jpg"
    r = run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "65", "-Z", "1200", str(cover), "--out", str(jpg)], 60)
    if r.returncode != 0:
        die(f"封面压缩失败：{r.stderr.strip()[:200]}")
    images = [str(jpg)]
    if cards:
        r = run([sys.executable, str(HERE / "render_cards.py"), "--cards", "|||".join(cards), "--out-dir", str(work / "cards")], 60)
        if r.returncode != 0:
            die(f"文字卡渲染失败：{(r.stderr or r.stdout).strip()[-300:]}")
        images += r.stdout.split()

    expected = len(images)
    print(f"标题：{a.title}\n正文 {len(body)} 字\n图片 {expected} 张：封面图（首图）" +
          (f" + {len(cards)} 张本地文字卡 → {work / 'cards'}" if cards else ""))
    if not (a.draft or a.execute):
        print("---- 正文 ----\n" + body + "\n\n（预演结束，未碰页面。测试加 --draft，真发加 --execute）")
        return

    ensure_patch()
    cmd = ["opencli", "xiaohongshu", "publish", body, "--title", a.title, "--images", ",".join(images), "-f", "json"]
    # 不传 --topics：适配器挂话题必报 "no real topic entity appeared"（2026-09-13 实测）
    if a.draft:
        cmd += ["--draft", "true"]
    before = {d["id"] for d in drafts()}

    r = run(cmd)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or ("成功" not in out):
        left = [d["id"] for d in drafts() if d["id"] not in before]
        extra = f"\n失败留下的残留草稿（报给用户，重跑前先 draft-delete）：{left}" if left else ""
        die(f"发布命令失败（不许去掉 --images 重试）：{out[-500:]}{extra}")

    if a.draft:
        new = [d for d in drafts() if d["id"] not in before]
        if not new:
            die("命令说成功，但草稿箱里没有新草稿")
        if new[0].get("images") != expected:
            die(f"草稿图片数 {new[0].get('images')}，应为 {expected}：封面没传上")
        print(f"\n✅ 草稿已存，{expected} 张图齐全。id={new[0]['id']}")
        print(f"测试完删除：opencli xiaohongshu draft-delete \"{new[0]['id']}\" --execute")
    else:
        print(f"\n✅ 已发布：{out[-300:]}")


if __name__ == "__main__":
    main()
