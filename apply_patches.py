#!/usr/bin/env python3
"""把 patches/opencli/ 下的适配器补丁装进全局 @jackwener/opencli，并重启 daemon。

npm update 会覆盖包内文件，更新 opencli 后重跑一次：python3 apply_patches.py
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH_DIR = HERE / "patches/opencli"

# 即刻补丁新增的参数：只改 js 不够，opencli 从包根 cli-manifest.json 读参数定义
JIKE_ARGS = [
    {"name": "images", "type": "string", "required": False, "help": "图片路径，逗号分隔（jpg/png）"},
    {"name": "dry-run", "type": "bool", "default": False, "help": "只填好正文和图片、核验后清空，不点发送"},
]


def opencli_root() -> Path:
    if os.environ.get("OPENCLI_ROOT"):
        return Path(os.environ["OPENCLI_ROOT"])
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    return Path(npm_root) / "@jackwener/opencli"


def patch_manifest(root: Path) -> None:
    path = root / "cli-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = next(e for e in manifest if e.get("site") == "jike" and e.get("name") == "create")
    names = {a["name"] for a in entry["args"]}
    entry["args"] += [a for a in JIKE_ARGS if a["name"] not in names]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    root = opencli_root()
    if not (root / "clis").is_dir():
        raise SystemExit(f"找不到 opencli 安装目录：{root}（可用 OPENCLI_ROOT 指定）")
    for src in PATCH_DIR.rglob("*.js"):
        dst = root / "clis" / src.relative_to(PATCH_DIR)
        if dst.exists() and not dst.with_suffix(".js.orig").exists():
            shutil.copy(dst, dst.with_suffix(".js.orig"))
        shutil.copy(src, dst)
        print(f"patched {dst}")
    patch_manifest(root)
    print("patched cli-manifest.json (jike create args)")
    subprocess.run(["opencli", "daemon", "restart"])


if __name__ == "__main__":
    main()
