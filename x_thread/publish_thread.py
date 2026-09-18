#!/usr/bin/env python3
"""X thread 发布（2026-09-14 跑通的版本 + 回复链修复）。

⭐ 两个决定性因素（缺一不可，见 memory: x-thread-publish-working）：
  1. 窗口必须 --window foreground —— background 打开的标签会被回收成 about:blank，
     报错却伪装成 "no box" / "verify failed"，极难排查。
  2. 用 execCommand('insertText') 一步注入 —— opencli browser type 会返回
     {"typed": true} 但文字没进（X 页面重渲染使 ref 失效）。

用法：
  echo "xfg-<name>" > /tmp/xfg-session          # session 名
  python3 publish_thread.py 1                    # 从第 1 条开始发
  python3 publish_thread.py 3 <第2条的URL>        # 从第 3 条续发

  ⚠️ 待发内容放 /tmp/xthread/part1.txt ... partN.txt（每条必须单段落、≤280 加权字符）
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ENV = dict(os.environ, OPENCLI_BROWSER_COMMAND_TIMEOUT="120")
STATUS = re.compile(r"/status/(\d+)")
VIS = "var v=function(e){return !!e&&(e.offsetParent!==null||e.getClientRects().length>0)};"


def run(*a, t=180):
    return subprocess.run(["opencli", *a], capture_output=True, text=True, timeout=t, env=ENV)


def ev(session, js, t=180):
    r = run("browser", session, "eval", js, t=t)
    return (r.stdout or "").strip()


def inject(session, text):
    """一步注入 + 读回校验。返回 dict。"""
    js = """
    (async function(){
      var txt=%s;
      %s
      function pick(){var a=Array.from(document.querySelectorAll('[data-testid="tweetTextarea_0"]')).filter(v);
        return a.sort(function(x,y){return y.getBoundingClientRect().height-x.getBoundingClientRect().height})[0];}
      var b=null; for(var i=0;i<30;i++){b=pick(); if(b)break; await new Promise(r=>setTimeout(r,300));}
      if(!b) return JSON.stringify({err:'no box', url:location.href});
      b.focus();
      var s=window.getSelection(),rg=document.createRange();
      rg.selectNodeContents(b); s.removeAllRanges(); s.addRange(rg);
      document.execCommand('delete');
      document.execCommand('insertText', false, txt);
      await new Promise(r=>setTimeout(r,500));
      return JSON.stringify({match:(b.innerText||'')===txt, len:(b.innerText||'').length});
    })()
    """ % (json.dumps(text), VIS)
    out = ev(session, js)
    try:
        return json.loads(out)
    except Exception:
        return {"err": "非JSON返回", "raw": out[:200]}



    """点 Post。文本注入后按钮会有一小段 disabled，必须轮询等它变可用，
    否则报 {'err':'disabled'}（实测踩过 —— 注入成功但点不动）。"""
    js = """
    (async function(){
      %s
      for (var i=0;i<20;i++){
        var btns=Array.from(document.querySelectorAll('[data-testid="tweetButtonInline"],[data-testid="tweetButton"]'));
        var b=btns.find(v);
        if(b){
          var st=b.getAttribute('aria-disabled')||b.disabled;
          if(st!=='true'&&st!==true){ b.click(); return JSON.stringify({clicked:true, waited:i}); }
        }
        await new Promise(r=>setTimeout(r,250));
      }
      return JSON.stringify({err:'disabled-20tries'});
    })()
    """ % VIS
    out = ev(session, js)
    try:
        return json.loads(out)
    except Exception:
        return {"err": "非JSON返回", "raw": out[:200]}


def latest_status_id(session, after_id=None):
    """取最新一条帖子的 status id。

    ⚠️ 绝不能简单地 --limit 1 就取——发完第 N 条后"最新"就是 N 条自己，
    会让后续全部 reply 到 N，第 1 条被孤立（2026-09-14 实际踩过）。
    这里显式要求 id != after_id（上一条的 id），并只在取不到时告警。
    """
    for _ in range(4):
        r = run("twitter", "tweets", os.environ.get("X_HANDLE", ""), "--limit", "5", "-f", "json", t=180)
        try:
            items = json.loads(r.stdout or "[]")
        except Exception:
            items = []
        ids = [str(t.get("id")) for t in items if t.get("id")]
        if ids:
            # ⚠️ 不能取 ids[0]！twitter tweets 的返回顺序不保证（实测按时间正序，
            # 最旧在前），取 [0] 会永远拿到最旧的那条，导致后续全部 reply 到它。
            # Twitter status id 是 snowflake（数值单调递增）⇒ 取数值最大者即最新。
            newest = max(ids, key=lambda x: int(x))
            if after_id is None or newest != str(after_id):
                return newest
        time.sleep(1)
    return None


def clear_composer(session):
    """清空编辑器。⭐ 必须在【任何】失败路径上调用 —— x.com 只在编辑器有内容时
    注册 beforeunload，残留草稿会让之后任何导航/关窗弹出 Chrome 原生确认框
    （那个框由浏览器自己渲染，脚本够不着，没人点会冻住整个浏览器）。"""
    js = ("(function(){%s"
          "var a=Array.from(document.querySelectorAll('[data-testid=\"tweetTextarea_0\"]')).filter(v);"
          "var b=a.sort(function(x,y){return y.getBoundingClientRect().height-x.getBoundingClientRect().height})[0];"
          "if(!b) return JSON.stringify({ok:true,note:'no box'});"
          "b.focus();var s=window.getSelection(),rg=document.createRange();"
          "rg.selectNodeContents(b);s.removeAllRanges();s.addRange(rg);"
          "document.execCommand('delete');"
          "return JSON.stringify({ok:(b.innerText||'').trim()===''})})()") % VIS
    try:
        return json.loads(ev(session, js, t=60))
    except Exception:
        return {"ok": False}


def click_post(session):
    """点 Post。⭐ 文本注入后按钮会短暂 disabled，必须轮询等它变可用 ——
    实测直接点会报 {'err':'disabled'}（注入成功了却点不动）。"""
    js = ("(async function(){%s"
          "for(var i=0;i<20;i++){"
          "var btns=Array.from(document.querySelectorAll('[data-testid=\"tweetButtonInline\"],[data-testid=\"tweetButton\"]'));"
          "var b=btns.find(v);"
          "if(b){var st=b.getAttribute('aria-disabled')||b.disabled;"
          "if(st!=='true'&&st!==true){b.click();return JSON.stringify({clicked:true,waited:i})}}"
          "await new Promise(r=>setTimeout(r,250));}"
          "return JSON.stringify({err:'disabled-20tries'})})()") % VIS
    out = ev(session, js)
    try:
        return json.loads(out)
    except Exception:
        return {"err": "非JSON返回", "raw": out[:200]}


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    session = Path("/tmp/xfg-session").read_text().strip() if Path("/tmp/xfg-session").exists() else "xfg"
    parent_id = None
    if len(sys.argv) > 2 and sys.argv[2]:
        m = STATUS.search(sys.argv[2])
        if m:
            parent_id = m.group(1)

    parts = []
    i = 1
    while Path(f"/tmp/xthread/part{i}.txt").exists():
        parts.append(Path(f"/tmp/xthread/part{i}.txt").read_text(encoding="utf-8").strip())
        i += 1
    if not parts:
        print("❌ /tmp/xthread/part*.txt 不存在"); return 2

    # ⭐ 发之前校验：每条必须单段落、且不超 280 加权字符。
    # 理由（2026-09-14 实测）：execCommand('insertText') 会吞掉换行，带换行的内容
    # 要么注入后校验失败，要么发出残缺文本；超 280 会被 X 拒绝或截断。
    # 早先只在 docstring 里写了这条约束，代码不校验 —— 现在补上，避免带病发布。
    bad = False
    for n, text in enumerate(parts, 1):
        if "\n" in text:
            print(f"❌ part{n}.txt 含换行 —— 每条必须是单段落（insertText 会吞换行）")
            bad = True
        clean_text = re.sub(r'https?://\S+', 'x' * 23, text)
        w = sum(2 if ord(c) > 0x2E80 else 1 for c in clean_text)  # URL按Twitter t.co 23字符算，中文按双宽
        if w > 280:
            print(f"❌ part{n}.txt 加权长度 {w} > 280")
            bad = True
    if bad:
        print("⛔ 校验未通过，未发布任何内容。修好 /tmp/xthread/part*.txt 再跑。")
        return 3

    print(f"[*] session={session}  共 {len(parts)} 条  从第 {start} 条开始  parent={parent_id or '(无)'}")

    for n in range(start, len(parts) + 1):
        text = parts[n - 1]
        if n == 1 and not parent_id:
            url = "https://x.com/compose/post"
        else:
            if not parent_id:
                print(f"[{n}] ❌ 无 parent_id，停止（否则会断链）"); return 1
            url = f"https://x.com/compose/post?in_reply_to={parent_id}"
        # ⭐ foreground —— background 的标签会被回收
        run("browser", session, "open", url, "--window", "foreground", t=90)
        time.sleep(2)   # 实测 compose 页 2s 内可注入；原来拍 6s 纯浪费

        res = inject(session, text)
        print(f"[{n}] 注入 {res}")
        if res.get("err") or not res.get("match"):
            print(f"[{n}] ❌ 注入失败，停止")
            clear_composer(session)          # ⭐ 失败必须清空
            return 1

        cp = click_post(session)
        print(f"[{n}] 发布 {cp}")
        if cp.get("err"):
            print(f"[{n}] ❌ 点击 Post 失败")
            clear_composer(session)          # ⭐ 失败必须清空
            return 1
        time.sleep(2)   # 发帖 3s 内生效，2s 足够开始轮询

        new_id = latest_status_id(session, after_id=parent_id)
        if not new_id:
            print(f"[{n}] ⚠️ 取不到新帖 id，停止")
            clear_composer(session)          # ⭐ 失败必须清空
            return 1
        if str(new_id) == str(parent_id):
            print(f"[{n}] ⚠️ 最新 id 与 parent 相同 —— 可能没发出去，停止")
            clear_composer(session)          # ⭐ 失败必须清空
            return 1
        parent_id = new_id
        print(f"[{n}] ✅ id={parent_id}")
        time.sleep(1)

    print(f"[✓] 完成，最后一条 id={parent_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
