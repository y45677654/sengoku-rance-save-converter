# 战国兰斯存档转换器 (Sengoku Rance Save Converter)

[![Version: v1.0.1](https://img.shields.io/badge/Version-v1.0.1-orange.svg)](https://github.com/y45677654/sengoku-rance-save-converter/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![Language: Bilingual](https://img.shields.io/badge/Language-English%20%7C%20%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue.svg)](#)

[🇨🇳 简体中文说明](#-中文说明) | [🌐 English Documentation](#-english-guide)

---

## 🇨🇳 中文说明

《战国兰斯》（兰斯7 / Sengoku Rance）旧版本与 Steam 官方版存档双向转换与适配工具。支持图形界面（GUI）与独立免安装 EXE，支持中英双语自适应切换，普通玩家无需配置任何 Python 环境即可双击使用。

### 🎯 版本与兼容性支持列表 (Compatibility Matrix)

#### 1. 转换器版本
* **当前版本**：`v1.0.1` (维护更新版 / Maintenance Release)

#### 2. 支持的源游戏版本（旧版战国兰斯）
| 游戏发行版本 | 版本号 | 语言/补丁 | 兼容状态 | 说明 |
| :--- | :--- | :--- | :---: | :--- |
| **《戦国ランス》日文原版** | v1.00 ~ v1.04 | 日语 | **完全支持** | 官方光盘版/DLsite 版，自动识别 `ランス７_*.ASD` 及中文系统解压乱码文件名并重命名映射 |
| **爱丽丝汉化组汉化版** | 基于 v1.04 内核 | 简体中文 / 繁体中文 | **完全支持** | 国内最广泛流传的汉化版本 |
| **早期海外民间英化版** | 基于 v1.04 内核 | 英语 | **完全支持** | Anime-Sharing 论坛英化补丁等 |
| **网络全CG通关存档** | 任意旧版 | 全语言 | **完全支持** | `Rance7_Sys.ASD` 全CG/全回想继承 |
| **论坛免安装整合硬盘版** | v1.00 ~ v1.04 | 简中 / 日文 | **完全支持** | 只要存档内含 `KEY_CODE_ランス７` 均完全通用 |

#### 3. 支持的目标游戏版本（Steam 官方版）
| 游戏发行版本 | 平台 / AppID | 语言版本 | 兼容状态 | 说明 |
| :--- | :--- | :--- | :---: | :--- |
| **Steam 官方版《Sengoku Rance》** | Steam (AppID: 1245050) | 官方英语 (English) | **完全支持** | 发行商 MangaGamer / AliceSoft |
| **Steam 官方版《Sengoku Rance》** | Steam (AppID: 1245050) | 官方日文 (Japanese) | **完全支持** | 发行商 MangaGamer / AliceSoft |
| **Steam 官方后续补丁更新** | Steam 自动更新推送 | 全部语言 | **持续兼容** | 官方若未颠覆重构底层引擎则长期有效 |

---

### 📖 问题背景：为什么直接复制旧存档会报错并被重置？

许多老玩家在购买 Steam 版《战国兰斯》后，尝试将以往的旧版存档（v1.04 日文版、爱丽丝汉化版等）直接复制到 Steam 的 `SaveData` 文件夹中，但在启动游戏或加载时会**频繁弹窗报错，甚至导致整个存档目录被游戏引擎自动重置清空**。

根本技术原因如下：
1. **游戏内部钥匙串（Game Key）不一致**：
   * 旧版本使用的唯一识别钥匙是：`KEY_CODE_ランス７`（日文 Shift-JIS 编码，占 18 字节）。
   * Steam 版官方使用的唯一识别钥匙改为了：`KEY_CODE_Rance`（ASCII 编码，占 15 字节）。
   * Steam 版引擎在读取存档时检测到钥匙不匹配，判定存档“已损坏”或“不是本游戏的存档”，从而触发内置安全机制，强行清空重置存档。
2. **数据块绝对偏移地址（Offset Table）位移**：
   * 战国兰斯使用的 AliceSoft System 4.0 引擎在存档头部记录了 5 个核心数据区（记录区、全局变量区、字符串区、数组区、键值对区）的绝对偏移地址。
   * 钥匙长度由 18 字节缩减为 15 字节后（差了 3 字节），后续所有的指针必须整体平移 3 字节。如果直接复制，引擎读取指针越界，校验同样会失败。

**本工具的作用**：自动解密并解压存档、精准替换钥匙串、平移 5 处数据块偏移量指针，最后重新加密压缩，生成完全符合 Steam 官方引擎校验的全新合法存档。

---

### 🚀 快速上手教程（无需安装 Python）

#### 方式一：直接下载 EXE 运行（推荐普通玩家）
1. 前往本项目的 **[Releases 页面](../../releases)** 下载最新版 `战国兰斯存档转换器.exe`（或 `SengokuRanceSaveConverter.exe`）。
2. 双击打开，软件会自动为您尝试检测 Steam 版《战国兰斯》的安装目录。
3. 界面支持中英双语自适应，也可在右上角随时点击 `🌐 语言 / Language` 切换。
4. 确认源目录与目标目录路径无误（可点击 `⇅ 对调源目录与目标目录` 快速切换转换方向）。
5. 点击 **【🚀 开始转换】** 即可自动完成转换与导出！

#### 方式二：通过 Python 源码运行（开发者/技术玩家）
本项目采用纯 Python 标准库编写，**零第三方依赖**，克隆后直接运行：
```bash
python rance7_converter_gui.py
```

---

### ⚠️ 重要注意事项（防 Steam 云存档覆盖）

导入完成后，首次进入游戏前请务必留意：
1. **暂时关闭 Steam 云同步**：
   * 在 Steam 库中右键《战国兰斯》 -> **属性** -> **通用**。
   * 暂时关闭 **“将游戏存档保存于 Steam 云”** 的开关。
2. **启动游戏检查**：
   * 启动游戏，检查存档列表是否已正常显示回合数与武将缩略图，CG 库是否已正常恢复。
3. **重新开启云同步（可选）**：
   * 退出游戏后重新开启云同步。下次启动若弹出“云存档冲突”提示，请选择**“上传本地文件到 Steam 云”**或**“以本地文件为准”**。

---

<br/>

## 🌐 English Guide

A standalone GUI tool for bidirectional save data conversion between legacy versions of **Sengoku Rance (Rance 7)** and the official **Steam release (MangaGamer, AppID: 1245050)**.  
Works out-of-the-box with **zero Python configuration** required.

### ❓ Why This Tool Exists

When players purchase the official Steam release of *Sengoku Rance* and attempt to copy their old save files (e.g. from the v1.00 ~ v1.04 Japanese original, old English fan patches, or downloaded 100% Clear Data saves) into the Steam `SaveData` directory, the game will throw fatal errors and **completely reset the save directory to empty defaults**.

#### Technical Root Cause:
1. **Game Key Mismatch**:
   - Legacy versions use `KEY_CODE_ランス７` (Shift-JIS encoded, 18 bytes) as the game identifier.
   - The Steam release changed this identifier to `KEY_CODE_Rance` (ASCII encoded, 15 bytes).
   - If the key does not match, AliceSoft's System 4.0 engine rejects the save file.
2. **Offset Pointer Drift (-3 Bytes)**:
   - System 4.0 save files contain an internal offset table tracking 5 critical data regions (`records`, `globals`, `strings`, `arrays`, `keyvals`).
   - Changing an 18-byte key to a 15-byte key causes an internal 3-byte shift. Without adjusting the offset table, pointers will read out of bounds.

**What this tool does**:  
It decrypts (MT19937 PRNG + zlib), patches the game key, recalculates the internal offset tables, and re-encrypts the save files so the Steam engine accepts them natively.

---

### 🎯 Compatibility Matrix

| Source Save Version | Language / Patch | Supported? | Details |
| :--- | :--- | :---: | :--- |
| **Japanese Original** | v1.00 ~ v1.04 (Retail / DLsite) | **Supported** | All official retail versions |
| **English Fan Translation** | Anime-Sharing / v1.04 patches | **Supported** | Fully compatible |
| **100% Clear Data Saves** | `Rance7_Sys.ASD` (All CGs & routes) | **Supported** | Unlock all CGs, clears & bonuses without grinding |
| **Chinese Fan Translation** | Alice Fan Patch / v1.04 | **Supported** | Fully compatible |

> **Note on Standalone MangaGamer Version**: If you previously bought MangaGamer's standalone digital release and its saves already use `KEY_CODE_Rance`, you can copy them directly without conversion. The converter will safely notify you if a file is already in the new format.

---

### 🚀 Quick Start (No Python Needed)

1. Go to the **[Releases page](../../releases)** and download `SengokuRanceSaveConverter.exe`.
2. Launch the application. It will automatically detect your Steam installation of *Sengoku Rance*.
3. Verify your source and destination directories (use **⇅ Swap Directories** if converting from Steam to legacy).
4. Click **【🚀 Start Conversion】**.
5. Once completed, your saves are converted, and a timestamped backup of your destination folder is automatically created.

---

### ⚠️ Steam Cloud Sync Notice

Before launching the game for the first time after conversion:
1. Right-click **Sengoku Rance** in your Steam Library -> **Properties** -> **General**.
2. Temporarily toggle **Steam Cloud OFF**.
3. Launch the game, verify that your save slots (1~48) and CG Gallery load properly.
4. Exit the game and turn Steam Cloud back ON. If prompted about a cloud conflict, choose **"Upload local files to Steam Cloud"**.

---

## 🛠️ 技术致谢与开源协议 (Acknowledgements & License)

- **System 4.0 Research**: 特别感谢开源开发者 [`nunuhara`](https://github.com/nunuhara/alice-tools) ([`alice-tools`](https://github.com/nunuhara/alice-tools)) 与 [`kichikuou`](https://github.com/kichikuou) ([`xsystem4`](https://github.com/kichikuou)) 对 AliceSoft System 4.0 引擎与存档数据格式的研究成果与开源贡献。  
  *Special thanks to [`nunuhara`](https://github.com/nunuhara/alice-tools) ([`alice-tools`](https://github.com/nunuhara/alice-tools)) and [`kichikuou`](https://github.com/kichikuou) ([`xsystem4`](https://github.com/kichikuou)) for their research and documentation on AliceSoft System 4.0 data structures and save file formats.*
- **License**: [GNU General Public License v3.0](LICENSE).
- **Disclaimer**: 本工具仅供个人数据迁移与单机存档备份交流使用。游戏资产与知识产权归原开发商 AliceSoft 及发行商所有。  
  *This tool is developed for game save preservation and personal data migration only. All game assets and copyrights belong to AliceSoft and MangaGamer / Shiravune.*

---

## 📝 更新日志 (Changelog)

### `v1.0.1`
- **新增**: 日文原版（`ランス７_*.ASD`）与中文 Windows 系统直接解压导致的乱码前缀（如 `愼嵓呔呥售_*.ASD`）自动识别与智能规范化重命名机制。
- **优化**: 导入 Steam 官方版时自动规范化为 `Rance7_%03d.ASD`、`Rance7_%03d.AS2` 与 `Rance7_Sys.ASD`，彻底解决进入游戏后无法识别存档的问题。
- **优化**: 转换日志中清晰显示文件名映射变更路径（例如 `愼嵓呔呥售_001.ASD -> Rance7_001.ASD`）。

### `v1.0.0`
- 首个正式开源版本，支持旧版战国兰斯与 Steam 官方版存档双向加解密转换、Steam 路径自动探测与自动备份。
