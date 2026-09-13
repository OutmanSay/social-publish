#!/usr/bin/env python3
"""本地渲染小红书文字卡（不靠平台「文字配图」，字一个不会糊）。

风格对齐 mono-color：暖灰纸底 + 单色靛蓝墨 + 大留白。1080x1440（3:4）。
每张卡：第一行当标题（大字），其余当正文；卡内换行用 \\n。

python3 render_cards.py --cards "标题\\n正文|||标题2\\n正文2" --out-dir DIR
→ 输出 DIR/card-01.jpg ...，每行打印一个路径
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
PAPER = (237, 234, 227)
INK = (27, 42, 91)
MARGIN = 96
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def wrap(draw, text, f, width):
    lines = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            if draw.textlength(line + ch, font=f) > width:
                lines.append(line)
                line = ch
            else:
                line += ch
        lines.append(line)
    return lines


def render(card, idx, total, out):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    parts = card.replace("\\n", "\n").split("\n", 1)
    title, body = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    width = W - 2 * MARGIN

    d.text((MARGIN, MARGIN), f"{idx:02d} / {total:02d}", font=font(30), fill=INK)
    y = MARGIN + 150
    tf = font(76, bold=True)
    for line in wrap(d, title, tf, width):
        d.text((MARGIN, y), line, font=tf, fill=INK)
        y += 104
    y += 30
    d.rectangle([MARGIN, y, MARGIN + 120, y + 8], fill=INK)
    y += 70
    bf = font(44)
    for line in wrap(d, body, bf, width):
        if y > H - MARGIN - 80:
            raise SystemExit(f"❌ 第 {idx} 张卡字太多放不下，拆成两张")
        d.text((MARGIN, y), line, font=bf, fill=INK)
        y += 72
    d.line([MARGIN, H - MARGIN - 40, W - MARGIN, H - MARGIN - 40], fill=INK, width=2)
    img.save(out, quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    cards = [c.strip() for c in a.cards.split("|||") if c.strip()]
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(cards, 1):
        p = out_dir / f"card-{i:02d}.jpg"
        render(c, i, len(cards), p)
        print(p)


if __name__ == "__main__":
    main()
