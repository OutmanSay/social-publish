# social-publish 📢

> 🧠 **AI Agent Skill** — Let your agent cross-post to Weibo, Jike, Zhihu, WeChat Official Accounts and Xiaohongshu, with a confirmation gate and no silent failures.
> Works with [OpenClaw](https://github.com/openclaw/openclaw) · [Claude Code](https://claude.com/claude-code) · and any agent runtime that can shell out.

**写完一篇，跟 AI 说"全平台发"，它把微博、即刻、知乎、公众号草稿、小红书都办了。每一步要么真成功，要么明确报失败。**

---

## What's this?

这是一个 **AI agent skill**：一套确定性发布脚本 + 给 agent 读的操作规程（`SKILL.md`）。

跟你的 agent 说：
- *"这段发微博和即刻"* → agent 预演、给你看最终正文，你说"发"才真发
- *"这篇全平台发一下"* → 微博/即刻带图发出，知乎自己找合适的问题挂靠，公众号做成打开就能点发表的草稿，小红书封面 + 文字卡
- *"微博还登着吗"* → agent 跑只读 preflight

**为什么要脚本而不是让 agent 直接点网页**：模型读文档会漏（弱模型常常只读前 80 行），网页操作会把错误页误判成成功。所以规则写成代码：不带 `--execute` 不发，封面没设上就报错，配图不存在就停，失败不静默降级。

## 平台

| 平台 | 方式 | 能力 |
|---|---|---|
| 微博 | 读 Chrome cookie + HTTP | 文字 + 多图，`--rehearse` 真上传图片但不发 |
| 即刻 | opencli（补丁） | 文字 + 多图，`--dry-run` 填好再清空 |
| 今日头条 | opencli | 标题 ≤30 字长文图文，自动开启广告收益分成 |
| 百家号 | opencli | 富文本图文，单图封面，支持存草稿/直接发布 |
| 知乎 | opencli | 回答问题（发了删不掉，先定稿） |
| 公众号 | opencli（补丁） | 草稿：标题/作者/摘要/封面四件齐，配图在正文顶部 |
| 小红书 | opencli（补丁） | 封面 + 本地渲染文字卡 |
| X | opencli | 短帖可用，多段落长帖不可用（见 SKILL.md） |

## 快速开始

依赖：macOS、Python 3、[opencli](https://github.com/jackwener/opencli)（含 Browser Bridge 扩展）、`pip install browser_cookie3 pillow`。

```bash
git clone https://github.com/OutmanSay/social-publish.git
cd social-publish
python3 apply_patches.py          # 装适配器补丁，npm update opencli 后重跑

export WEIBO_CHROME_PROFILE="Default"   # 登着 weibo.com 的 Chrome Profile 目录名
export WEIBO_UID="你的微博UID"
export MP_AUTHOR="公众号作者名"

python3 preflight.py --platform all --deep                          # 只读检查登录态
python3 publish.py --platform weibo --text "测试预演"                 # 预演，不发
python3 mp_draft.py 文章.md --title 标题 --summary 摘要 --cover 封面.png  # 预演，不建草稿
```

把目录放进 agent 的 skills 目录（如 `~/.claude/skills/social-publish`），agent 就会按 `SKILL.md` 走。

## 文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 给 agent 的规程：确认门、失败分类、各平台坑 |
| `preflight.py` | 只读登录态检查，`--repair` 用后台标签页刷新 |
| `publish.py` | 微博/即刻/X 统一发布，默认预演 |
| `weibo_post.py` | 微博 HTTP 发帖、传图、`--check`、`--list` |
| `mp_draft.py` | 公众号草稿一条命令，含封面核验 |
| `md2plain.py` | Markdown → 公众号可用纯文本 |
| `xhs_note.py` | 小红书图文，三档：预演 / 存草稿核验 / 发布 |
| `render_cards.py` | 本地渲染小红书文字卡 |
| `apply_patches.py`, `patches/` | opencli 适配器补丁（Apache-2.0，见 `patches/README.md`） |

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)。git 历史里保留了能找到原文件的三个快照（2026-08-28、2026-09-13、2026-09-14），更早的版本没有留存文件，只在 CHANGELOG 里记了变化。

## License

MIT（`patches/` 下的 opencli 修改版为 Apache-2.0）。
