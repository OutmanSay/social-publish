---
name: social-publish
description: >
  社交平台发布与发布状态检查。凡用户要发微博、X/Twitter、即刻、知乎、公众号，
  跨平台同步，或询问某条是否发出、平台是否登录，都必须使用本技能。
  流程包含确认门、只读 preflight、无 computer-use 登录恢复、确定性发布与归档。
metadata:
  openclaw:
    emoji: "📢"
    aliases: ["发帖", "发布", "publish", "cross-post", "weibo-publish"]
    requires:
      bins: ["python3", "opencli"]
---

# Social Publish

本目录是 OpenClaw、Hermes、Pi、Claude Code、OpenCode、Codex 的共享发布真源。不要为某个 Agent 另写一套发布流程。

## 不可破坏的规则

- 每次不可逆发布前，必须取得用户对最终正文和平台的明确确认。
- 默认只预演；只有统一脚本的 `--execute` 可以触发真实发布。
- 社交发布和登录恢复禁止使用 `computer_use`、截图点击、坐标点击或键盘模拟。它们慢且容易把错误页面误判成登录失败。
- 浏览器登录刷新只使用 OpenCLI Browser Bridge 的后台标签页；cookie 有效时直接走 HTTP/OpenCLI，不打开浏览器。
- 同一失败最多自动修复一次。未知失败、提交超时或返回不明确时停止，不盲重试，以免重复发布。
- 不把 selector/timeout/adapter 错误说成“未登录”。按下表分类后报告。

## 标准入口

所有 Agent 都应调用这里的确定性脚本，不要自行拼接 `open -a Chrome` 或直接操控页面。`<SKILL_DIR>` 指本目录。

```bash
# 默认检查微博、X、即刻；只读，不发布
python3 <SKILL_DIR>/preflight.py --repair --deep

# 指定平台检查；all 也包含知乎和公众号
python3 <SKILL_DIR>/preflight.py --platform all --repair --deep

# 统一预演：不加 --execute 永远不发布
python3 <SKILL_DIR>/publish.py \
  --platform weibo --platform twitter --platform jike \
  --content-file /tmp/social-post.txt

# 用户已明确确认最终正文和平台后才可执行
python3 <SKILL_DIR>/publish.py \
  --platform weibo --platform twitter --platform jike \
  --content-file /tmp/social-post.txt --execute
```

优先使用 `--content-file`，避免长文本经过 shell 引号后变形。创建临时正文文件时不要覆盖用户文件。

## 失败分类

| category | 含义 | 处理 |
|---|---|---|
| `auth` | cookie/登录态确实缺失 | Browser Bridge 后台打开对应站点，等待后复检一次 |
| `adapter` | DOM selector/composer 不可用 | 刷新后台页面并复检一次；仍失败则报告适配器故障 |
| `timeout` | 请求或页面超时 | 不自动再次发布；先核对是否已经产生外链 |
| `missing_dependency` | 本机命令缺失 | 报告具体依赖，不改用 computer use |
| `unknown` | 无法证明原因 | 原样报告精简错误，不推断成未登录 |

## 主流程

1. 轻整理用户原文，保留语气；不擅自加 hashtag、emoji 或营销腔。
2. 展示最终正文与平台，取得一次明确确认。跨平台一次确认即可。
3. 把最终正文写入临时文件。
4. 先运行 `publish.py` 预演，核对 X 拆分结果和目标平台。
5. 确认仍有效后加 `--execute`。脚本会运行 preflight，并仅对可证明发生在提交前的 composer 故障重试一次。
6. 逐平台报告真实结果。部分成功时明确列出成功与失败平台，不把整体说成全失败。
7. 成功后归档（位置自定）。

## 平台实现

| 平台 | 实现 | 注意事项 |
|---|---|---|
| 微博 | `weibo_post.py` 读取 Chrome 指定 Profile 的 cookie，HTTP 发布 | 环境变量 `WEIBO_CHROME_PROFILE`、`WEIBO_UID`；脚本自身也要求 `--execute` |
| X | OpenCLI Twitter adapter | 统一脚本按加权长度安全拆 Thread |
| 即刻 | OpenCLI Jike adapter | |
| 知乎 | `opencli zhihu answer` | 问题回答；单独按最终答案确认后执行 |
| 公众号 | `opencli weixin create-draft` | 只创建草稿，最终发布仍需人工操作 |

不要把 Chrome 里肉眼可见的登录状态当作 cookie 证明（可能登在另一个 Profile），以 `preflight.py` 结果为准。

## 知乎与公众号

当前统一 `publish.py` 只覆盖微博、X、即刻。知乎需要问题 URL，公众号需要标题/摘要，参数语义不同，继续使用对应 OpenCLI 命令，但仍遵守确认门和 `preflight.py`：

```bash
opencli zhihu whoami
opencli zhihu answer <问题URL> "回答内容"        # 预览
opencli zhihu answer <问题URL> "回答内容" --execute

opencli weixin drafts
opencli weixin create-draft "正文" --title "标题" --summary "摘要"
```
