# -*- coding: utf-8 -*-
"""
=============================================================================
战国兰斯（兰斯7）旧版本存档 -> Steam官方版 转换与导入工具
=============================================================================
【背景说明】：
- 旧版本战国兰斯（如 v1.04 日文版/旧汉化版）存档内部的游戏识别钥匙为：KEY_CODE_ランス７（18字节）
- Steam 版战国兰斯游戏引擎校验的游戏识别钥匙为：KEY_CODE_Rance（15字节）
- 本脚本将自动把旧版存档进行解密解压、修正钥匙与内部数据块偏移量（-3字节），
  然后重新压缩加密，生成可供 Steam 版直接无缝读取的存档文件。
=============================================================================
"""

import os
import sys
import shutil
import struct
import zlib
from datetime import datetime

# ==================== AliceSoft 引擎算法常量定义 ====================
# MT19937 梅森旋转算法参数（AliceSoft System 4.0 专用）
MT_N = 624
MT_M = 397
MT_MATRIX_A = 0x9908B0DF
MT_UPPER_MASK = 0x80000000
MT_LOWER_MASK = 0x7FFFFFFF
MT_TEMPERING_MASK_B = 0x9D2C5680
MT_TEMPERING_MASK_C = 0xEFC60000

# AliceSoft GD11 存档加密专用种子密钥
GD11_ENCRYPT_KEY = 0x12320F

# 游戏内部识别钥匙串定义
OLD_KEY = b"KEY_CODE_\x83\x89\x83\x93\x83X\x82V\x00"  # 旧版日文钥匙：KEY_CODE_ランス７\0
NEW_KEY = b"KEY_CODE_Rance\x00"                         # Steam版英文钥匙：KEY_CODE_Rance\0


class MT19937:
    """
    梅森旋转伪随机数生成器（32位纯整数实现）
    用于 AliceSoft 存档的逐字节异或解密与加密
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
    读取并解密、解压一个 AliceSoft System 4.0 存档文件
    返回未压缩的原始数据（bytes）
    """
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # 校验头部标志（必须为 GD\x01\x01）
    if len(file_bytes) < 8 or file_bytes[:4] != b"GD\x01\x01":
        raise ValueError(f"不是合法的 AliceSoft GD 格式存档: {file_path}")

    raw_uncompressed_size = struct.unpack_from("<I", file_bytes, 4)[0]
    payload = bytearray(file_bytes[8:])

    # 如果首字节为 0x1A，表示数据经过了 MT19937 异或加密
    if payload and payload[0] == 0x1A:
        mt = MT19937(GD11_ENCRYPT_KEY)
        for i in range(len(payload)):
            payload[i] ^= (mt.genrand() & 0xFF)

    # 使用标准 zlib 解压缩
    decompressed_data = zlib.decompress(bytes(payload))
    if len(decompressed_data) != raw_uncompressed_size:
        print(f"【警告】解压大小 ({len(decompressed_data)}) 与标称大小 ({raw_uncompressed_size}) 不符: {file_path}")

    return decompressed_data


def compress_and_encrypt(raw_data: bytes, compression_level: int = 9) -> bytes:
    """
    将处理好的原始数据进行 zlib 压缩与 MT19937 加密，包装为合法的 GD\x01\x01 文件
    """
    compressed_bytes = bytearray(zlib.compress(raw_data, level=compression_level))

    # 使用 MT19937 算法加密压缩流
    mt = MT19937(GD11_ENCRYPT_KEY)
    for i in range(len(compressed_bytes)):
        compressed_bytes[i] ^= (mt.genrand() & 0xFF)

    # 组装 8 字节头部：魔数 "GD\x01\x01" + 4 字节未压缩大小（小端整数）
    header = b"GD\x01\x01" + struct.pack("<I", len(raw_data))
    return header + bytes(compressed_bytes)


def convert_gsave_data(old_raw: bytes) -> bytes:
    """
    将解压后的旧版 gsave 二进制数据转换为 Steam 版格式：
    1. 替换识别钥匙：KEY_CODE_ランス７ -> KEY_CODE_Rance
    2. 计算钥匙长度变化差值（-3 字节）
    3. 同步修改头部记录的 5 个数据块绝对偏移地址（全部减 3）
    """
    if not old_raw.startswith(OLD_KEY):
        raise ValueError("存档头部未找到旧版游戏识别钥匙串（KEY_CODE_ランス７）")

    # 钥匙长度差值（15 - 18 = -3 字节）
    delta = len(NEW_KEY) - len(OLD_KEY)

    # 解析头部结构
    pos = len(OLD_KEY)
    uk1, version, uk2, nr_ain_globals = struct.unpack_from("<iiii", old_raw, pos)
    pos += 16

    # 提取 5 个核心数据块的偏移量和计数
    rec_off, n_rec, glob_off, n_glob, str_off, n_str, arr_off, n_arr, kv_off, n_kv = struct.unpack_from(
        "<iiiiiiiiii", old_raw, pos
    )
    pos += 40

    # 重新打包调整后的偏移量
    new_offsets = struct.pack(
        "<iiiiiiiiii",
        rec_off + delta, n_rec,
        glob_off + delta, n_glob,
        str_off + delta, n_str,
        arr_off + delta, n_arr,
        kv_off + delta, n_kv
    )

    # 组装转换后的二进制流
    new_raw = (
        NEW_KEY +
        struct.pack("<iiii", uk1, version, uk2, nr_ain_globals) +
        new_offsets +
        old_raw[pos:]
    )
    return new_raw


