#!/usr/bin/env python3
"""Markdown → 公众号纯文本正文。

公众号编辑器是 ProseMirror，create-draft 走 insertText，Markdown 符号会原样显示。
用法：python3 md2plain.py 文章.md > 正文.txt
"""
import re
import sys

CN_NUM = "一二三四五六七八九十"


def convert(md: str) -> str:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)  # frontmatter
    out, h2 = [], 0
    for line in md.splitlines():
        s = line.rstrip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            text = m.group(2)
            if len(m.group(1)) == 2 and h2 < len(CN_NUM):
                text = f"{CN_NUM[h2]}、{text}"
                h2 += 1
            s = text
        s = re.sub(r"^\s*>\s?", "", s)                      # 引用
        s = re.sub(r"^\s*[-*+]\s+", "· ", s)                # 无序列表
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)          # 图片
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)      # 链接
        s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)           # 粗体
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", s)  # 斜体
        s = re.sub(r"`([^`]+)`", r"\1", s)                  # 行内代码
        if re.fullmatch(r"\s*([-*_]\s*){3,}", s):           # 分隔线
            s = ""
        out.append(s)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    sys.stdout.write(convert(src))
