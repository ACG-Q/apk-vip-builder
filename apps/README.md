# apps/ — 多 APK VIP 构建指南

## 概述

`apps/` 目录下每个子目录对应一个 APK 项目，各自独立管理下载源、smali 补丁逻辑和构建状态。所有通用流水线脚本（下载、反编译、编译签名、发布）集中在 `scripts/`，由 GitHub Actions 可复用 workflow（`_vip_build.yml`）统一调度。

### 架构原则

- **每个 App 完全隔离** —— 各自的 app.json、patch.py、state.json、download.apk
- **通用流水线共享** —— 反编译、编译、签名、release 由 scripts/ 处理
- **新增仅需 3 步** —— 创建 app.json + patch.py + workflow 触发文件

## 目录结构详解

```
apps/
├── README.md                   # 本文件
└── <app_name>/                 # 每个 App 一个目录 (目录名即 --app 参数值)
    ├── app.json                # 【必要】APK 元数据配置
    ├── patch.py                # 【必要】smali 语义搜索 + 补丁逻辑
    ├── state.json              # 自动管理 —— SHA256、版本号、大小跟踪
    └── download.apk            # 自动下载或手动放置的原始 APK
```

### 各文件说明

| 文件 | 作用 | 维护方式 |
|------|------|----------|
| `app.json` | 定义 App 名称、包名、下载地址、输出格式 | 开发者手动创建 |
| `patch.py` | 实现 `patch()` 函数，对反编译后的 smali 做 VIP 补丁 | 开发者手动编写 |
| `state.json` | 记录上次构建的 SHA256、版本号、大小，用于变更检测 | CI 自动更新；首次需手动创建空 JSON `{}` |
| `download.apk` | 原始 APK 文件 | 有 `download_url` 时自动下载；无则手动放置 |

## 快速上手：三步添加一个新 App

### 步骤 1：创建 `apps/<app_name>/app.json`

`app.json` 是 App 的身份证，定义下载来源和输出方式。

#### 完整 Schema

```json
{
  "name": "MyApp",
  "package": "com.example.myapp",
  "download_url": "https://example.com/latest.apk",
  "output_apk": "MyApp_VIP_{version}.apk"
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | — | 显示名称，用于日志输出和 `{app_name}` 占位符 |
| `package` | string | 是 | — | Android 包名（如 `com.catchingnow.np`），用于 Release 标题和 Tag |
| `download_url` | string | 否 | `""` | APK 下载地址。**留空 = 手动放置模式**，APK 需通过 git commit 放到 `apps/<app_name>/download.apk` |
| `output_apk` | string | 是 | — | 签名后 APK 文件名，支持的占位符见下表 |

##### `output_apk` 支持的占位符

| 占位符 | 来源 | 示例值 |
|--------|------|--------|
| `{version}` | apktool.yml `versionName` | `3.4.5` |
| `{version_code}` | apktool.yml `versionCode` | `203053733` |
| `{package}` | apktool.yml `renameManifestPackage` 或 AndroidManifest.xml | `com.catchingnow.np` |
| `{build_time}` | 构建时间（UTC，格式 `YYYYMMDD_HHMMSS`） | `20250628_193000` |
| `{app_name}` | app.json 的 `name` 字段 | `FilterBox` |

#### 示例 A：自动下载（有固定 URL）

```json
{
  "name": "FilterBox",
  "package": "com.catchingnow.np",
  "download_url": "https://filterbox.catchingnow.com/latest.apk",
  "output_apk": "FilterBox_VIP_{version}.apk"
}
```

此模式下 GitHub Actions 使用 `schedule` 定时检查更新。

#### 示例 B：手动放置（无 URL）

```json
{
  "name": "AnotherApp",
  "package": "com.example.another",
  "download_url": "",
  "output_apk": "AnotherApp_VIP_{version}.apk"
}
```

此模式下 APK 文件需手动放置到 `apps/another-app/download.apk` 并提交到 git 仓库。GitHub Actions 使用 `push` 触发（检测到 `download.apk` 文件变更时自动构建）。

### 步骤 2：实现 `apps/<app_name>/patch.py`

每个 App 的 VIP 补丁逻辑完全独立，由 `patch.py` 导出的 `patch()` 函数实现。

#### `patch()` 函数接口

```python
from pathlib import Path

