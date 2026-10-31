#!/usr/bin/env python3
"""Build the A51 (SM-A515F, Exynos 9611) ADT for the A51 XNU config.

Adapted from mkadt_herolte.py. Hardware addresses come from the stock A51 DTB
(/tmp/opencode/a51_inner.dtb and the runtime FDT pulled from TWRP):
  GIC-400 dist 0x12300000, CPU iface 0x12301000; timer 26 MHz, virt INTID 27;
  UFS HC 0x13520000; framebuffer 0xCA000000 (1080x2400);
  lower DRAM bank 0x80000000..0xBAB00000, upper bank 0x880000000..0x900000000.
"""
import argparse
import os
from pathlib import Path

import adt
import mkadt

DRAM_BASE = 0x90000000
DRAM_SIZE = 0x20000000
BANK2_BASE, BANK2_SIZE = 0x880000000, 0x80000000
SOC_BASE = 0x10000000
FB_BASE, FB_WIDTH, FB_HEIGHT = 0xca000000, 1080, 2400


def set_prop(node, name, value):
    for i, (key, flags, _) in enumerate(node.props):
        if key == name:
            node.props[i] = (key, flags, value)
            return
    node.props.append((name, 0, value))


def child(node, name):
    for candidate in node.children:
        if candidate.prop('name') == mkadt.cstr(name):
            return candidate
    raise ValueError(f'missing donor ADT node {name}')


