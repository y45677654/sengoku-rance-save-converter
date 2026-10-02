# -*- coding: utf-8 -*-
"""
=============================================================================
战国兰斯（兰斯7）存档转换与导入工具 - 图形界面国际化版 (GUI i18n)
Sengoku Rance (Rance 7) Save Data Converter & Importer - Internationalized GUI
=============================================================================
【功能特点 / Features】：
1. 支持旧版（v1.00~v1.04 日文版/民间英化版/汉化版）与 Steam 官方版保存数据双向转换。
2. 自动检测电脑中的 Steam 安装路径及《战国兰斯》游戏存档位置。
3. 允许自由自定义源存档输入目录与目标导出目录，并提供一键对调与模式联动机制。
4. 转换前自动安全备份目标目录，杜绝丢档风险。
5. 支持中英双语 (简体中文 / English) 智能自适应系统语言，并提供实时一键切换。
6. 原生 Tkinter 编写，编译打包为无需 Python 环境的单文件免安装 EXE。

【开源协议 / License】：GPL-3.0
【技术致谢 / Acknowledgements】：
特别感谢开源开发者 nunuhara (alice-tools) 与 kichikuou (xsystem4) 对 AliceSoft 引擎与数据格式的研究成果。
=============================================================================
"""

import os
import re
import sys
import shutil
import struct
import zlib
import locale
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# ==================== AliceSoft 引擎底层加解密与转换核心 ====================

# MT19937 梅森旋转伪随机数生成算法核心参数（System 4.0 专用）
MT_N = 624
MT_M = 397
MT_MATRIX_A = 0x9908B0DF
MT_UPPER_MASK = 0x80000000
MT_LOWER_MASK = 0x7FFFFFFF
MT_TEMPERING_MASK_B = 0x9D2C5680
MT_TEMPERING_MASK_C = 0xEFC60000

# AliceSoft GD11 专有加密种子密钥
GD11_ENCRYPT_KEY = 0x12320F

# 游戏内部识别钥匙串定义
KEY_OLD = b"KEY_CODE_\x83\x89\x83\x93\x83X\x82V\x00"  # 旧版日文钥匙：KEY_CODE_ランス７\0（18字节）
KEY_STEAM = b"KEY_CODE_Rance\x00"                      # Steam版英文钥匙：KEY_CODE_Rance\0（15字节）


class MT19937:
    """
    梅森旋转算法（Mersenne Twister）32位整数版纯算法实现
    用于对 AliceSoft 引擎的压缩流进行逐字节异或混淆解密/加密
    """
    def __init__(self, seed: int):
        self.st = [0] * MT_N
        self.st[0] = seed & 0xFFFFFFFF
        for i in range(1, MT_N):
            self.st[i] = (69069 * self.st[i - 1]) & 0xFFFFFFFF
        self.i = MT_N

    def genrand(self) -> int:
        mag01 = [0, MT_MATRIX_A]
        if self.i >= MT_N:
            for kk in range(MT_N - MT_M):
                y = (self.st[kk] & MT_UPPER_MASK) | (self.st[kk + 1] & MT_LOWER_MASK)
                self.st[kk] = self.st[kk + MT_M] ^ (y >> 1) ^ mag01[y & 1]
            for kk in range(MT_N - MT_M, MT_N - 1):
                y = (self.st[kk] & MT_UPPER_MASK) | (self.st[kk + 1] & MT_LOWER_MASK)
                self.st[kk] = self.st[kk + (MT_M - MT_N)] ^ (y >> 1) ^ mag01[y & 1]
            y = (self.st[MT_N - 1] & MT_UPPER_MASK) | (self.st[0] & MT_LOWER_MASK)
            self.st[MT_N - 1] = self.st[MT_M - 1] ^ (y >> 1) ^ mag01[y & 1]
            self.i = 0

        y = self.st[self.i]
        self.i += 1
        y ^= (y >> 11)
        y ^= (y << 7) & MT_TEMPERING_MASK_B
        y ^= (y << 15) & MT_TEMPERING_MASK_C
        y ^= (y >> 18)
        return y & 0xFFFFFFFF