def run_migration(source_dir: str, target_dir: str) -> None:
    """
    执行完整的备份、转换与迁移任务
    """
    print("=" * 68)
    print("  战国兰斯（兰斯7）旧版本存档 -> Steam 官方版 自动转换导入程序")
    print("=" * 68)
    print(f"【源存档目录】: {source_dir}")
    print(f"【目标 Steam 目录】: {target_dir}\n")

    if not os.path.exists(source_dir):
        print(f"【错误】找不到源存档目录: {source_dir}")
        return

    if not os.path.exists(target_dir):
        print(f"【错误】找不到 Steam 存档目录: {target_dir}")
        return

    # ---------------- 步骤 1：自动创建备份 ----------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    steam_parent = os.path.dirname(target_dir)
    backup_dir = os.path.join(steam_parent, f"SaveData_Backup_{timestamp}")

    print(">>> 正在备份当前 Steam 存档目录...")
    try:
        shutil.copytree(target_dir, backup_dir)
        print(f"【备份成功】原 Steam 存档已完整备份至:\n    {backup_dir}\n")
    except Exception as e:
        print(f"【备份失败】无法创建备份目录: {e}")
        print("为确保安全，已终止导入操作！")
        return

    # ---------------- 步骤 2：扫描并转换存档文件 ----------------
    source_files = sorted(os.listdir(source_dir))
    converted_count = 0
    skipped_count = 0
    failed_files = []

    print(">>> 开始逐个解析并转换存档...")

    for filename in source_files:
        ext = os.path.splitext(filename)[1].upper()
        source_file_path = os.path.join(source_dir, filename)
        target_file_path = os.path.join(target_dir, filename)

        # 战国兰斯的有效存档格式为 .ASD（进度/全局存档）和 .AS2（缩略元数据）
        if ext in [".ASD", ".AS2"]:
            # 跳过非 GD 格式的临时文件（如 MsgSkip.asd，该文件 Steam 版已有自带的有效缓存）
            if filename.lower() == "msgskip.asd":
                skipped_count += 1
                continue

            try:
                # 1. 解密解压
                raw_data = decrypt_and_decompress(source_file_path)

                # 2. 转换钥匙与偏移量
                converted_raw = convert_gsave_data(raw_data)

                # 3. 压缩加密
                new_encrypted_bytes = compress_and_encrypt(converted_raw)

                # 4. 写入 Steam 存档目录
                with open(target_file_path, "wb") as f_out:
                    f_out.write(new_encrypted_bytes)

                print(f"  [√] 成功转换: {filename:<16} (大小: {len(new_encrypted_bytes):>7} 字节)")
                converted_count += 1

            except Exception as ex:
                print(f"  [X] 转换失败: {filename} - {ex}")
                failed_files.append((filename, str(ex)))

        elif filename.lower() in ["msgskipflag.sav", "volume.sav"]:
            # 这两个设置文件格式完全一致，直接拷贝覆盖
            try:
                shutil.copy2(source_file_path, target_file_path)
                print(f"  [√] 直接同步: {filename}")
                converted_count += 1
            except Exception as ex:
                failed_files.append((filename, str(ex)))
        else:
            # key0104.dat 等旧版专有文件直接安全跳过
            print(f"  [-] 安全跳过旧版专用文件: {filename}")
            skipped_count += 1

    # ---------------- 步骤 3：输出统计与使用指引 ----------------
    print("\n" + "=" * 68)
    print("【转换导入完成统计】")
    print(f"  - 成功转换并导入文件数: {converted_count}")
    print(f"  - 安全跳过/保留文件数: {skipped_count}")
    print(f"  - 转换失败文件数:     {len(failed_files)}")

    if failed_files:
        print("\n【失败列表】:")
        for fn, err in failed_files:
            print(f"  - {fn}: {err}")
    else:
        print("\n【成功】全部存档文件均已 100% 成功转换并写入 Steam 目录！")
    print("=" * 68)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="战国兰斯旧版本存档 -> Steam 官方版 命令行转换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python convert_rance7_save.py --src \"D:\\OldSave\" --dst \"D:\\SteamSave\""
    )
    default_desktop_src = os.path.join(os.path.expanduser("~"), "Desktop", "战国兰斯", "SaveData")
    default_steam_dst = r"C:\Program Files (x86)\Steam\steamapps\common\Sengoku Rance\SaveData"

    parser.add_argument(
        "--src",
        default=default_desktop_src,
        help="待转换的旧版战国兰斯 SaveData 目录路径 (默认探测当前电脑桌面)"
    )
    parser.add_argument(
        "--dst",
        default=default_steam_dst,
        help="Steam 版 Sengoku Rance\\SaveData 目录路径"
    )
    args = parser.parse_args()

    run_migration(args.src, args.dst)