def patch(
    smali_dir: Path,        # 反编译后的 smali 目录：output/{app}/apktool/smali/
    version_info: dict,     # 版本信息：{"version": "1.0.0", "version_code": 100, "package": "com.example.xxx"}
    repo_url: str           # GitHub 仓库地址，对应 --url 参数或 vars.REPO_URL
) -> list[str]:            # 返回补丁描述列表（每项一行，用于日志输出）
    ...
```

#### `version_info` 字段说明

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `version` | string | apktool.yml 的 `versionName` | 版本号，如 `3.4.5` |
| `version_code` | int | apktool.yml 的 `versionCode` | 版本码，如 `203053733` |
| `package` | string | apktool.yml 的 `renameManifestPackage` → AndroidManifest.xml | 包名 |

#### 可复用工具函数

以下函数定义在 `apps/filterbox/patch.py` 中，你可以直接复制到自己的 `patch.py` 中使用：

| 函数 | 用途 | 签名 |
|------|------|------|
| `patch_by_sig` | 按方法签名替换方法体 | `(content, params_sig, return_type, new_body, static_only) → (new_content, count)` |
| `patch_method_at` | 替换指定行号的方法体 | `(content, start_line, new_body) → (new_content, ok)` |
| `find_vip_interface` | 搜索 VIP 状态接口（通过方法特征） | `() → interface_name \| None` |
| `find_implementations` | 查找实现某个接口的类 | `(iface_name) → [smali_file_path]` |
| `find_state_class` | 查找调用接口的状态类 | `(iface_name) → (smali_file, line_number) \| (None, None)` |
| `find_purchase_dialog` | 查找购买弹窗 ViewModel | `(state_dir) → (smali_file, line_number) \| (None, None)` |
| `is_std_lib` | 判断是否为 Android/Kotlin 标准库类 | `(relative_path) → bool` |

#### 最小示例：仅打印版本信息，不做任何修改

```python
from pathlib import Path

def patch(smali_dir: Path, version_info: dict, repo_url: str) -> list[str]:
    ver = version_info.get("version", "unknown")
    print(f"App version: {ver}")
    return ["OK: version info printed"]
```

#### FilterBox 参考示例

完整实现请查看 `apps/filterbox/patch.py`，它演示了四种常见的补丁模式：

- **Phase A**：通过方法签名特征定位 VIP 状态接口
- **Phase B**：查找接口实现类，将方法返回值 patch 为 true/active
- **Phase C**：定位购买弹窗 ViewModel，将入口方法替换为 `return-void`
- **Phase D**：在设置页列表末尾插入"软件版本"项 + GitHub 跳转监听器

### 步骤 3：创建 GitHub Actions 触发文件

在 `.github/workflows/` 下创建 `vip_<app_name>.yml`，调用可复用 workflow。

#### 场景 A：自动下载（每日 `schedule` + 手动触发）

```yaml
# .github/workflows/vip_filterbox.yml
name: VIP FilterBox

on:
  schedule:
    - cron: '0 0 * * *'          # 每天 UTC 0:00 自动检查
  workflow_dispatch:              # 支持手动触发

jobs:
  build:
    uses: ./.github/workflows/_vip_build.yml
    with:
      app_name: filterbox
      repo_url: ${{ vars.REPO_URL || 'https://github.com/ACG-Q/apk-vip-builder' }}
    secrets: inherit              # 传递 RELEASE_KEYSTORE 等 Secrets