def decrypt_and_decompress(file_path: str) -> bytes:
    """
    读取、解密并解压一个 AliceSoft System 4.0 存档文件
    返回未压缩的原始二进制流
    """
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # 校验容器魔数（必须为 GD\x01\x01）
    if len(file_bytes) < 8 or file_bytes[:4] != b"GD\x01\x01":
        raise ValueError("不是合法的 AliceSoft GD 格式存档 / Not a valid AliceSoft GD save")

    raw_uncompressed_size = struct.unpack_from("<I", file_bytes, 4)[0]
    payload = bytearray(file_bytes[8:])

    # 若首字节为 0x1A，表示经过了 MT19937 异或加密
    if payload and payload[0] == 0x1A:
        mt = MT19937(GD11_ENCRYPT_KEY)
        for i in range(len(payload)):
            payload[i] ^= (mt.genrand() & 0xFF)

    # zlib 解压
    decompressed = zlib.decompress(bytes(payload))
    return decompressed


def compress_and_encrypt(raw_data: bytes, compression_level: int = 9) -> bytes:
    """
    将二进制原始数据重新进行 zlib 压缩并加上 MT19937 异或加密，生成标准的 GD 容器文件
    """
    compressed = bytearray(zlib.compress(raw_data, level=compression_level))

    # MT19937 重新加密
    mt = MT19937(GD11_ENCRYPT_KEY)
    for i in range(len(compressed)):
        compressed[i] ^= (mt.genrand() & 0xFF)

    # 包装头部：GD\x01\x01 + 原始解压后长度（4字节小端整型）
    header = b"GD\x01\x01" + struct.pack("<I", len(raw_data))
    return header + bytes(compressed)


def convert_gsave_buffer(old_raw: bytes, mode: str = "old_to_steam") -> bytes:
    """
    核心转换逻辑：替换钥匙串并精准平移 5 个数据块偏移地址
    - mode="old_to_steam": KEY_CODE_ランス７ -> KEY_CODE_Rance (偏移量各减 3)
    - mode="steam_to_old": KEY_CODE_Rance -> KEY_CODE_ランス７ (偏移量各加 3)
    """
    if mode == "old_to_steam":
        src_key = KEY_OLD
        dst_key = KEY_STEAM
    elif mode == "steam_to_old":
        src_key = KEY_STEAM
        dst_key = KEY_OLD
    else:
        # 智能自动探测钥匙
        if old_raw.startswith(KEY_OLD):
            src_key, dst_key = KEY_OLD, KEY_STEAM
        elif old_raw.startswith(KEY_STEAM):
            src_key, dst_key = KEY_STEAM, KEY_OLD
        else:
            raise ValueError("未在存档头部找到已知的游戏识别钥匙串 / Unknown game key in save header")

    if not old_raw.startswith(src_key):
        raise ValueError("当前存档钥匙不匹配，未能识别为预期格式 / Save game key mismatch")

    delta = len(dst_key) - len(src_key)

    # 解析 gsave 头部结构
    pos = len(src_key)
    uk1, version, uk2, nr_ain_globals = struct.unpack_from("<iiii", old_raw, pos)
    pos += 16

    # 读取 5 个内部核心数据区的偏移量及元素计数
    rec_off, n_rec, glob_off, n_glob, str_off, n_str, arr_off, n_arr, kv_off, n_kv = struct.unpack_from(
        "<iiiiiiiiii", old_raw, pos
    )
    pos += 40

    # 重新组装经平移后的偏移量表
    new_offsets = struct.pack(
        "<iiiiiiiiii",
        rec_off + delta, n_rec,
        glob_off + delta, n_glob,
        str_off + delta, n_str,
        arr_off + delta, n_arr,
        kv_off + delta, n_kv
    )

    # 拼装全新二进制流（保留后续全部游戏状态、武将、地图与旗标数据）
    new_raw = (
        dst_key +
        struct.pack("<iiii", uk1, version, uk2, nr_ain_globals) +
        new_offsets +
        old_raw[pos:]
    )
    return new_raw


# ==================== Steam 路径智能自动探测器 ====================

