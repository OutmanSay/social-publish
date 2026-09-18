#!/usr/bin/env python3
"""Markdown 转微信公众号内联样式富文本 HTML。"""
import re
import html

THEME = {
    "primary": "#07c160",
    "text": "#333333",
    "bg_quote": "#f6f8fa",
    "border_quote": "#07c160",
    "code_bg": "#f1f5f9",
    "code_color": "#0284c7",
    "pre_bg": "#282c34",
    "pre_color": "#abb2bf",
}

def md_to_wechat_html(md_text: str, theme=THEME) -> str:
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
        style = (
            "margin: 20px 0; padding: 14px 18px; border-left: 4px solid %s; "
            "background: %s; border-radius: 4px; color: #555555; font-size: 15px; line-height: 1.75;"
        ) % (theme["border_quote"], theme["bg_quote"])
        content = "<br>".join(parse_inline(l) for l in quote_lines)
        html_blocks.append('<blockquote style="%s"><p style="margin: 0;">%s</p></blockquote>' % (style, content))
        in_quote = False
        quote_lines = []

    def parse_inline(text: str) -> str:
        # 代码
        text = re.sub(r"`([^`]+)`", r'<code style="background: %s; color: %s; padding: 2px 6px; border-radius: 4px; font-size: 13.5px; font-family: Menlo, Monaco, monospace;">\1</code>' % (theme["code_bg"], theme["code_color"]), text)
        # 加粗
        text = re.sub(r"\*\*([^*]+)\*\*", r'<strong style="color: #111111; font-weight: bold;">\1</strong>', text)
        # 链接
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" style="color: %s; text-decoration: underline;">\1</a>' % theme["code_color"], text)
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
            h2_style = (
                "margin: 32px 0 16px 0; font-size: 18px; font-weight: bold; color: #111827; "
                "border-bottom: 2px solid %s; padding-bottom: 6px; display: table;"
            ) % theme["primary"]
            html_blocks.append('<h2 style="%s">%s</h2>' % (h2_style, parse_inline(stripped[3:].strip())))
            i += 1
            continue
        elif stripped.startswith("### "):
            h3_style = (
                "margin: 24px 0 12px 0; font-size: 16.5px; font-weight: bold; color: #1f2937; "
                "border-left: 3px solid %s; padding-left: 10px;"
            ) % theme["primary"]
            html_blocks.append('<h3 style="%s">%s</h3>' % (h3_style, parse_inline(stripped[4:].strip())))
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
        "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; "
        "padding: 0 4px; box-sizing: border-box;"
    )
    return '<section style="%s">%s</section>' % (container_style, "".join(html_blocks))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            print(md_to_wechat_html(f.read()))
