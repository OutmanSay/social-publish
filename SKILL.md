---
name: social-publish
description: >
  社交平台发布与发布状态检查。凡用户要发微博、即刻、知乎、公众号、小红书，
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

本目录是 OpenClaw、Hermes、Pi、Claude Code、OpenCode、Codex 的共享发布真源。不要为某个 Agent 另写一套发布流程。`<SKILL_DIR>` 指本目录。

首次使用先装适配器补丁：`python3 <SKILL_DIR>/apply_patches.py`（`npm update` opencli 之后重跑）。

## 不可破坏的规则

- 每次不可逆发布前，必须取得用户对最终正文和平台的明确确认。
- 默认只预演；只有统一脚本的 `--execute` 可以触发真实发布。
- ⚠️「不带 `--execute` 就安全」**只对 `publish.py` / `weibo_post.py` / `mp_draft.py` 成立**。裸跑 `opencli jike create`（不带补丁的 `--dry-run true`）、`opencli xiaohongshu publish`（含 `--draft true`，会真存进创作平台草稿箱）**一跑就是真写**，所以即刻测试走 `publish.py --rehearse`；`opencli zhihu answer` 不带 `--execute` 会被拒。只要求预演时：微博、即刻跑 `publish.py --rehearse`，小红书跑 `xhs_note.py` 不加参数，知乎只写好内容和命令不跑。
- 社交发布和登录恢复禁止使用 `computer_use`、截图点击、坐标点击或键盘模拟。它们慢且容易把错误页面误判成登录失败。
- 浏览器登录刷新只使用 OpenCLI Browser Bridge 的后台标签页；cookie 有效时直接走 HTTP/OpenCLI，不打开浏览器。
- 同一失败最多自动修复一次。未知失败、提交超时或返回不明确时停止，不盲重试，以免重复发布。
- 不把 selector/timeout/adapter 错误说成“未登录”。按下表分类后报告。

## 标准入口

所有 Agent 都应调用这里的确定性脚本，不要自行拼接 `open -a Chrome` 或直接操控页面。

```bash
# 默认检查微博、X、即刻；只读，不发布
python3 <SKILL_DIR>/preflight.py --repair --deep

# 指定平台检查；all 也包含知乎和公众号
python3 <SKILL_DIR>/preflight.py --platform all --repair --deep

# 统一预演：不加 --execute 永远不发布
python3 <SKILL_DIR>/publish.py \
  --platform weibo --platform jike \
  --content-file /tmp/social-post.txt --image 封面.png

# ⭐ 彩排（测试用，不发帖）：微博真上传图片拿 pid；即刻真把图文填进发帖框、核验后清空
#   ... 同上命令加 --rehearse

# 用户已明确确认最终正文和平台后才可执行
python3 <SKILL_DIR>/publish.py \
  --platform weibo --platform jike \
  --content-file /tmp/social-post.txt --image 封面.png --execute
#   全平台发布时微博、即刻都带 --image（与公众号/小红书共用同一张封面），可多次传
#   配图不存在脚本直接报错；⛔ 不许去掉 --image 继续发
#   脚本自动把配图压到 ≤500KB jpg（即刻单图 >~700KB 必崩 sendCommand），传原图即可

# ⭐ 今日头条独立发布：标题 ≤30 字，自动开启广告收益
python3 <SKILL_DIR>/toutiao_post.py 文章.md \
  --title "标题（≤30字）" --cover 封面.jpg [--execute]

# ⭐ 百家号独立发布：Markdown→HTML，自动绑定封面
python3 <SKILL_DIR>/bjh_post.py 文章.md \
  --title "文章标题" --cover 封面.jpg [--draft|--execute]

# ⭐ 公众号草稿：只许用这一条，禁止手拼 opencli weixin create-draft
# 自动做：Markdown→纯文本、压封面、补丁自检、登录检查、验封面真设上；任一步失败非零退出
python3 <SKILL_DIR>/mp_draft.py 文章.md \
  --title "标题" --summary "一句话摘要" --cover 封面.png --author "作者"   # 预演
#   ...确认后同一条命令加 --execute。--author 也可用环境变量 MP_AUTHOR
#   ⛔ 脚本报 ❌ 就原样报告失败，不许绕开脚本、不许去掉封面重试

# ⭐ 小红书图文：只许用这一条。三档互斥：不加=预演不碰页面 / --draft=存草稿并核验图片数（测试用）/ --execute=真发
python3 <SKILL_DIR>/xhs_note.py 精简版.md \
  --title "≤20字" --cover 封面.png --cards "卡片标题1\n卡片正文1|||卡片标题2\n卡片正文2"
#   首图 = 封面；后面的文字卡由 render_cards.py 本地渲染，不用小红书自带「文字配图」，顺序固定、字不会糊
#   每张卡正文放不下脚本会报错，拆成两张
#   不支持话题标签：适配器挂话题必报 "no real topic entity appeared"，脚本已不传
#   ⚠️ 失败时脚本会列出残留草稿 id；存草稿测试完用 opencli xiaohongshu draft-delete "<id>" --execute 删
```