def build(canvas=(FB_WIDTH, FB_HEIGHT), dram=(DRAM_BASE, DRAM_SIZE), scale=3):
    root = mkadt.build(seed=os.urandom(64), qemu=True)
    if scale == 2:
        set_prop(child(root, 'chosen'), 'display-scale', mkadt.u32(2))
        product = child(root, 'product')
        set_prop(product, 'artwork-device-subtype', mkadt.u32(1792))
        set_prop(product, 'artwork-scale-factor', mkadt.u32(2))
        canvas = (828, 1792)
    # iPhone X userland (D22AP / iPhone10,3), reused from the S7 port.
    set_prop(root, 'compatible', mkadt.cstr('D22AP') + mkadt.cstr('iPhone10,3') +
             mkadt.cstr('samsung,a5xelte') + mkadt.cstr('samsung,a51') +
             mkadt.cstr('samsung,exynos9611') + mkadt.cstr('AppleARM'))
    chosen = child(root, 'chosen')
    set_prop(chosen, 'dram-base', mkadt.u64(dram[0]))
    set_prop(chosen, 'dram-size', mkadt.u64(dram[1]))
    set_prop(chosen, 'firmware-version', mkadt.cstr('a51-entry'))
    set_prop(chosen, 'system-firmware-version', mkadt.cstr('a51-entry'))
    for name, last in (('wifi0', 1), ('bluetooth0', 2), ('ethernet0', 3)):
        set_prop(chosen, f'mac-address-{name}', bytes((0x02, 0x41, 0x35, 0x31, 0x00, last)))
    cpus = child(root, 'cpus')
    cpu0 = child(cpus, 'cpu0')
    # A51 boots on the big cluster (Cortex-A73, MPIDR 0x100..); advertise as
    # cortex-a53 so SweetCPU's IONameMatch ('arm,cortex-a53') binds it.
    set_prop(cpu0, 'compatible', mkadt.cstr('arm,cortex-a53') + mkadt.cstr('ARM,v8'))
    set_prop(cpu0, 'reg', mkadt.u32(0x100))
    set_prop(cpu0, 'timebase-frequency', mkadt.u32(26000000))
    for logical in range(1, 8):
        # 4 big (A73, MPIDR 0x100..) + 4 little (A53, MPIDR 0x0..)
        big = logical < 4
        core = logical if big else logical - 4
        mpidr = 0x100 | core if big else core
        cpus.children.append(mkadt.node(f'cpu{logical}', [
            ('device_type', mkadt.cstr('cpu')),
            ('compatible', mkadt.cstr('arm,cortex-a53') + mkadt.cstr('ARM,v8')),
            ('reg', mkadt.u32(mpidr)),
            ('cpu-id', mkadt.u32(logical)),
            ('cluster-id', mkadt.u32(0)),
            ('cluster-type', mkadt.u32(0)),
            ('die-cluster-id', mkadt.u32(0)),
            ('cluster-core-id', mkadt.u32(logical)),
            ('l2-cache-id', mkadt.u32(1 if not big else 0)),
            ('l3-cache-id', mkadt.u32(0)),
            ('state', mkadt.cstr('stopped')),
            ('timebase-frequency', mkadt.u32(26000000)),
            ('clock-frequency', mkadt.u32(2300000000 if big else 1700000000)),
            ('bus-frequency', mkadt.u32(100000000)),
            ('memory-frequency', mkadt.u32(1800000000)),
            ('peripheral-frequency', mkadt.u32(26000000)),
            ('fixed-frequency', mkadt.u32(26000000)),
        ]))
    arm_io = child(root, 'arm-io')
    set_prop(arm_io, 'device_type', mkadt.cstr('a51-io'))
    set_prop(arm_io, 'compatible', mkadt.cstr('samsung,exynos9611-io') +
             mkadt.cstr('arm-io'))
    set_prop(arm_io, 'ranges', mkadt.u64(0, SOC_BASE, 0xf0000000))
    arm_io.children = [n for n in arm_io.children if n.prop('name') == mkadt.cstr('wdt')]
    # GIC-400: distributor 0x12300000, CPU interface 0x12301000.
    arm_io.children.append(mkadt.node('gic', [
        ('compatible', mkadt.cstr('arm,cortex-a15-gic')),
        ('interrupt-controller', mkadt.cstr('master')),
        ('virtual-timer-intid', mkadt.u32(27)),
        ('reg', mkadt.u64(0x12300000 - SOC_BASE, 0x1000, 0x12301000 - SOC_BASE, 0x1000)),
    ]))
    arm_io.children.append(mkadt.node('disp0', [
        ('device_type', mkadt.cstr('display-subsystem')),
        ('compatible', mkadt.cstr('samsung,a5xelte-display') +
         mkadt.cstr('samsung,a51-display')),
        ('canvas-width', mkadt.u32(canvas[0])),
        ('canvas-height', mkadt.u32(canvas[1])),
    ]))
    root.children = [n for n in root.children if n.prop('name') not in
                     (mkadt.cstr('sweet-fbcon'), mkadt.cstr('sweet-ufs'))]
    # Exynos 9611 UFSHCI at 0x13520000; node name kept as 'herolte-ufs' so the
    # (unmodified) herolte_ufs driver binds it.
    root.children.append(mkadt.node('herolte-ufs', [
        ('reg', mkadt.u64(0x13520000, 0x3000)),
    ]))
    root.children.append(mkadt.node('a5xelte-fbcon', [
        ('reg', mkadt.u64(FB_BASE, FB_WIDTH * FB_HEIGHT * 4)),
        ('width', mkadt.u32(FB_WIDTH)),
        ('height', mkadt.u32(FB_HEIGHT)),
        ('stride', mkadt.u32(FB_WIDTH * 4)),
    ]))
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--canvas', default=f'{FB_WIDTH}x{FB_HEIGHT}')
    parser.add_argument('--bank2', action='store_true')
    parser.add_argument('--bank2-mb', type=int, default=BANK2_SIZE >> 20)
    parser.add_argument('--scale2', action='store_true')
    args = parser.parse_args()
    canvas = tuple(int(v) for v in args.canvas.lower().split('x'))
    dram = (BANK2_BASE, min(args.bank2_mb << 20, BANK2_SIZE)) if args.bank2 else (DRAM_BASE, DRAM_SIZE)
    blob = adt.serialize(build(canvas, dram, 2 if args.scale2 else 3))
    args.output.write_bytes(blob)
    print(f'{args.output}: {len(blob)} bytes')
