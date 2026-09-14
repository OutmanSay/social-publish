# Changelog

git 里有文件快照的版本标了 📦；没有的只记变化，原文件没留存。07-15、07-31 两条的日期取自文件修改时间，其余来自当时的工作记录。

## 2026-09-14.2 📦
- 新增今日头条（头条号）与百家号接入：
  - 新增 `toutiao_post.py`：头条号长文图文静默发布，支持单图封面绑定、自动开启广告收益分成。
  - 新增 `bjh_post.py`：百家号长文图文发布，支持 UEditor 富文本注入、单图封面选择、支持 `--draft` 存草稿与 `--execute` 直接发布。
  - `publish.py` 扩展支持 `--platform toutiao` 与 `--platform baijiahao`，支持图文多平台一键分发。
  - 全平台发布矩阵扩展为 7 平台（微博、即刻、知乎、公众号、小红书、今日头条、百家号）。

## 2026-09-14.1 📦
- 封面出图模型改为 `gpt-image-2.5-sunburst`（原 `gpt-image-2`）。同题中文封面对比，2.5 系耗时持平、中文无错字，gpt-image-2 会自行加入品牌 logo。

## 2026-09-14 📦
- 公众号：配图插在正文**顶部**（原来落在末尾）。插图前等 ProseMirror 规整 DOM，把光标放到第一段开头；插完校验位置，不在顶部就中止并报错。

## 2026-09-13 📦
- 新增 `mp_draft.py`：公众号草稿一条命令。Markdown 转纯文本、压封面、补丁自检、登录检查、核验封面真设上。
- 新增 `md2plain.py`：直接塞 Markdown 进公众号编辑器会原样显示 `##`、`>`。
- 新增 `xhs_note.py` + `render_cards.py`：小红书封面 + 本地文字卡，预演 / 存草稿核验 / 发布三档。
- 公众号封面上传补丁：原版等 fileChooser 事件，隐藏 input 必超时，改为 DataTransfer 直塞。
- 小红书 `--images` 补丁：同样回落 DataTransfer。
- 即刻补丁：新增 `--images` 和 `--dry-run`；`publish.py` 加 `--image`、`--rehearse`，配图自动压到 ≤500KB（即刻单图 >~700KB 会崩）。
- `weibo_post.py` 支持传图（先上传拿 pid，预演也跑上传，提前暴露故障）。
- X 提交超时从 75s 提到 210s（发成功却报失败）；多段落长帖排查到底后放弃，X 移出默认发布集合。
- 小红书补进「全平台发布」。

## 2026-09-12
- 公众号草稿四个字段（标题/作者/摘要/封面）必须填满，封面自己生成。
- 查实 `freepublish/submit` 对个人主体已回收，发表改为手机「公众号助手」人工点。
- 全平台发布时知乎默认也发，自己搜问题挂靠，按知乎语境重写。

## 2026-08-28 📦
- 最早留存的快照。统一入口 `preflight.py` + `publish.py`，失败分类表，确认门，默认预演。

## 2026-08-12
- X 发 Thread 改用 persistent 会话复用同一窗口：原来每条开新窗，关窗触发 x.com `beforeunload` 弹窗，无人应答导致命令挂起。

## 2026-07-31
- `weibo_post.py` 发帖改为必须显式 `--execute`，默认只预演。

## 2026-07-15
- 新增 `preflight.py`（只读登录态检查 + 后台标签页刷新）和 `publish.py`（微博/X/即刻统一发布、X 按加权长度拆 Thread）及单测。

## 2026-06-25
- 独立的 `weibo-publish` 并入 `social-publish`，扩展到 X、即刻、知乎、公众号。

## 2026-05-25
- `weibo_post.py --list [N]`：走登录态接口拉自己最近 N 条（公开页拿不到）。

## 2026-05-24
- `weibo-publish` v1：`browser_cookie3` 读 Chrome cookie + 纯 HTTP `POST /ajax/statuses/update`，Chrome 关着也能发。先试过在登录 tab 里 fetch，因依赖浏览器开着弃用。
