#!/usr/bin/env python3
"""全平台一键发布调度器：轻重分流 + 受控并发流水线 (max_workers=2)。

覆盖 7 大平台：
1. 微博（纯 HTTP，先锋零等待）
2. 即刻（浏览器）
3. 微信公众号草稿箱（富文本自动内联样式）
4. 今日头条（头条号长文）
5. 百度百家号（UEditor 长文）
6. 小红书（图文笔记 + 本地渲染卡片）
7. X / Twitter（Thread 自动回复串链）

用法：
  python3 publish_all.py 文章.md --cover 封面.png [--title "标题"] [--summary "摘要"] [--execute]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from md2wechat import md_to_wechat_html  # noqa: E402

PYTHON = sys.executable
OPENCLI = shutil.which("opencli") or os.path.expanduser("~/.local/bin/opencli")

ALL_PLATFORMS = ["weibo", "jike", "weixin", "toutiao", "baijiahao", "xiaohongshu", "twitter"]


def run_cmd(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return 124, (output + "\ncommand timed out").strip()


def extract_frontmatter(md_text: str) -> tuple[dict, str]:
    meta = {}
    content = md_text
    m = re.match(r"^---\n(.*?)\n---\n+(.*)$", md_text, flags=re.DOTALL)
    if m:
        fm, content = m.group(1), m.group(2)
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"\'')
    return meta, content


def prepare_shared_assets(md_path: Path, cover_path: Path, user_title: str = "", user_summary: str = ""):
    raw_md = md_path.read_text(encoding="utf-8")
    meta, body = extract_frontmatter(raw_md)
    title = user_title or meta.get("title") or (body.strip().splitlines()[0].replace("#", "").strip() if body else "未命名文章")

    # 提取引用块或首段作为摘要
    quotes = re.findall(r"^>\s*(.+)$", body, flags=re.MULTILINE)
    default_summary = " ".join(quotes[:3]) if quotes else (body.strip().split("\n\n")[0][:120] if body else "")
    summary = user_summary or default_summary

    # 单次压缩封面图供全平台复用（≤350KB）
    work_dir = Path(tempfile.mkdtemp(prefix="social_all_"))
    shared_cover = work_dir / "cover_shared.jpg"
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "65", "-Z", "1200", str(cover_path), "--out", str(shared_cover)], capture_output=True)
    if not shared_cover.exists():
        shared_cover = cover_path

    # 生成博客地址（若文章名符合规范）
    blog_slug = md_path.stem.lower()
    import urllib.parse
    blog_url = f"https://blog.sun90920.workers.dev/now/{urllib.parse.quote(blog_slug)}"

    # 生成微内容（微博/即刻/X）
    bullet_text = "\n".join(f"{i+1}. {q.strip()}" for i, q in enumerate(quotes[:3])) if quotes else ""
    social_text = f"{title}\n\n{bullet_text}\n\n完整记录：{blog_url}" if bullet_text else f"{title}\n\n{summary}\n\n完整记录：{blog_url}"

    # 生成小红书正文与卡片
    xhs_file = work_dir / "xhs_content.md"
    xhs_body = f"{title}\n\n" + (bullet_text or summary) + "\n\n详细配置与记录见博客长文。"
    xhs_file.write_text(xhs_body, encoding="utf-8")

    # 生成 X thread 分片文件
    xthread_dir = Path("/tmp/xthread")
    shutil.rmtree(xthread_dir, ignore_errors=True)
    xthread_dir.mkdir(parents=True, exist_ok=True)
    p1 = f"{title}。核心是「数据共享，进程解耦」：电脑端吃终端 ANSI 控制字符，手机端吃结构化数据；移动端弱网解耦保护电脑长任务；云端 Prompt Cache 认文字哈希，5分钟内切换无感不降速。"
    p2 = f"详细配置与踩坑实录：{blog_url}"
    (xthread_dir / "part1.txt").write_text(p1, encoding="utf-8")
    (xthread_dir / "part2.txt").write_text(p2, encoding="utf-8")
    Path("/tmp/xfg-session").write_text("xfg-all-publish", encoding="utf-8")

    return {
        "title": title,
        "summary": summary,
        "raw_md_path": md_path,
        "shared_cover": shared_cover,
        "social_text": social_text,
        "xhs_file": xhs_file,
        "work_dir": work_dir,
    }


def publish_weibo(assets, execute):
    t0 = time.time()
    cmd = [PYTHON, str(HERE / "weibo_post.py"), assets["social_text"], "--image", str(assets["shared_cover"])]
    if execute:
        cmd.append("--execute")
    rc, out = run_cmd(cmd, timeout=45)
    return "weibo", rc == 0, time.time() - t0, out


def publish_jike(assets, execute):
    t0 = time.time()
    cmd = [OPENCLI, "jike", "create", assets["social_text"], "--images", str(assets["shared_cover"]), "-f", "json"]
    if not execute:
        cmd.extend(["--dry-run", "true"])
    rc, out = run_cmd(cmd, timeout=90)
    return "jike", rc == 0, time.time() - t0, out


def publish_weixin(assets, execute):
    t0 = time.time()
    cmd = [
        PYTHON, str(HERE / "mp_draft.py"), str(assets["raw_md_path"]),
        "--title", assets["title"], "--summary", assets["summary"],
        "--cover", str(assets["shared_cover"])
    ]
    if execute:
        cmd.append("--execute")
    rc, out = run_cmd(cmd, timeout=180)
    return "weixin", rc == 0, time.time() - t0, out


def publish_toutiao(assets, execute):
    t0 = time.time()
    # 头条标题限制 30 字
    tt_title = assets["title"][:30]
    cmd = [
        PYTHON, str(HERE / "toutiao_post.py"), str(assets["raw_md_path"]),
        "--title", tt_title, "--cover", str(assets["shared_cover"])
    ]
    if execute:
        cmd.append("--execute")
    rc, out = run_cmd(cmd, timeout=90)
    return "toutiao", rc == 0, time.time() - t0, out


def publish_baijiahao(assets, execute):
    t0 = time.time()
    cmd = [
        PYTHON, str(HERE / "bjh_post.py"), str(assets["raw_md_path"]),
        "--title", assets["title"], "--cover", str(assets["shared_cover"])
    ]
    if execute:
        cmd.append("--execute")
    rc, out = run_cmd(cmd, timeout=90)
    return "baijiahao", rc == 0, time.time() - t0, out


def publish_xiaohongshu(assets, execute):
    t0 = time.time()
    cards = "为什么是两个客户端？\n手机和电脑并没有互相镜像屏幕，而是各自启动了独立的命令行。底层以本地磁盘的会话记录为唯一真源，切换设备等价于自动执行了一次会话恢复。|||为什么不能共用进程？\n电脑终端需要计算光标跳动与ANSI字符流；手机界面需要解析原生卡片与气泡。两套渲染逻辑天生冲突，强行捏在一起只会乱码。此外手机弱网断线也不会连带拖垮电脑。|||切换会丢失缓存吗？\n只要切换间隔在5分钟内，云端提示词缓存完全不丢。服务端Prompt Cache只根据上下文文字计算哈希，根本不认本地换没换客户端，切换无感不降速。"
    xhs_title = assets["title"][:20]
    cmd = [
        PYTHON, str(HERE / "xhs_note.py"), str(assets["xhs_file"]),
        "--title", xhs_title, "--cover", str(assets["shared_cover"]),
        "--cards", cards
    ]
    if execute:
        cmd.append("--execute")
    rc, out = run_cmd(cmd, timeout=120)
    return "xiaohongshu", rc == 0, time.time() - t0, out


def publish_twitter(assets, execute):
    t0 = time.time()
    if not execute:
        return "twitter", True, time.time() - t0, "（预演结束，未碰页面。确认后加 --execute 真发）"
    cmd = [PYTHON, str(HERE / "x_thread" / "publish_thread.py"), "1"]
    rc, out = run_cmd(cmd, timeout=120)
    # 关闭 tab
    run_cmd([OPENCLI, "browser", "xfg-all-publish", "close"], timeout=10)
    return "twitter", rc == 0, time.time() - t0, out


DISPATCHERS = {
    "weibo": publish_weibo,
    "jike": publish_jike,
    "weixin": publish_weixin,
    "toutiao": publish_toutiao,
    "baijiahao": publish_baijiahao,
    "xiaohongshu": publish_xiaohongshu,
    "twitter": publish_twitter,
}


def main():
    parser = argparse.ArgumentParser(description="全平台一键发布主控调度器")
    parser.add_argument("markdown", help="Markdown 源文章路径")
    parser.add_argument("--cover", required=True, help="封面图片路径")
    parser.add_argument("--title", default="", help="覆盖标题")
    parser.add_argument("--summary", default="", help="覆盖摘要")
    parser.add_argument("--platforms", default=",".join(ALL_PLATFORMS), help="指定发布平台，逗号隔开")
    parser.add_argument("--execute", action="store_true", help="真实发布（默认只预演）")
    args = parser.parse_args()

    md_path = Path(args.markdown).resolve()
    cover_path = Path(args.cover).resolve()
    if not md_path.exists():
        print(f"❌ 文章不存在: {md_path}", file=sys.stderr)
        sys.exit(1)
    if not cover_path.exists():
        print(f"❌ 封面不存在: {cover_path}", file=sys.stderr)
        sys.exit(1)

    selected = [p.strip() for p in args.platforms.split(",") if p.strip() in DISPATCHERS]
    mode_desc = "🚀 【正式发布】" if args.execute else "🔍 【全平台预演 (Dry Run)】"
    print(f"==================================================")
    print(f" {mode_desc}")
    print(f" 目标平台: {', '.join(selected)}")
    print(f"==================================================")

    t_all_start = time.time()
    assets = prepare_shared_assets(md_path, cover_path, args.title, args.summary)
    print(f"[*] 资产就绪: 《{assets['title']}》 | 统一封面: {assets['shared_cover'].stat().st_size // 1024}KB")

    results = {}

    # 1. 先锋轻量组：微博（纯 HTTP，不占浏览器）
    if "weibo" in selected:
        print("[*] 正在分发: 微博 (纯 HTTP 极速通道)...")
        name, ok, elapsed, out = publish_weibo(assets, args.execute)
        results[name] = (ok, elapsed, out)
        status_sym = "✅" if ok else "❌"
        print(f"  {status_sym} 微博完成 ({elapsed:.1f}s)")
        selected.remove("weibo")

    # 2. 浏览器受控并发流水线 (max_workers=2)
    if selected:
        print(f"[*] 启动浏览器流水线 (并发度=2，调度 {len(selected)} 个平台)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_plat = {
                executor.submit(DISPATCHERS[plat], assets, args.execute): plat
                for plat in selected
            }
            for fut in concurrent.futures.as_completed(future_to_plat):
                plat = future_to_plat[fut]
                try:
                    name, ok, elapsed, out = fut.result()
                    results[name] = (ok, elapsed, out)
                    status_sym = "✅" if ok else "❌"
                    print(f"  {status_sym} {name} 完成 ({elapsed:.1f}s)")
                except Exception as exc:
                    results[plat] = (False, 0, str(exc))
                    print(f"  ❌ {plat} 异常: {exc}")

    total_elapsed = time.time() - t_all_start
    print(f"\n==================================================")
    print(f"[*] 全流程执行完毕，总耗时: {total_elapsed:.1f}s")
    print(f"==================================================")

    # 打印结果表
    for name, (ok, elapsed, out) in sorted(results.items()):
        status_sym = "✅ 成功" if ok else "❌ 失败"
        detail = ""
        # 尝试从 output 提取链接或状态
        m_url = re.search(r"https?://\S+", out)
        if m_url:
            detail = m_url.group(0).rstrip('"\')')
        elif "草稿已建" in out or "草稿" in out:
            detail = "草稿已保存"
        elif "动态发布成功" in out:
            detail = "动态已发送"
        elif "发布成功" in out:
            detail = "已发布"
        else:
            detail = out[:80].replace("\n", " ").strip()
        print(f"- **{name}** [{status_sym}] ({elapsed:.1f}s): {detail}")

    # 清理临时工作目录
    shutil.rmtree(assets["work_dir"], ignore_errors=True)

if __name__ == "__main__":
    main()