优先使用 `--content-file`，避免长文本经过 shell 引号后变形。创建临时正文文件时不要覆盖用户文件。

⚠️ 正文里贴链接必须用纯 ASCII 地址（百分号编码）。中文路径原样贴，多个平台会在汉字处截断成 404。

### ⭐ X thread 发布（2026-09-14 首次跑通）

**X 免费号单条 280 字符**（中文按双宽算），长文只能拆 **thread**（首条 normal post + 后续 reply 自己）。
`opencli twitter post` 的多段落路径**不可用**（合成 `ClipboardEvent('paste')` 不被 Draft.js 接收），
但**单段落一直是通的** —— 拆成单段落即可。这是平台原生做法，不是妥协。

**⛔ 本脚本没有 `--execute` 门槛，裸跑即真发**，所以「不可破坏的规则」第 1 条（发布前必须取得用户对最终正文和平台的明确确认）是**它唯一也是必须的门槛**。

`publish.py --platform twitter` 的旧直发路径已显式停用：它使用 `--window background`，且 `split_for_x()` 会用双换行拼段落，与当前 X 的 `insertText` 注入能力冲突。X 发布只走本节的 `x_thread/publish_thread.py`。

```bash
python3 x_thread/publish_thread.py 1                    # 从第 1 条开始
python3 x_thread/publish_thread.py 3 <第2条的URL>        # 续发
#   待发内容放 /tmp/xthread/part1.txt .. partN.txt（每条单段落、≤280 加权字符）
#   session 名写 /tmp/xfg-session
```

原理、两个决定性因素、别再走的弯路、验证方法 —— 见下面「X / Twitter：拆 Thread 可用」一节。

### ⭐ 长正文：`opencli browser eval` 的参数上限（2026-09-14 修）

**症状**：头条/百家号发长文报 `OSError: [Errno 7] Argument list too long: 'opencli'`。

**根因**：这两个脚本原先把整篇正文 HTML **+ 封面 base64**（一张图就 335KB）拼成一个 JS 字符串，当**命令行位置参数**传给 `opencli browser eval`，超过系统 `ARG_MAX`。**不是内容问题，跟标题/图片无关，纯粹是传参方式。**

**正解：分片传输**（已落地在这两个脚本里）。
`push_payload(session, key, data)` 按 `CHUNK = 20000` 把内容逐片累加到页面上的 `window.__tt_payload` / `window.__bjh_payload`，最后用一段**不含长内容**的短 JS 读取并注入。⚠️ 任何往 `eval` 里塞大段文本的新脚本都要照这个来。

**报告纪律**：这类错误**不是** `auth`/`adapter`，别按"页面打不开"处理；也**不许绕开脚本**（去掉封面重试之类）。原样报错 + 修脚本。

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
4. 先运行 `publish.py` 预演，核对目标平台。
5. 确认仍有效后加 `--execute`。脚本会运行 preflight，并仅对可证明发生在提交前的 composer 故障重试一次。
6. 逐平台报告真实结果。部分成功时明确列出成功与失败平台，不把整体说成全失败。
7. 成功后归档（位置自定），记录平台、时间、外链、正文和来源。

## 平台实现

| 平台 | 实现 | 注意事项 |
|---|---|---|
| 微博 | `weibo_post.py` 读取 Chrome 指定 Profile 的 cookie，HTTP 发布 | 环境变量 `WEIBO_CHROME_PROFILE`（默认 `Default`）、`WEIBO_UID`；脚本自身也要求 `--execute` |
| 即刻 | OpenCLI Jike adapter（打补丁后支持 `--images`、`--dry-run`） | |
| 今日头条 | `toutiao_post.py` → OpenCLI 后台静默发文 | 标题 ≤30 字，自动开启广告收益分成 |
| 百家号 | `bjh_post.py` → OpenCLI 后台富文本发文 | 支持单图封面自动绑定，支持存草稿/直接发布 |
| 知乎 | `opencli zhihu answer` | 问题回答；单独按最终答案确认后执行 |
| 公众号 | `mp_draft.py` → `opencli weixin create-draft`（打补丁） | 只创建草稿，最终发表人工操作 |
| 小红书 | `xhs_note.py` → `opencli xiaohongshu publish`（打补丁） | 正文上限 1000 字 |
| X | `x_thread/publish_thread.py` → OpenCLI Twitter adapter | 长文拆 thread；⚠️ 脚本无 `--execute`，裸跑即真发，见下 |

