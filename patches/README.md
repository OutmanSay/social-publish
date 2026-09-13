# opencli 适配器补丁

这里的 `.js` 是 [jackwener/opencli](https://github.com/jackwener/opencli) v1.8.7 适配器的**修改版**，原作按 Apache-2.0 授权，修改版沿用 Apache-2.0。安装：`python3 ../apply_patches.py`（会先把原文件备份成 `.js.orig`）。

| 文件 | 改了什么 | 为什么 |
|---|---|---|
| `weixin/create-draft.js` | 封面上传改走 DataTransfer 直塞隐藏 `input[type=file]`；配图插在正文顶部并校验位置 | 原版 `setFileInput` 等 fileChooser 事件，隐藏 input 永远等不到，必超时；原版光标停在正文末尾，图落到底部 |
| `xiaohongshu/publish.js` | `fileChooserOpened` 失败时同样回落 DataTransfer | 同上 |
| `jike/create.js` | 新增 `--images`（多图）和 `--dry-run`（填好图文、核验后清空、不发送） | 原版只能发纯文本，也没有安全的彩排手段 |

## 改 opencli 适配器的三个坑

1. 参数定义以包根 `cli-manifest.json` 为准，只改 js 会报 `unknown option`。`apply_patches.py` 会一并补 manifest。
2. opencli 常驻 daemon 缓存适配器模块，改完必须 `opencli daemon restart`，否则等于没改。
3. `~/.opencli/clis/<site>/` 这个"本地覆盖目录"实际不被加载，`opencli doctor` 报它是 shadow 容易误读成已生效。
