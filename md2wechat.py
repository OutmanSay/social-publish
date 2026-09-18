#!/usr/bin/env python3
"""Markdown 转微信公众号内联样式富文本 HTML（多主题支持）。"""
import re
import html
import sys

THEMES = {
    "minimal-green": {
        "name": "极简绿标（默认款）",
        "primary": "#07c160",
        "text": "#333333",
        "muted_text": "#666666",
        "border_quote": "#07c160",
        "code_bg": "#f4f4f5",
        "code_color": "#0969da",
        "pre_bg": "#24292e",
        "pre_color": "#e1e4e8",
        "h2_style": "margin: 32px 0 16px 0; font-size: 18px; font-weight: bold; color: #111827; border-bottom: 2px solid #07c160; padding-bottom: 6px; display: table;",
        "h3_style": "margin: 24px 0 12px 0; font-size: 16.5px; font-weight: bold; color: #1f2937; border-left: 3px solid #07c160; padding-left: 10px;",
        "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;",
    },
    "latepost": {
        "name": "晚点风格（严肃商业深红）",
        "primary": "#d32f2f",
        "text": "#1a1a1a",
        "muted_text": "#4a4a4a",
        "border_quote": "#d32f2f",
        "code_bg": "#f5f5f5",
        "code_color": "#d32f2f",
        "pre_bg": "#2a2a2a",
        "pre_color": "#f5f5f5",
        "h2_style": "margin: 32px 0 16px 0; font-size: 18.5px; font-weight: 700; color: #1a1a1a; border-bottom: 2px solid #d32f2f; padding-bottom: 6px; display: table;",
        "h3_style": "margin: 24px 0 12px 0; font-size: 16.5px; font-weight: 700; color: #d32f2f; border-left: 4px solid #d32f2f; padding-left: 10px;",
        "font_family": "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;",
    },
    "medium": {
        "name": "Medium长文（典雅衬线随笔）",
        "primary": "#757575",
        "text": "#242424",
        "muted_text": "#666666",
        "border_quote": "#9ca3af",
        "code_bg": "#f4f4f5",
        "code_color": "#242424",
        "pre_bg": "#292929",
        "pre_color": "#f0f0f0",
        "h2_style": "margin: 34px 0 16px 0; font-size: 19px; font-weight: 700; color: #1a1a1a; font-family: Georgia, 'Times New Roman', serif; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; width: 100%;",
        "h3_style": "margin: 26px 0 12px 0; font-size: 17px; font-weight: 700; color: #242424; font-family: Georgia, 'Times New Roman', serif; border-left: 3px solid #757575; padding-left: 10px;",
        "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;",
    },
    "apple": {
        "name": "Apple极简（科技冷灰蓝）",
        "primary": "#0071e3",
        "text": "#1d1d1f",
        "muted_text": "#6e6e73",
        "border_quote": "#0071e3",
        "code_bg": "#f5f5f7",
        "code_color": "#0071e3",
        "pre_bg": "#1d1d1f",
        "pre_color": "#f5f5f7",
        "h2_style": "margin: 34px 0 16px 0; font-size: 18.5px; font-weight: 600; color: #1d1d1f; border-bottom: 2px solid #0071e3; padding-bottom: 6px; display: table;",
        "h3_style": "margin: 24px 0 12px 0; font-size: 16.5px; font-weight: 600; color: #1d1d1f; border-left: 3px solid #0071e3; padding-left: 10px;",
        "font_family": "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif;",
    }
}

DEFAULT_THEME = "minimal-green"