不要把 Chrome 里肉眼可见的登录状态当作 cookie 证明（可能登在另一个 Profile），以 `preflight.py` 结果为准。

## 知乎

```bash
opencli zhihu whoami
opencli zhihu answer <问题URL> "回答内容"        # 预览
opencli zhihu answer <问题URL> "回答内容" --execute
```

⚠️ 知乎**没有 edit / delete 命令**：一条回答发出去，CLI 改不了也删不掉，只能在网页端处理。发之前就得定稿。

**全平台发布时，自己找问题挂靠**：
1. `opencli zhihu search "<从文章里抽 2-3 组关键词>" --limit 6 -f yaml`，换角度搜 2-3 轮。
2. 选题标准是**「这篇文章真的回答了那个问题」**，不是关键词重合度高。优先选现有回答都在转述理论、而作者有第一人称实践或反面边界的题。
3. ⛔ 别把其它平台的原文直接贴过去。开头要接住那个问题本身，中段给机制，把原文里的"边界/代价/不同意的部分"提上来当独立段落。
4. 发完把 `created_url` 记进归档。

## 小红书

- 版式固定：**第一张封面图，后面本地渲染文字卡**。
- `--images` 补丁：包内 `clis/xiaohongshu/publish.js` 在 `fileChooserOpened` 失败时回落 DataTransfer。`xhs_note.py` 每次自检，被 `npm update` 冲掉会自动恢复。
- 正文上限 1000 字：长文先改写成精简版 .md 再跑，脚本超限直接报错，不许硬截断。

## 公众号：草稿做到「打开即可发」，最后一下人工

⛔ **`freepublish/submit`（API 直接发布）对个人主体不可用**。微信官方文档：「2025 年 7 月起，个人主体账号、企业主体未认证账号及不支持认证的账号将被回收以上接口的调用权限」（`developers.weixin.qq.com/doc/service/guide/product/publish.html`）。个人主体订阅号无法做微信认证，所以这条路是关的。网上有教程说可用，与官方矛盾，以官方为准。

**所以标准做法：草稿做到打开就能点发表，不留填表工作。** 最后一步用手机「公众号助手」App 点发表，比电脑后台快。

`mp_draft.py` 内部做的事，供排障时看：

```bash
opencli weixin drafts                    # 先看草稿箱，避免重复
python3 <SKILL_DIR>/md2plain.py 文章.md > 正文.txt   # ⛔ 必做，见下
sips -s format jpeg -s formatOptions 65 -Z 1200 cover.png --out cover.jpg  # 压到 ~150KB
opencli weixin create-draft "$(cat 正文.txt)" \
  --title "标题（≤64字）" --author "作者（≤8字）" --summary "一句话摘要" \
  --cover-image cover.jpg --timeout 240
```

**标题、作者、摘要、封面四个字段一个都不能省**，封面自己生成，不要回头问用户要图。

**⛔ 正文必须先过 `md2plain.py`**。直接塞 Markdown，草稿里满是 `##` 和 `>`。它去掉 frontmatter/引用/粗体/链接，二级标题转成「一、二、三、」独立行。

**封面上传**：`create-draft.js` 原版走 `setFileInput`，必报 `fileChooserOpened` 超时。补丁改成 DataTransfer 直塞。
- 输出里的 `(with cover)` 只要传了参数就会打印，**不代表封面设上了**。以 `opencli weixin drafts` 里新草稿**没有**「图文内容不完整 请补充封面图」为准。
- ⛔ **封面上传失败 = 报失败**，不许去掉 `--cover-image` 重跑然后说"发布完毕"。
- **配图在正文顶部**：补丁里先等 2 秒让 ProseMirror 规整 DOM，再把光标放到第一个 `span[leaf]` 开头，然后插图。插完会校验图是否在第一段文字前面，不在就报「配图没插到正文顶部」并中止。

**重做草稿会留下旧草稿**：opencli 没有删草稿命令，报告里写明要手动删哪几条（按「更新于」时间点名）。

