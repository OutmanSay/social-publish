# opencli 适配器补丁

这里的 `.js` 是 [jackwener/opencli](https://github.com/jackwener/opencli) v1.8.7 适配器的**修改版**，原作按 Apache-2.0 授权，修改版沿用 Apache-2.0。安装：`python3 ../apply_patches.py`（会先把原文件备份成 `.js.orig`）。

| 文件 | 改了什么 | 为什么 |
|---|---|---|
| `weixin/create-draft.js` | 封面上传改走 DataTransfer 直塞隐藏 `input[type=file]`；配图插在正文顶部并校验位置 | 原版 `setFileInput` 等 fileChooser 事件，隐藏 input 永远等不到，必超时；原版光标停在正文末尾，图落到底部 |
| `xiaohongshu/publish.js` | `fileChooserOpened` 失败时同样回落 DataTransfer | 同上 |
| `jike/create.js` | 新增 `--images`（多图）和 `--dry-run`（填好图文、核验后清空、不发送） | 原版只能发纯文本，也没有安全的彩排手段 |

## 改 opencli 适配器的四个坑

1. 参数定义以包根 `cli-manifest.json` 为准，只改 js 会报 `unknown option`。`apply_patches.py` 会一并补 manifest。
   反过来说：**包根存在 `cli-manifest.json` 时，`clis/**/*.js` 根本不会被加载**（`discoverClis()` 走 manifest 快路径后 `continue`，跳过文件系统扫描）。所以**要改适配器逻辑，先把 manifest 移走**；只加参数则改 manifest。
2. opencli 常驻 daemon 缓存适配器模块，改完必须 `opencli daemon restart`，否则等于没改。
3. ⚠️ **`~/.opencli/clis/<site>/` 这个"本地覆盖目录"是【真的会被加载】的，而且覆盖内置**（它在 builtin 之后被加载）。早期文档曾把它记成"不被加载"，是错的——这个误判会让人查不出"改了代码不生效"。
4. ⚠️ **`.bak-*` 后缀的目录照样会被加载。** `discoverClisFromFs` 对目录下每个子目录里的 `.js` 都 import，**不过滤目录名**。所以备份适配器目录时**必须挪到 `clis/` 之外**，否则备份目录会静默覆盖正式的适配器——这是"改了代码不生效"最常见的原因。`opencli doctor` 会把这类目录报成 shadow。