```

#### 场景 B：手动放置（`push` 触发 + 手动触发）

```yaml
# .github/workflows/vip_another-app.yml
name: VIP AnotherApp

on:
  workflow_dispatch:
  push:
    paths:
      - 'apps/another-app/download.apk'

jobs:
  build:
    uses: ./.github/workflows/_vip_build.yml
    with:
      app_name: another-app
      repo_url: ${{ vars.REPO_URL || 'https://github.com/ACG-Q/apk-vip-builder' }}
    secrets: inherit
```

#### 两种场景 workflow 对比

| 项目 | 自动下载（FilterBox） | 手动放置（AnotherApp） |
|------|-----------------------|------------------------|
| 触发方式 | `schedule` + `workflow_dispatch` | `push` (path: `download.apk`) + `workflow_dispatch` |
| APK 来源 | CI 自动从 `download_url` 下载 | 开发者手动 git commit `download.apk` |
| `download_url` | 必填 | 留空 |
| 适用场景 | 公开下载链接的应用 | 私有 APK / 需要手动处理的应用 |

### 步骤 4：提交到仓库

```bash
git add apps/your-app/
git add .github/workflows/vip_your-app.yml
git commit -m "feat: add your-app VIP build"
git push
```

> `apps/*/download.apk` 默认被 `.gitignore` 忽略（自动下载场景）。**手动放置场景需要删除 `.gitignore` 中的 `apps/*/download.apk` 这一行**，才能将该文件纳入版本管理。

## 完整流水线说明

当 workflow 触发后，以下步骤依次执行：

```
                        ┌─────────────────────┐
                        │  Checkout 代码库      │
                        ├─────────────────────┤
                        │  Setup Python 3.11   │
                        ├─────────────────────┤
                        │  Setup Java 17       │
                        ├─────────────────────┤
                        │  Cache / 下载工具     │ ← apktool + JRE（一次，全局缓存）
                        ├─────────────────────┤
                        │  解码 Keystore        │ ← 从 Secrets 恢复签名密钥
                        ├─────────────────────┤
                        │  Identify APK         │ ← scripts/identify_apk.py --app xxx
                        │  • 有 download_url → 下载 APK 并 SHA256 比对
                        │  • 无 download_url → 检查本地 download.apk 的 SHA256
                        │  • 无变化 → 跳过构建，退出
                        ├─────────────────────┤
                        │  Decompile APK        │ ← scripts/decompile_apk.py --app xxx
                        │  • apktool d → output/{app}/apktool/
                        │  • 提取 versionName / versionCode → output/{app}/version.json
                        ├─────────────────────┤
                        │  Build VIP            │ ← scripts/build_vip.py --app xxx --url ...
                        │  • 动态 import apps/{app}/patch.py → 执行 patch()
                        │  • apktool b → 重新编译 unsigned.apk
                        │  • uber-apk-signer → 签名 → output/{app}/signed/
                        │  • 生成 release_info.json（含 tag / SHA256 / 大小 / 构建时间）
                        ├─────────────────────┤
                        │  Create Release       │ ← scripts/create_release.py --app xxx
                        │  • gh release create
                        │  • Tag:   {package}_{version}_{YYYYMMDD_HHMMSS}
                        │  • Title: {package} {version} {构建时间} Build
                        │  • Body:  包名 / 版本 / SHA256 / 大小 / 构建时间表格
                        └─────────────────────┘
```

### Release 产出

构建完成后，GitHub Actions 会创建一个 Release：

- **Tag 格式：** `{package}_{version}_{YYYYMMDD_HHMMSS}`
  示例：`com.catchingnow.np_3.4.5_20250628_193000`
- **Title 格式：** `{package} {version} {构建时间} Build`
  示例：`com.catchingnow.np 3.4.5 2025-06-28 19:30 UTC Build`
- **Release Body：** 包含包名、版本（含 versionCode）、SHA256、大小、构建时间的 Markdown 表格
- **附件：** 签名后的 VIP APK 文件

## 本地开发与测试

### 前置条件

- Python 3.11+
- Java 17+（或由 `scripts/download_tools.py` 自动下载）
- 已放置的 APK 文件

### 安装依赖

```bash
pip install -r scripts/requirements.txt
```

### 完整本地流程

```bash
# 1. 下载工具（首次运行）
python scripts/download_tools.py

