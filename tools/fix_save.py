#!/usr/bin/env python3
"""
fix_save.py - GTA IV Save Game Repair & Converter Utility for macIV
===================================================================
Repairs and adapts GTA IV save files (SGTA4xx) so they load seamlessly in macIV:
- Appends missing 12-byte XLive container footers (truncated by GTASnP / web tools).
- Re-calculates and updates the IEEE 802.3 CRC32 checksum.
- Fixes header size mismatches (e.g. from downgraded Complete Edition saves).
- Backs up original save files with .bak extension before modifying.
- Supports importing saves directly into the macIV user savegames directory.
"""

import sys
import os
import glob
import struct
import zlib
import shutil
import argparse

DEFAULT_SAVE_DIR = os.path.expanduser(
    "~/Library/Application Support/gtaiv/drive_c/Documents and Settings/Player/Local Settings/Application Data/Rockstar Games/GTA IV/savegames/user_ee000000deadc0de"
)

def repair_save_file(filepath, verbose=True):
    if not os.path.isfile(filepath):
        if verbose:
            print(f"[-] File not found: {filepath}")
        return False

    with open(filepath, "rb") as f:
        data = bytearray(f.read())

    if len(data) < 272:
        if verbose:
            print(f"[-] {os.path.basename(filepath)}: File too small ({len(data)} bytes) to be a GTA IV save.")
        return False

    tag = data[12:16]
    if tag != b"SAVE":
        if verbose:
            print(f"[-] {os.path.basename(filepath)}: Invalid header tag ({tag!r}), expected b'SAVE'.")
        return False

    # Extract save title from UTF-16LE block at offset 16..272
    try:
        title = data[16:272].decode("utf-16le").split("\x00")[0].strip()
    except Exception:
        title = "Unknown Mission"
    if not title:
        title = "Auto-Save / Empty"

    # Find "END\0" terminator from end of file
    end_idx = data.rfind(b"END\x00")
    if end_idx == -1:
        if verbose:
            print(f"[-] {os.path.basename(filepath)}: Corrupt save file (missing 'END\\0' terminator).")
        return False

    inner_len = end_idx + 4
    target_size = inner_len + 12

    # Compute CRC32 over inner body bytes (from byte 16 up to inner_len)
    body = data[16:inner_len]
    expected_crc = zlib.crc32(body) & 0xFFFFFFFF

    current_hdr_size = struct.unpack_from("<I", data, 4)[0]
    has_footer = (len(data) >= target_size)
    current_crc = struct.unpack_from("<I", data, inner_len)[0] if has_footer else 0

    needs_repair = False
    reasons = []

    if len(data) != target_size:
        needs_repair = True
        reasons.append(f"file length {len(data)} != {target_size} (missing/invalid footer)")
    if current_hdr_size != target_size:
        needs_repair = True
        reasons.append(f"header size {current_hdr_size} != {target_size}")
    if current_crc != expected_crc:
        needs_repair = True
        reasons.append(f"CRC32 0x{current_crc:08X} != 0x{expected_crc:08X}")

    if not needs_repair:
        if verbose:
            print(f"[✔] {os.path.basename(filepath)}: Already valid ('{title}', size={len(data)}, CRC=0x{expected_crc:08X})")
        return True

    # Backup original
    bak_path = filepath + ".bak"
    if not os.path.exists(bak_path):
        shutil.copy2(filepath, bak_path)

    # Re-structure save data
    footer = struct.pack("<I", expected_crc) + b"\xCD\xCD\xCD\xCD" + b"imag"
    repaired_data = data[:inner_len] + footer
    struct.pack_into("<I", repaired_data, 4, target_size)

    with open(filepath, "wb") as f:
        f.write(repaired_data)

    if verbose:
        reason_str = ", ".join(reasons)
        print(f"[+] Fixed {os.path.basename(filepath)}: '{title}' ({reason_str})")
        print(f"    New size: {len(repaired_data)} bytes | CRC32: 0x{expected_crc:08X} | Backup: {os.path.basename(bak_path)}")

    return True

def main():
    parser = argparse.ArgumentParser(description="Repair GTA IV save files for macIV (Apple Silicon macOS).")
    parser.add_argument("paths", nargs="*", help="Path(s) to save files (SGTA4xx) or directory containing saves.")
    parser.add_argument("--import-to", dest="import_dir", help="Import & repair specified save files into destination directory.")
    args = parser.parse_args()

    target_dir = DEFAULT_SAVE_DIR
    files_to_check = []

    if args.paths:
        for p in args.paths:
            p_exp = os.path.expanduser(p)
            if os.path.isdir(p_exp):
                files_to_check.extend(sorted(glob.glob(os.path.join(p_exp, "SGTA4*"))))
            elif os.path.isfile(p_exp):
                files_to_check.append(p_exp)
    else:
        if os.path.isdir(target_dir):
            files_to_check.extend(sorted(glob.glob(os.path.join(target_dir, "SGTA4*"))))
        else:
            print(f"[-] Default save directory not found:\n    {target_dir}")
            print("    Please specify the path to your save file or save folder.")
            sys.exit(1)

    # Filter out backup files
    files_to_check = [f for f in files_to_check if not f.endswith(".bak")]

    if not files_to_check:
        print(f"[-] No save files found in {target_dir}")
        sys.exit(0)

    print(f"==> Inspecting & repairing {len(files_to_check)} save game(s)...")
    repaired_count = 0
    for f in files_to_check:
        if args.import_dir:
            dest_dir = os.path.expanduser(args.import_dir)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, os.path.basename(f))
            shutil.copy2(f, dest_path)
            if repair_save_file(dest_path):
                repaired_count += 1
        else:
            if repair_save_file(f):
                repaired_count += 1

    print(f"\n✔ Done! All {repaired_count} save file(s) are ready to load.")

if __name__ == "__main__":
    main()