def md_to_wechat_html(md_text: str, theme_name: str = DEFAULT_THEME) -> str:
    theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    # 1. 去除 frontmatter
    md_text = re.sub(r"^---\n.*?\n---\n+", "", md_text, flags=re.DOTALL)

    lines = md_text.splitlines()
    html_blocks = []

    in_code_block = False
    code_lines = []
    code_lang = ""

    in_quote = False
    quote_lines = []

    in_list = False
    list_items = []
    list_ordered = False

    def flush_list():
        nonlocal in_list, list_items, list_ordered
        if not in_list:
            return
        tag = "ol" if list_ordered else "ul"
        style = "margin: 16px 0; padding-left: 24px; color: %s; font-size: 15.5px; line-height: 1.8;" % theme["text"]
        lis = "".join('<li style="margin-bottom: 6px;">%s</li>' % parse_inline(item) for item in list_items)
        html_blocks.append('<%s style="%s">%s</%s>' % (tag, style, lis, tag))
        in_list = False
        list_items = []

    def flush_quote():
        nonlocal in_quote, quote_lines
        if not in_quote:
            return
        # 极简无框纯净版：左侧严格 100% 垂直对齐，去除任何首行悬挂空格
        style = (
            "margin: 20px 0; padding: 2px 0 2px 12px; border-left: 3px solid %s; "
            "color: %s; font-size: 15px; line-height: 1.8;"
        ) % (theme["border_quote"], theme["muted_text"])
        lines_clean = [l.strip() for l in quote_lines if l.strip()]
        paras = "".join(
            '<p style="margin: 0 0 %spx 0; padding: 0; text-indent: 0;">%s</p>' % (
                "6" if idx < len(lines_clean) - 1 else "0",
                parse_inline(l)
            )
            for idx, l in enumerate(lines_clean)
        )
        html_blocks.append('<blockquote style="%s">%s</blockquote>' % (style, paras))
        in_quote = False
        quote_lines = []

    def parse_inline(text: str) -> str:
        text = re.sub(r"`([^`]+)`", r'<code style="background: %s; color: %s; padding: 2px 6px; border-radius: 4px; font-size: 13.5px; font-family: Menlo, Monaco, monospace;">\1</code>' % (theme["code_bg"], theme["code_color"]), text)
        text = re.sub(r"\*\*([^*]+)\*\*", r'<strong style="color: %s; font-weight: bold;">\1</strong>' % theme["text"], text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" style="color: %s; text-decoration: underline;">\1</a>' % theme["primary"], text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if in_code_block:
                code_content = html.escape("\n".join(code_lines))
                style = (
                    "margin: 20px 0; padding: 14px 16px; background: %s; color: %s; "
                    "border-radius: 6px; font-size: 13px; line-height: 1.6; overflow-x: auto; "
                    "font-family: Menlo, Monaco, Consolas, monospace;"
                ) % (theme["pre_bg"], theme["pre_color"])
                html_blocks.append('<pre style="%s"><code>%s</code></pre>' % (style, code_content))
                in_code_block = False
                code_lines = []
            else:
                flush_list()
                flush_quote()
                in_code_block = True
                code_lang = stripped[3:].strip()
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 引用块
        if stripped.startswith(">"):
            flush_list()
            in_quote = True
            quote_lines.append(stripped[1:].strip())
            i += 1
            continue
        elif in_quote:
            flush_quote()

        # 列表
        m_ul = re.match(r"^[-*]\s+(.*)$", stripped)
        m_ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_ul:
            if not in_list or list_ordered:
                flush_list()
                in_list = True
                list_ordered = False
            list_items.append(m_ul.group(1))
            i += 1
            continue
        elif m_ol:
            if not in_list or not list_ordered:
                flush_list()
                in_list = True
                list_ordered = True
            list_items.append(m_ol.group(1))
            i += 1
            continue
        elif in_list:
            flush_list()

        # 标题
        if stripped.startswith("## "):
            html_blocks.append('<h2 style="%s">%s</h2>' % (theme["h2_style"], parse_inline(stripped[3:].strip())))
            i += 1
            continue
        elif stripped.startswith("### "):
            html_blocks.append('<h3 style="%s">%s</h3>' % (theme["h3_style"], parse_inline(stripped[4:].strip())))
            i += 1
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落
        p_style = "margin: 0 0 16px 0; font-size: 15.5px; color: %s; line-height: 1.85; text-align: justify; letter-spacing: 0.5px;" % theme["text"]
        html_blocks.append('<p style="%s">%s</p>' % (p_style, parse_inline(stripped)))
        i += 1

    flush_list()
    flush_quote()

    container_style = (
        "font-family: %s; padding: 0 4px; box-sizing: border-box;"
    ) % theme["font_family"]
    return '<section style="%s">%s</section>' % (container_style, "".join(html_blocks))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Markdown 转微信公众号内联富文本")
    parser.add_argument("file", help="Markdown 文件路径")
    parser.add_argument("--theme", default=DEFAULT_THEME, choices=list(THEMES.keys()), help="选择排版主题")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as f:
        print(md_to_wechat_html(f.read(), theme_name=args.theme))
