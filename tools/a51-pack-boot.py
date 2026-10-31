#!/usr/bin/env python3
"""Inspect or repack a Samsung A51 (SM-A515F) BOOT image (Android v2, dt-table).

Host-side only: never opens a block device and never flashes the phone.
Keeps the stock Samsung dt-table (magic d7b7ab1e) and the stock ramdisk
unless --ramdisk is given. Optionally appends a SWEETXNU payload to IMAGE.

  info  STOCK
  pack  STOCK IMAGE OUT [--append P] [--ramdisk R] [--partition-size N]
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

ARM64_MAGIC = b"ARMd"


def parse(boot):
    if boot[:8] != b"ANDROID!":
        raise SystemExit("not an Android BOOT image")
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size,
     second_addr, tags_addr, page, ver, osv) = struct.unpack_from("<10I", boot, 8)
    if page not in (2048, 4096):
        raise SystemExit(f"unexpected page size {page}")
    if ver < 2:
        raise SystemExit(f"expected header v2, got v{ver}")
    align = lambda size: (size + page - 1) // page * page
    kernel_off = page
    ramdisk_off = kernel_off + align(kernel_size)
    second_off = ramdisk_off + align(ramdisk_size)
    recovery_dtbo_size, recovery_dtbo_addr = struct.unpack_from("<IQ", boot, 1632)
    header_size = struct.unpack_from("<I", boot, 1644)[0]
    dt_size, dt_addr = struct.unpack_from("<IQ", boot, 1648)
    recovery_dtbo_off = second_off + align(second_size)
    dt_off = recovery_dtbo_off + align(recovery_dtbo_size)
    if dt_off + dt_size > len(boot):
        raise SystemExit("image is truncated")
    return {
        "page": page, "align": align, "version": ver,
        "kernel_addr": kernel_addr, "ramdisk_addr": ramdisk_addr,
        "second_addr": second_addr, "tags_addr": tags_addr,
        "unused": osv, "header_size": header_size,
        "kernel": boot[kernel_off:kernel_off + kernel_size],
        "ramdisk": boot[ramdisk_off:ramdisk_off + ramdisk_size],
        "second": boot[second_off:second_off + second_size],
        "recovery_dtbo": boot[recovery_dtbo_off:recovery_dtbo_off + recovery_dtbo_size],
        "dt": boot[dt_off:dt_off + dt_size],
        "tail": boot[dt_off + align(dt_size):],
        "dt_size": dt_size,
    }


def image_header(kernel):
    if len(kernel) < 64 or kernel[56:60] != ARM64_MAGIC:
        return None
    text_offset, image_size, flags = struct.unpack_from("<3Q", kernel, 8)
    return text_offset, image_size, flags


def cmd_info(args):
    boot = args.stock.read_bytes()
    b = parse(boot)
    print(f"bytes={len(boot)} sha256={hashlib.sha256(boot).hexdigest()}")
    print(f"page={b['page']} version={b['version']} header_size={b['header_size']}")
    print(f"kernel={len(b['kernel'])} at {b['kernel_addr']:#x}")
    print(f"ramdisk={len(b['ramdisk'])} at {b['ramdisk_addr']:#x}")
    print(f"second={len(b['second'])} at {b['second_addr']:#x} tags={b['tags_addr']:#x}")
    print(f"dt={len(b['dt'])} tail={b['tail'][:16].hex()}")
    hdr = image_header(b["kernel"])
    if hdr:
        print("arm64 Image: text_offset={:#x} image_size={:#x} flags={:#x}".format(*hdr))
    else:
        print(f"kernel is not a raw arm64 Image (starts {b['kernel'][:4].hex()})")
    print(f"dt magic: {b['dt'][:4].hex()}")


def cmd_pack(args):
    if args.output.exists():
        raise SystemExit("output exists; choose a new private path")
    stock = args.stock.read_bytes()
    b = parse(stock)
    image = bytearray(args.image.read_bytes())
    if image[56:60] != ARM64_MAGIC:
        raise SystemExit("IMAGE lacks the arm64 Image header")
    if args.append:
        payload = args.append.read_bytes()
        if payload[:8] != b"SWEETXNU":
            raise SystemExit("--append payload is not a SWEETXNU container")
        image.extend(b"\0" * (-len(image) % 4096))
        image.extend(payload)
    stock_hdr = image_header(b["kernel"])
    if stock_hdr and stock_hdr[0]:
        text_offset, _, flags = stock_hdr
        image_size = (len(image) + 0x10000 + 0xfff) & ~0xfff
        struct.pack_into("<3Q", image, 8, text_offset, image_size, flags)
    else:
        # stock kernel is not a raw arm64 Image (e.g. UEFI); keep the new
        # image's own text_offset/flags and just fill in image_size.
        image_size = (len(image) + 0x10000 + 0xfff) & ~0xfff
        cur_to, cur_sz, cur_fl = struct.unpack_from("<3Q", image, 8)
        if not cur_to:
            cur_to = 0x80000
        struct.pack_into("<3Q", image, 8, cur_to, image_size, cur_fl)
        print("note: stock kernel header not an arm64 Image; kept IMAGE header", file=sys.stderr)
    ramdisk = args.ramdisk.read_bytes() if args.ramdisk else b["ramdisk"]
    page, align = b["page"], b["align"]
    header = bytearray(stock[:page])
    # Android v2 header fields
    struct.pack_into("<I", header, 8, len(image))          # kernel_size
    struct.pack_into("<I", header, 16, len(ramdisk))      # ramdisk_size
    # recovery_dtbo (offset 1632) and dt (1648) sizes unchanged
    # hash (offset 576..596) over kernel, ramdisk, second, recovery_dtbo, dt
    digest = hashlib.sha1()
    for part in (bytes(image), ramdisk, b["second"], b["recovery_dtbo"], b["dt"]):
        digest.update(part)
        digest.update(struct.pack("<I", len(part)))
    header[576:596] = digest.digest()
    header[596:608] = b"\0" * 12
    out = bytearray(header)
    for part in (bytes(image), ramdisk, b["second"], b["recovery_dtbo"], b["dt"]):
        if part:
            out.extend(part)
            out.extend(b"\0" * (align(len(part)) - len(part)))
    out.extend(b"SEANDROIDENFORCE")
    if args.partition_size and len(out) > args.partition_size:
        raise SystemExit(f"candidate {len(out)} exceeds BOOT partition {args.partition_size}")
    args.output.write_bytes(out)
    print("candidate only; no device write")
    print(f"stock_sha256={hashlib.sha256(stock).hexdigest()}")
    print(f"candidate_sha256={hashlib.sha256(out).hexdigest()}")
    print(f"bytes={len(out)} kernel_addr={b['kernel_addr']:#x} ramdisk_addr={b['ramdisk_addr']:#x}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    info = sub.add_parser("info")
    info.add_argument("stock", type=Path)
    pack = sub.add_parser("pack")
    pack.add_argument("stock", type=Path)
    pack.add_argument("image", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--ramdisk", type=Path)
    pack.add_argument("--append", type=Path)
    pack.add_argument("--partition-size", type=int)
    args = ap.parse_args()
    {"info": cmd_info, "pack": cmd_pack}[args.cmd](args)


if __name__ == "__main__":
    main()