⚠️ 公众号网页登录态短命，`create-draft` 前先 `preflight.py --platform weixin --deep`；失效时 `--repair` 会开好登录页，扫码登录即可。

⛔ **别把 Markdown 直接塞进 `create-draft`**：后台编辑器是 ProseMirror，只认富文本，`**加粗**` 会原样显示成星号。事后也没法用脚本补救，改 DOM / execCommand / 点工具栏 / 合成 paste 事件全部无效。**要么正文本来就是纯文本，要么走下面的 API 路线。**

**要排版就走 `cgi-bin/draft/add` 官方 API**（个人订阅号可用、无需认证）。`content` 字段支持 HTML 标签，必须少于 2 万字符，图片 URL 必须来自「上传图文消息内的图片获取 URL」接口。流程：Markdown → **内联样式** HTML（不认 `<style>` 和 class）→ `draft/add`。需 AppID+AppSecret，出口 IP 要加白名单。

## X / Twitter：拆 Thread 可用（见 `x_thread/publish_thread.py`）

X 免费号单条限 **280 字符**（中文按双宽算），长文只能拆 **thread**（首条 normal post + 后续逐条 reply 自己）。这是平台原生做法，不是妥协。
`x_thread/publish_thread.py` 实测跑通（6 条串成一条完整链）。

**⛔ 该脚本没有 `--execute` 门槛，裸跑即真发。** 跑之前必须已确认最终正文。

### 两个决定性因素（缺一不可）

1. **X 的所有写操作（发布 / 删除 / 回复）必须 `--window foreground`。** `--window background` 打开的标签**会被回收成 `about:blank`**，而报错**伪装成** `no box` / `Could not verify tweet text` / `Could not find the "More" context menu` —— 看起来像注入失败或登录态问题，**其实是页面没了**。极难排查。
2. **用 `execCommand('insertText')` 一步注入**，别用 `opencli browser type`：它报 `{"typed":true}` 但**文字哪里都没进**（X 页面频繁重渲染会让 ref 失效）。正解是在**一次 `eval` 里**完成「选节点 → 聚焦 → 清空 → insertText → 读回校验」。

### 别再走的弯路

- ❌ **「合成 `paste` 事件是正解」是错的。** 合成 `ClipboardEvent('paste')` 进得去但没用：handler 跑了、`defaultPrevented=true`，编辑器仍为空（Draft.js 读不到合成的 DataTransfer）。
- ❌ **「改 `clis/**/*.js` 不生效、有一层没找到的加载机制」—— 机制已找到**：manifest **存在且成功加载**时，`discoverClis()` 走快路径并 `continue`，跳过文件系统扫描；manifest 无效或加载失败则 fallthrough 回 `discoverClisFromFs`。源码：`discovery.js:104-113`。要改适配器**先把可用 manifest 移走**；只加参数则改 manifest。
- ❌ **「`~/.opencli/clis/` 本地覆盖目录不被加载」也是错的** —— 它**真的会加载，且覆盖内置**（在 builtin 之后跑）。且 `discoverClisFromFs` 对每个子目录都扫、**不过滤目录名**，所以目录名带 `.bak-*` 后缀**照样被当适配器加载**。**这正是"改了代码不生效"的真凶**：残留的备份目录覆盖了包内适配器。
- ❌ 按行插入 + 敲 Enter：CDP `nativeKeyPress` 不传 `code`/`windowsVirtualKeyCode`，Draft.js 不认；JS 合成 `KeyboardEvent` 过不了 `isTrusted` 校验。

**排查加载问题的正确工具**：`NODE_OPTIONS="--import=<hook>"` + 自定义 loader 打印**所有被 import 的 URL**。别靠猜。

### 验证链结构

```bash
opencli twitter thread <首条 id> -f json     # ✅ 首条 + 全部回复，一次拿全
```

⚠️ 别用 `twitter tweets` 验链：它是**折叠后的时间线视图，不是 thread 清单**。同一条 6 条 thread 连续 3 次实测均只覆盖 3 条（根帖 + 链尾两条，第 2–4 条被折叠/遗漏），会误判成「帖子丢了」。
且 `in_reply_to` 是**直接父节点**不是会话根 —— 逐条核对时**必须按 id 匹配**再读。

### 保留的修复

`opencli twitter post` 默认 60s 命令上限不够（发成功却报失败），用 `OPENCLI_BROWSER_COMMAND_TIMEOUT=180`（post 没有 `--timeout` 参数）。失败时先清空编辑框：x.com 在编辑框有内容时注册 `beforeunload`，弹窗没人应答会冻住整个浏览器。