# 2. 下载或确认 APK
python scripts/identify_apk.py --app filterbox

# 3. 反编译
python scripts/decompile_apk.py --app filterbox

# 4. 构建 VIP（patch → 编译 → 签名）
python scripts/build_vip.py --app filterbox --url "https://github.com/your-org/your-repo"

# 5. 查看构建产物
ls output/filterbox/signed/
cat output/filterbox/release_info.json
```

### 常见调试命令

```bash
# 仅检查 APK 是否有更新
python scripts/identify_apk.py --app filterbox
echo $?    # 0=有更新 1=无更新

# 仅测试 patch（不编译签名）
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('patch', 'apps/filterbox/patch.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from pathlib import Path
result = mod.patch(
    Path('output/filterbox/apktool/smali'),
    {'version': '3.4.5', 'version_code': 203053733, 'package': 'com.catchingnow.np'},
    'https://github.com/ACG-Q/apk-vip-builder'
)
print('Patches:', result)
"

# 查看版本信息
cat output/filterbox/version.json
```

## 常见问题

### Q: `patch.py` 怎么写？我不熟悉 smali

A: 建议先用 jadx-gui 反编译 APK，浏览关键类结构。然后：

1. 分析 VIP 状态检测逻辑 —— 通常是一个接口 + 若干实现类
2. 找到 VIP 状态接口的调用处 —— 通常是静态方法
3. 找到购买弹窗的入口 —— 通常是 BottomSheetDialog 相关类
4. 参考 `apps/filterbox/patch.py` 的模式，用 `patch_by_sig()` 等工具函数做替换

smali 不熟悉时可对照 jadx-gui 的 Java 源码和 smali 文件对照学习。

### Q: 如何测试 patch 是否正确？

A: 依次运行完整本地流程（identify → decompile → build_vip），然后安装签名后的 APK 验证功能。首次建议在模拟器或备用机测试。

### Q: Release tag 格式是什么？

A: `{package}_{version}_{YYYYMMDD_HHMMSS}`，例如 `com.catchingnow.np_3.4.5_20250628_193000`。所有字段自动从 apktool.yml 和构建时间提取。

### Q: 如何自定义 GitHub 跳转链接？

A: 通过 GitHub Actions 的 `vars.REPO_URL` 配置。在仓库 Settings → Secrets and variables → Actions → Variables 中添加 `REPO_URL`。如果未设置，默认跳转到仓库主页。

### Q: `state.json` 需要手动维护吗？

A: 不需要。`scripts/identify_apk.py` 自动读写 `state.json` 中的 `last_hash`、`last_size`、`last_version`、`last_version_code`。首次创建时只需 `echo '{}' > apps/<app_name>/state.json`。

### Q: 可以同时构建多个版本吗？

A: 可以。每个 App 有独立的 workflow 文件（`vip_*.yml`），它们可以并行运行。GitHub Actions 的 `ubuntu-latest` runner 会为每个 workflow 分别启动一个 job。

### Q: 手动放置的 APK 如何更新？

A: 用新版本 APK 覆盖 `apps/<app_name>/download.apk`，然后 git commit 并 push。配置了 `push` 触发的工作流会自动检测到 hash 变化并执行完整构建。

### Q: 如何修改签名密钥？

A: 在仓库 Settings → Secrets and variables → Actions → Secrets 中更新 `RELEASE_KEYSTORE`（keystore 的 base64 编码）和 `RELEASE_KEYSTORE_PASS`（密码）。本地开发使用 `scripts/setup.ps1` 生成。
