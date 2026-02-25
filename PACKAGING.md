# 🐈 nanobot Windows 打包指南

## 概览

本项目支持打包为 Windows 可执行文件和安装包，提供以下三种方式：

| 输出 | 说明 | 命令 |
|------|------|------|
| `dist\nanobot\` | 文件夹模式（推荐） | `.\build_installer.ps1` |
| `dist\nanobot.exe` | 单文件便携版 | `.\build_installer.ps1 -OneFile` |
| `nanobot-x.x.x-win64-setup.exe` | Windows 安装包 | `.\build_installer.ps1` |

## 前置条件

- **Conda**（已安装，推荐 Miniconda / Anaconda）
- **Conda 环境**（默认使用 `python312`，已包含项目依赖）
- **Inno Setup 6**（可选，仅在需要生成安装包时需要）
  - 下载: https://jrsoftware.org/isdl.php

## 快速开始

### 方式一：一键构建（推荐）

脚本会自动使用你的 conda `python312` 环境，**不会重新下载依赖**。

```powershell
# 使用默认 conda 环境 (python312) 打包
.\build_installer.ps1

# 指定其他 conda 环境
.\build_installer.ps1 -CondaEnv myenv

# 清理旧构建后重新打包
.\build_installer.ps1 -Clean

# 仅打包为文件夹（跳过安装包生成）
.\build_installer.ps1 -SkipInnoSetup

# 打包为单个 exe 文件（便携版）
.\build_installer.ps1 -OneFile

# 如果需要重新安装依赖到 conda 环境
.\build_installer.ps1 -InstallDeps
```

### 方式二：手动分步构建

```powershell
# 1. 激活 conda 环境（使用已有的依赖）
conda activate python312

# 2. 确保 PyInstaller 已安装
pip install pyinstaller

# 3. 使用 spec 文件构建
pyinstaller --noconfirm --clean nanobot.spec

# 4. 验证
.\dist\nanobot\nanobot.exe version

# 5.（可选）生成安装包
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

### 方式三：仅生成便携版 exe

```powershell
conda activate python312
pip install pyinstaller
pyinstaller --onefile --console --name nanobot nanobot/__main__.py
# 输出: dist\nanobot.exe
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `nanobot.spec` | PyInstaller 构建配置，定义打包规则、隐藏导入、数据文件 |
| `installer.iss` | Inno Setup 脚本，定义安装向导、注册表、PATH 等 |
| `build_installer.ps1` | PowerShell 一键构建脚本 |

## 输出目录

```
dist/
  nanobot/              # 文件夹模式输出
    nanobot.exe          # 主程序
    *.dll, *.pyd         # 依赖库
    nanobot/skills/      # 技能文件
    ...

installer_output/
  nanobot-0.1.3-win64-setup.exe   # Windows 安装包
```

## 安装包特性

安装包（通过 Inno Setup 生成）包含：

- ✅ 安装向导界面（支持中英文）
- ✅ 自动添加到系统 PATH（可选）
- ✅ 创建桌面快捷方式（可选）
- ✅ 开始菜单项
- ✅ 完整的卸载程序
- ✅ 无需管理员权限（用户级安装）

## 常见问题

### Q: 打包后的 exe 文件很大？

这是正常的，因为 PyInstaller 会将 Python 解释器和所有依赖库都打包进去。可以通过以下方式减小体积：

1. 使用虚拟环境，只安装必要依赖
2. 在 spec 文件中排除不需要的模块（`excludes` 列表）
3. 启用 UPX 压缩（已默认启用）

### Q: 杀毒软件误报？

PyInstaller 打包的程序可能被某些杀毒软件误报，这是已知问题。可以：
- 将打包目录加入杀毒白名单
- 对 exe 进行代码签名（需要代码签名证书）

### Q: 运行时提示缺少模块？

在 `nanobot.spec` 的 `hiddenimports` 列表中添加缺失的模块名。

### Q: 如何添加应用图标？

1. 准备一个 `.ico` 格式的图标文件
2. 在 `nanobot.spec` 中修改 `icon=None` 为 `icon='path/to/icon.ico'`
3. 在 `installer.iss` 中取消 `SetupIconFile` 的注释