def detect_steam_rance_path() -> str:
    """
    智能检测本机 Steam 版《战国兰斯》的 SaveData 路径
    1. 探测常见默认安装路径
    2. 探测注册表中的 Steam 安装根路径
    3. 解析 Steam 的 libraryfolders.vdf 探测所有外部游戏库磁盘
    """
    candidate = r"C:\Program Files (x86)\Steam\steamapps\common\Sengoku Rance\SaveData"
    if os.path.isdir(candidate):
        return candidate

    candidate_32 = r"C:\Program Files\Steam\steamapps\common\Sengoku Rance\SaveData"
    if os.path.isdir(candidate_32):
        return candidate_32

    steam_path = None
    try:
        import winreg
        for key_path in [r"SOFTWARE\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                    val, _ = winreg.QueryValueEx(k, "InstallPath")
                    if val and os.path.isdir(val):
                        steam_path = val
                        break
            except Exception:
                pass

        if not steam_path:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                val, _ = winreg.QueryValueEx(k, "SteamPath")
                if val and os.path.isdir(val):
                    steam_path = val
    except Exception:
        pass

    if steam_path:
        p = os.path.join(steam_path, "steamapps", "common", "Sengoku Rance", "SaveData")
        if os.path.isdir(p):
            return p

        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                paths = re.findall(r'"path"\s+"([^"]+)"', content)
                for lp in paths:
                    lp_clean = lp.replace(r"\\", os.sep)
                    candidate = os.path.join(lp_clean, "steamapps", "common", "Sengoku Rance", "SaveData")
                    if os.path.isdir(candidate):
                        return candidate
            except Exception:
                pass

    return ""


# ==================== 国际化多语言文本字典 (i18n) ====================

APP_VERSION = "v1.0.0"

I18N = {
    "zh_CN": {
        "window_title": f"战国兰斯 (兰斯7) 存档转换导入工具 {APP_VERSION}",
        "header_title": f"战国兰斯存档转换器 (兰斯7) {APP_VERSION}",
        "header_subtitle": "支持旧版本与 Steam 官方版保存数据双向转换",
        "about_btn": "ℹ️ 版本与兼容性说明",
        "lang_label": "🌐 语言 / Language:",
        "src_group": " [1] 源存档读取目录 (输入) ",
        "dst_group": " [2] 转换后导出目录 (目标) ",
        "browse_btn": "浏览文件夹...",
        "swap_btn": "⇅ 对调源目录与目标目录",
        "detect_btn": "🔄 自动检测 Steam 目录",
        "backup_chk": "转换前备份目标目录中的现有文件 (强烈建议勾选)",
        "mode_label": "转换模式:",
        "modes": [
            "旧版本格式 -> Steam 官方版",
            "Steam 官方版 -> 旧版本格式",
            "自动识别格式"
        ],
        "start_btn": "🚀 开始转换",
        "converting_btn": "正在转换中，请稍候...",
        "log_group": " 运行日志与状态输出 ",
        "about_title": "版本与兼容性说明",
        "about_text": (
            f"战国兰斯（兰斯7）存档转换与导入工具 {APP_VERSION}\n"
            "=========================================\n\n"
            "【转换器版本】：v1.0.0 (正式版 / Initial Release)\n"
            "【开源协议】：GNU General Public License v3.0\n\n"
            "【适用的旧版游戏】：\n"
            "  • 《戦国ランス》日文原版 (v1.00 ~ v1.04 各版本)\n"
            "  • 汉化补丁版 / 早期民间英化版\n"
            "  • 系统全 CG/全回想进度存档 (Rance7_Sys.ASD)\n"
            "  • (判断标准: 存档内部含 KEY_CODE_ランス７ 标识即可兼容)\n\n"
            "【适用的 Steam 官方版】：\n"
            "  • Steam 官方正版《Sengoku Rance》(AppID: 1245050)\n"
            "  • 支持游戏内置所有语言 (English / Japanese)\n"
            "  • 官方后续小版本更新补丁持续受支持\n\n"
            "【技术致谢】：\n"
            "  特别感谢开源开发者 nunuhara (alice-tools) 与 kichikuou\n"
            "  (xsystem4) 对 AliceSoft 引擎与存档数据格式的研究成果。"
        ),
        "log_desktop_found": "[提示] 已自动定位桌面旧版存档目录: {path}",
        "log_steam_found": "[成功] 自动检测到 Steam 战国兰斯存档路径:\n       {path}",
        "log_steam_not_found": "[提示] 未能自动定位 Steam 战国兰斯目录，请手动点击【浏览文件夹...】选择。",
        "choose_src_title": "选择源存档文件夹",
        "choose_dst_title": "选择导出目标存档文件夹",
        "err_invalid_src": "请先选择合法的【源存档目录】！",
        "err_invalid_dst": "请先选择合法的【目标存档目录】！",
        "err_same_dir": "源目录与目标目录不能为同一个文件夹！",
        "log_swap_paths": "[提示] 已对调源读取目录与目标导出目录。",
        "log_auto_swapped_to_steam": "[提示] 转换模式已切换为【Steam 导出至旧版】，已自动为您对调源目录与目标目录。",
        "log_auto_swapped_to_old": "[提示] 转换模式已切换为【旧版导入至 Steam】，已自动为您对调源目录与目标目录。",
        "log_task_start": "[{time}] 开始执行存档转换任务...",
        "log_src_dir": "源读取目录: {path}",
        "log_dst_dir": "目标导出目录: {path}",
        "log_backup_creating": ">>> 正在创建备份: {path}",
        "log_backup_success": "[√] 备份成功创建，原有存档已妥善保存！",
        "log_backup_failed": "[X] 备份失败: {err}，为确保数据安全，转换终止。",
        "backup_err_title": "备份错误",
        "backup_err_msg": "无法备份目标目录:\n{err}",
        "log_detected_saves": ">>> 共检测到 {count} 个主存档与元数据文件，正在逐一处理...",
        "log_skip_msgskip": "  [-] 跳过临时缓存文件: {file} (目标环境自带默认有效缓存)",
        "log_converted_file": "  [√] 成功转换: {file:<18} (大小: {size} 字节)",
        "log_failed_file": "  [X] 处理失败: {file} - {err}",
        "log_sync_config": "  [√] 同步设置: {file}",
        "log_skip_key": "  [-] 跳过旧版专用授权文件: {file}",
        "log_task_finish": "任务完成！成功转换: {success} 个文件，失败: {failed} 个。",
        "warning_partial_title": "部分完成",
        "warning_partial_msg": "转换完成，但有 {count} 个文件处理失败，详情请查看日志框。",
        "success_title": "转换成功",
        "success_msg": (
            "保存数据已完成转换并成功写入目标目录。\n\n"
            "注意事项：\n"
            "若目标环境为 Steam 版本，首次启动游戏前建议在 Steam 属性中暂时关闭“云存档同步”，待游戏内验证存档无误后，再根据需要开启。"
        ),
        "fatal_err_title": "错误",
        "fatal_err_msg": "发生意外错误:\n{err}"
    },
    "en_US": {
        "window_title": f"Sengoku Rance Save Data Converter {APP_VERSION}",
        "header_title": f"Sengoku Rance Save Converter {APP_VERSION}",
        "header_subtitle": "Supports bi-directional conversion between Legacy and Steam save data.",
        "about_btn": "ℹ️ Version & Compatibility",
        "lang_label": "🌐 Language:",
        "src_group": " [1] Source Save Directory (Input) ",
        "dst_group": " [2] Destination Save Directory (Output) ",
        "browse_btn": "Browse...",
        "swap_btn": "⇅ Swap Directories",
        "detect_btn": "🔄 Auto-Detect Steam Path",
        "backup_chk": "Backup existing files in destination directory before converting (Strongly Recommended)",
        "mode_label": "Mode:",
        "modes": [
            "Legacy Format -> Steam Official",
            "Steam Official -> Legacy Format",
            "Auto-Detect Format"
        ],
        "start_btn": "🚀 Start Conversion",
        "converting_btn": "Converting in progress, please wait...",
        "log_group": " Conversion Log & Status ",
        "about_title": "Version & Compatibility Information",
        "about_text": (
            f"Sengoku Rance (Rance 7) Save Data Converter {APP_VERSION}\n"
            "=========================================\n\n"
            "【Converter Version】: v1.0.0 (Official Release)\n"
            "【License】: GNU General Public License v3.0\n\n"
            "【Supported Legacy Game Versions】:\n"
            "  • Sengoku Rance Japanese Original (v1.00 ~ v1.04)\n"
            "  • English / Chinese Fan-Translation Patches\n"
            "  • 100% Clear Data / Full CG Save files (Rance7_Sys.ASD)\n"
            "  • (Criterion: Any save with KEY_CODE_ランス７ header is supported)\n\n"
            "【Supported Target Game Versions (Steam Official)】:\n"
            "  • Steam Official Sengoku Rance (AppID: 1245050)\n"
            "  • Supports all in-game languages (English & Japanese)\n"
            "  • Future minor updates are continuously supported\n\n"
            "【Acknowledgements】:\n"
            "  Special thanks to nunuhara (alice-tools) and kichikuou\n"
            "  (xsystem4) for documenting AliceSoft System 4.0 save file formats."
        ),
        "log_desktop_found": "[Notice] Auto-located old save folder on Desktop: {path}",
        "log_steam_found": "[Success] Auto-detected Steam Sengoku Rance save folder:\n          {path}",
        "log_steam_not_found": "[Notice] Could not auto-detect Steam directory. Please click [Browse...] manually.",
        "choose_src_title": "Select Source Save Directory",
        "choose_dst_title": "Select Destination Save Directory",
        "err_invalid_src": "Please select a valid [Source Save Directory] first!",
        "err_invalid_dst": "Please select a valid [Destination Save Directory] first!",
        "err_same_dir": "Source and destination directories cannot be the same!",
        "log_swap_paths": "[Notice] Swapped source and destination directories.",
        "log_auto_swapped_to_steam": "[Notice] Switched mode to [Steam -> Legacy], directories auto-swapped.",
        "log_auto_swapped_to_old": "[Notice] Switched mode to [Legacy -> Steam], directories auto-swapped.",
        "log_task_start": "[{time}] Starting save data conversion task...",
        "log_src_dir": "Source Directory: {path}",
        "log_dst_dir": "Destination Directory: {path}",
        "log_backup_creating": ">>> Creating backup: {path}",
        "log_backup_success": "[√] Backup successfully created! Existing saves are safe.",
        "log_backup_failed": "[X] Backup failed: {err}. Conversion aborted for safety.",
        "backup_err_title": "Backup Error",
        "backup_err_msg": "Failed to backup target directory:\n{err}",
        "log_detected_saves": ">>> Detected {count} save files & metadata items, processing...",
        "log_skip_msgskip": "  [-] Skipped cache file: {file} (Target environment has valid default cache)",
        "log_converted_file": "  [√] Converted: {file:<18} (Size: {size} bytes)",
        "log_failed_file": "  [X] Failed:    {file} - {err}",
        "log_sync_config": "  [√] Synced config: {file}",
        "log_skip_key": "  [-] Safely skipped legacy key file: {file}",
        "log_task_finish": "Task finished! Successfully converted: {success}, Failed: {failed}.",
        "warning_partial_title": "Partially Completed",
        "warning_partial_msg": "Conversion finished, but {count} file(s) failed. Check the log box for details.",
        "success_title": "Conversion Successful",
        "success_msg": (
            "Save data has been converted and written to the destination directory successfully.\n\n"
            "Notice:\n"
            "If target is Steam, it is recommended to temporarily disable Steam Cloud before first launch to prevent cloud overwrite. Re-enable after verification."
        ),
        "fatal_err_title": "Error",
        "fatal_err_msg": "An unexpected error occurred:\n{err}"
    }
}


def detect_system_language() -> str:
    """自动探测当前操作系统的默认语言环境"""
    try:
        lang_tuple = locale.getdefaultlocale()
        if lang_tuple and lang_tuple[0]:
            code = lang_tuple[0].lower()
            if code.startswith("zh"):
                return "zh_CN"
    except Exception:
        pass
    return "en_US"


# ==================== Tkinter 图形用户界面 (GUI) ====================

class RanceSaveConverterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        # 初始语言自适应选择
        self.current_lang = detect_system_language()

        self.root.title(self.t("window_title"))
        self.root.geometry("780x620")
        self.root.minsize(740, 560)

        # 尝试设置 Windows 原生样式
        self.style = ttk.Style()
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")

        self.setup_ui()
        self.auto_fill_paths()

    def t(self, key: str, **kwargs) -> str:
        """根据当前选定语言获取对应的本地化字符串"""
        text = I18N.get(self.current_lang, I18N["zh_CN"]).get(key, "")
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def show_about_dialog(self):
        """展示转换器版本号与游戏版本兼容性详细说明"""
        messagebox.showinfo(self.t("about_title"), self.t("about_text"))

    def switch_language(self, event=None):
        """实时响应语言切换事件并动态刷新全部界面文字"""
        selected = self.lang_combo.get()
        if "English" in selected:
            self.current_lang = "en_US"
        else:
            self.current_lang = "zh_CN"

        self.update_ui_texts()

    def update_ui_texts(self):
        """动态刷新界面所有控件的文本内容"""
        self.root.title(self.t("window_title"))
        self.title_lbl.config(text=self.t("header_title"))
        self.subtitle_lbl.config(text=self.t("header_subtitle"))
        self.about_btn.config(text=self.t("about_btn"))
        self.lang_lbl.config(text=self.t("lang_label"))

        self.src_group.config(text=self.t("src_group"))
        self.src_btn.config(text=self.t("browse_btn"))
        self.swap_btn.config(text=self.t("swap_btn"))

        self.dst_group.config(text=self.t("dst_group"))
        self.dst_btn.config(text=self.t("browse_btn"))
        self.detect_btn.config(text=self.t("detect_btn"))
        self.backup_chk.config(text=self.t("backup_chk"))

        self.mode_lbl.config(text=self.t("mode_label"))
        current_idx = self.mode_combo.current()
        self.mode_combo['values'] = self.t("modes")
        if 0 <= current_idx < len(self.t("modes")):
            self.mode_combo.current(current_idx)
        else:
            self.mode_combo.current(0)

        self.start_btn.config(text=self.t("start_btn"))
        self.log_group.config(text=self.t("log_group"))

    def swap_paths(self):
        """一键对调源输入目录与目标导出目录，并智能联动模式"""
        src = self.src_var.get()
        dst = self.dst_var.get()
        self.src_var.set(dst)
        self.dst_var.set(src)

        # 智能对调模式（若当前是 0 则切为 1，若当前是 1 则切为 0）
        cur_idx = self.mode_combo.current()
        if cur_idx == 0:
            self.mode_combo.current(1)
        elif cur_idx == 1:
            self.mode_combo.current(0)

        self.log(self.t("log_swap_paths"))

    def on_mode_change(self, event=None):
        """当用户在下拉框切换转换模式时，智能判断并自动对调目录顺序"""
        cur_idx = self.mode_combo.current()
        src = self.src_var.get().strip().lower()
        dst = self.dst_var.get().strip().lower()

        # 如果切到模式 1 (Steam -> 旧版)：
        # 如果当前目标框像是 Steam (包含 steam 或 sengoku rance)，而源框不像 steam
        if cur_idx == 1:
            if ("steam" in dst or "sengoku" in dst) and ("steam" not in src and "sengoku" not in src):
                s_real = self.src_var.get()
                d_real = self.dst_var.get()
                self.src_var.set(d_real)
                self.dst_var.set(s_real)
                self.log(self.t("log_auto_swapped_to_steam"))

        # 如果切回模式 0 (旧版 -> Steam)：
        elif cur_idx == 0:
            if ("steam" in src or "sengoku" in src) and ("steam" not in dst and "sengoku" not in dst):
                s_real = self.src_var.get()
                d_real = self.dst_var.get()
                self.src_var.set(d_real)
                self.dst_var.set(s_real)
                self.log(self.t("log_auto_swapped_to_old"))

    def setup_ui(self):
        # 顶部标题栏装饰卡片
        header_frame = tk.Frame(self.root, bg="#2C3E50", padx=16, pady=12)
        header_frame.pack(fill=tk.X)

        title_container = tk.Frame(header_frame, bg="#2C3E50")
        title_container.pack(fill=tk.X)

        self.title_lbl = tk.Label(
            title_container,
            text=self.t("header_title"),
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#ECF0F1",
            bg="#2C3E50"
        )
        self.title_lbl.pack(side=tk.LEFT)

        # 语言切换下拉框与关于按钮容器
        top_right_box = tk.Frame(title_container, bg="#2C3E50")
        top_right_box.pack(side=tk.RIGHT)

        self.about_btn = tk.Button(
            top_right_box,
            text=self.t("about_btn"),
            font=("Microsoft YaHei UI", 9),
            bg="#34495E",
            fg="#ECF0F1",
            activebackground="#4A6572",
            activeforeground="white",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.show_about_dialog
        )
        self.about_btn.pack(side=tk.RIGHT)

        self.lang_combo = ttk.Combobox(
            top_right_box,
            values=["简体中文 (Chinese)", "English (英语)"],
            state="readonly",
            width=16,
            font=("Microsoft YaHei UI", 9)
        )
        self.lang_combo.current(0 if self.current_lang == "zh_CN" else 1)
        self.lang_combo.pack(side=tk.RIGHT, padx=(0, 10))
        self.lang_combo.bind("<<ComboboxSelected>>", self.switch_language)

        self.lang_lbl = tk.Label(
            top_right_box,
            text=self.t("lang_label"),
            font=("Microsoft YaHei UI", 9),
            fg="#BDC3C7",
            bg="#2C3E50"
        )
        self.lang_lbl.pack(side=tk.RIGHT, padx=(0, 4))

        self.subtitle_lbl = tk.Label(
            header_frame,
            text=self.t("header_subtitle"),
            font=("Microsoft YaHei UI", 9),
            fg="#BDC3C7",
            bg="#2C3E50"
        )
        self.subtitle_lbl.pack(anchor=tk.W, pady=(4, 0))

        # 主工作区卡片
        main_frame = ttk.Frame(self.root, padding="16 12 16 12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # [1] 源存档读取目录设置
        self.src_group = ttk.LabelFrame(main_frame, text=self.t("src_group"), padding=10)
        self.src_group.pack(fill=tk.X, pady=(0, 4))

        self.src_var = tk.StringVar()
        src_entry = ttk.Entry(self.src_group, textvariable=self.src_var, font=("Consolas", 9))
        src_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.src_btn = ttk.Button(self.src_group, text=self.t("browse_btn"), command=self.browse_src_dir)
        self.src_btn.pack(side=tk.RIGHT)

        # 中间对调按钮条
        swap_bar = ttk.Frame(main_frame)
        swap_bar.pack(fill=tk.X, pady=(2, 4))

        self.swap_btn = ttk.Button(
            swap_bar,
            text=self.t("swap_btn"),
            command=self.swap_paths
        )
        self.swap_btn.pack(anchor=tk.CENTER, pady=2)

        # [2] 目标导出目录设置
        self.dst_group = ttk.LabelFrame(main_frame, text=self.t("dst_group"), padding=10)
        self.dst_group.pack(fill=tk.X, pady=(0, 10))

        dst_input_frame = ttk.Frame(self.dst_group)
        dst_input_frame.pack(fill=tk.X)

        self.dst_var = tk.StringVar()
        dst_entry = ttk.Entry(dst_input_frame, textvariable=self.dst_var, font=("Consolas", 9))
        dst_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.dst_btn = ttk.Button(dst_input_frame, text=self.t("browse_btn"), command=self.browse_dst_dir)
        self.dst_btn.pack(side=tk.RIGHT)

        # 辅助功能行（重新探测按钮与模式）
        sub_row = ttk.Frame(self.dst_group)
        sub_row.pack(fill=tk.X, pady=(6, 0))

        self.detect_btn = ttk.Button(sub_row, text=self.t("detect_btn"), command=self.auto_detect_steam)
        self.detect_btn.pack(side=tk.LEFT)

        self.backup_var = tk.BooleanVar(value=True)
        self.backup_chk = ttk.Checkbutton(sub_row, text=self.t("backup_chk"), variable=self.backup_var)
        self.backup_chk.pack(side=tk.RIGHT)

        # [3] 转换模式与启动按钮
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(4, 10))

        self.mode_lbl = ttk.Label(action_frame, text=self.t("mode_label"), font=("Microsoft YaHei UI", 9))
        self.mode_lbl.pack(side=tk.LEFT, padx=(0, 4))

        self.mode_combo = ttk.Combobox(
            action_frame,
            values=self.t("modes"),
            state="readonly",
            width=32
        )
        self.mode_combo.pack(side=tk.LEFT)
        self.mode_combo.current(0)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)

        self.start_btn = tk.Button(
            action_frame,
            text=self.t("start_btn"),
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="#27AE60",
            fg="white",
            activebackground="#2ECC71",
            activeforeground="white",
            relief=tk.FLAT,
            padx=18,
            pady=4,
            command=self.start_conversion_thread
        )
        self.start_btn.pack(side=tk.RIGHT)

        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        # [4] 运行日志输出框
        self.log_group = ttk.LabelFrame(main_frame, text=self.t("log_group"), padding=6)
        self.log_group.pack(fill=tk.BOTH, expand=True)

        self.log_text = ScrolledText(
            self.log_group,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#F9FAFC",
            fg="#2C3E50"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str):
        """线程安全地在日志区域追加输出"""
        def _append():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        self.root.after(0, _append)

    def auto_fill_paths(self):
        """启动时自动尝试填充常用路径"""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        old_candidate = os.path.join(desktop, "战国兰斯", "SaveData")
        if os.path.isdir(old_candidate):
            self.src_var.set(old_candidate)
            self.log(self.t("log_desktop_found", path=old_candidate))

        self.auto_detect_steam()

    def auto_detect_steam(self):
        detected = detect_steam_rance_path()
        if detected:
            self.dst_var.set(detected)
            self.log(self.t("log_steam_found", path=detected))
        else:
            self.log(self.t("log_steam_not_found"))

    def browse_src_dir(self):
        d = filedialog.askdirectory(title=self.t("choose_src_title"), initialdir=self.src_var.get() or None)
        if d:
            self.src_var.set(os.path.normpath(d))

    def browse_dst_dir(self):
        d = filedialog.askdirectory(title=self.t("choose_dst_title"), initialdir=self.dst_var.get() or None)
        if d:
            self.dst_var.set(os.path.normpath(d))

    def start_conversion_thread(self):
        """使用独立工作线程执行转换，保证界面流畅不卡顿"""
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()

        if not src or not os.path.isdir(src):
            messagebox.showerror(self.t("fatal_err_title"), self.t("err_invalid_src"))
            return

        if not dst or not os.path.isdir(dst):
            messagebox.showerror(self.t("fatal_err_title"), self.t("err_invalid_dst"))
            return

        if os.path.abspath(src).lower() == os.path.abspath(dst).lower():
            messagebox.showerror(self.t("fatal_err_title"), self.t("err_same_dir"))
            return

        self.start_btn.config(state=tk.DISABLED, text=self.t("converting_btn"))
        self.progress_var.set(0)

        # 启动转换后台工作线程
        t = threading.Thread(target=self.do_conversion, args=(src, dst))
        t.daemon = True
        t.start()

    def do_conversion(self, src: str, dst: str):
        try:
            self.log("=" * 64)
            self.log(self.t("log_task_start", time=datetime.now().strftime('%H:%M:%S')))
            self.log(self.t("log_src_dir", path=src))
            self.log(self.t("log_dst_dir", path=dst))

            # 1. 自动备份目标目录
            if self.backup_var.get():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dst = os.path.join(os.path.dirname(dst), f"SaveData_Backup_{timestamp}")
                self.log(self.t("log_backup_creating", path=backup_dst))
                try:
                    shutil.copytree(dst, backup_dst)
                    self.log(self.t("log_backup_success"))
                except Exception as b_err:
                    self.log(self.t("log_backup_failed", err=b_err))
                    self.root.after(0, lambda: messagebox.showerror(self.t("backup_err_title"), self.t("backup_err_msg", err=b_err)))
                    return

            # 2. 获取源文件列表
            source_files = sorted([f for f in os.listdir(src)])
            save_files = [
                f for f in source_files 
                if os.path.splitext(f)[1].upper() in [".ASD", ".AS2"] 
                and f.lower() != "msgskip.asd"
            ]

            total_items = len(save_files) + 2  # 包含 Volume.sav 与 MsgSkipFlag.sav
            processed = 0
            converted_success = 0
            failures = []

            # 获取转换模式索引
            combo_idx = self.mode_combo.current()
            mode_map = ["old_to_steam", "steam_to_old", "auto"]
            selected_mode = mode_map[combo_idx] if 0 <= combo_idx < len(mode_map) else "old_to_steam"

            self.log(self.t("log_detected_saves", count=len(save_files)))

            for fn in source_files:
                ext = os.path.splitext(fn)[1].upper()
                src_fp = os.path.join(src, fn)
                dst_fp = os.path.join(dst, fn)

                if ext in [".ASD", ".AS2"]:
                    if fn.lower() == "msgskip.asd":
                        self.log(self.t("log_skip_msgskip", file=fn))
                        continue

                    try:
                        raw = decrypt_and_decompress(src_fp)
                        converted = convert_gsave_buffer(raw, mode=selected_mode)
                        encrypted = compress_and_encrypt(converted)
                        with open(dst_fp, "wb") as f_out:
                            f_out.write(encrypted)
                        converted_success += 1
                        self.log(self.t("log_converted_file", file=fn, size=len(encrypted)))
                    except Exception as ex:
                        failures.append((fn, str(ex)))
                        self.log(self.t("log_failed_file", file=fn, err=ex))

                    processed += 1
                    pct = min(100.0, (processed / max(1, total_items)) * 100)
                    self.root.after(0, lambda p=pct: self.progress_var.set(p))

                elif fn.lower() in ["volume.sav", "msgskipflag.sav"]:
                    try:
                        shutil.copy2(src_fp, dst_fp)
                        self.log(self.t("log_sync_config", file=fn))
                    except Exception as ex:
                        failures.append((fn, str(ex)))
                    processed += 1
                    pct = min(100.0, (processed / max(1, total_items)) * 100)
                    self.root.after(0, lambda p=pct: self.progress_var.set(p))

                elif fn.lower() == "key0104.dat":
                    self.log(self.t("log_skip_key", file=fn))

            self.progress_var.set(100)
            self.log("=" * 64)
            self.log(self.t("log_task_finish", success=converted_success, failed=len(failures)))

            if failures:
                self.root.after(0, lambda: messagebox.showwarning(
                    self.t("warning_partial_title"),
                    self.t("warning_partial_msg", count=len(failures))
                ))
            else:
                self.root.after(0, lambda: messagebox.showinfo(
                    self.t("success_title"),
                    self.t("success_msg")
                ))

        except Exception as global_ex:
            self.log(f"[Fatal] {global_ex}")
            self.root.after(0, lambda: messagebox.showerror(
                self.t("fatal_err_title"),
                self.t("fatal_err_msg", err=global_ex)
            ))
        finally:
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL, text=self.t("start_btn")))


def main():
    root = tk.Tk()
    app = RanceSaveConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
