/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>

/* A51 (SM-A515F, Exynos 9611) S-Boot splash framebuffer, kept continuously
 * open (bootargs s3cfb.bootloaderfb=0xca000000; the running edk2 build uses
 * the same address, 1080x2400 ARGB8888, 32-bit pixels). */
#define A51_FB_BASE   0xca000000UL
#define A51_FB_WIDTH  1080U
#define A51_FB_HEIGHT 2400U

/* Kick the panel: exynos9-DECON at 0x148b0000. Register writes taken from
 * the working edk2-exynos A51 firmware (PlatformUtils.c). */
uint32_t a51_fb_enable(void);
void a51_fb_text(unsigned row, const char *s);
void a51_fb_hex(unsigned row, const char *label, uint64_t value);
