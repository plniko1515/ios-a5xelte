/* SPDX-License-Identifier: GPL-2.0-only
 * A51 (SM-A515F, Exynos 9611) stage-0 probe: print the S-Boot handoff on the
 * firmware framebuffer, then return so probe.S can request TWRP.
 */
#include <stdint.h>
#include "../fdt.h"
#include "fbtext.h"

#define RECOVERY_DELAY_S 60U

static uint64_t counter(void)
{
    uint64_t value;
    __asm__ volatile("isb; mrs %0, cntpct_el0" : "=r" (value));
    return value;
}

void a51_probe_main(uintptr_t fdt, uint64_t el, uint64_t sctlr, uint64_t image)
{
    uint64_t midr, mpidr, mmfr0, pfr0, isar0, freq, start = 0, end = 0;
    uint32_t trig_before = a51_fb_enable();

    __asm__ volatile("mrs %0, midr_el1" : "=r" (midr));
    __asm__ volatile("mrs %0, mpidr_el1" : "=r" (mpidr));
    __asm__ volatile("mrs %0, id_aa64mmfr0_el1" : "=r" (mmfr0));
    __asm__ volatile("mrs %0, id_aa64pfr0_el1" : "=r" (pfr0));
    __asm__ volatile("mrs %0, id_aa64isar0_el1" : "=r" (isar0));
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r" (freq));

    unsigned row = 0;
    a51_fb_text(row++, "A51 XNU PROBE 1");
    a51_fb_hex(row++, "EL", el >> 2);
    a51_fb_hex(row++, "SCTLR", sctlr);
    a51_fb_hex(row++, "FDT", fdt);
    a51_fb_hex(row++, "IMAGE", image);
    a51_fb_hex(row++, "MIDR", midr);
    a51_fb_hex(row++, "MPIDR", mpidr);
    a51_fb_hex(row++, "MMFR0", mmfr0);
    a51_fb_hex(row++, "PFR0", pfr0);
    a51_fb_hex(row++, "ISAR0", isar0);
    a51_fb_hex(row++, "CNTFRQ", freq);
    a51_fb_hex(row++, "TRIG", trig_before);
    if (fdt && !(fdt & 7) && fdt_chosen_u64(fdt, "linux,initrd-start", &start) &&
        fdt_chosen_u64(fdt, "linux,initrd-end", &end)) {
        a51_fb_hex(row++, "INITRD", start);
        a51_fb_hex(row++, "INITRD END", end);
    } else {
        a51_fb_text(row++, "INITRD ?");
    }
    /* MMFR0[23:20] TGran16: 0 means no 16 KiB pages (needs the 4 KiB XNU). */
    a51_fb_text(row++, ((mmfr0 >> 20) & 15U) ? "16K PAGES: YES" : "16K PAGES: NO");

    if (!freq)
        freq = 26000000U;   /* a51 armv8-timer clock-frequency */
    uint64_t t0 = counter();
    unsigned shown = ~0U;
    for (;;) {
        uint64_t elapsed = (counter() - t0) / freq;
        if (elapsed >= RECOVERY_DELAY_S)
            return;
        unsigned left = RECOVERY_DELAY_S - (unsigned)elapsed;
        if (left != shown) {
            char line[] = "TWRP EN 00 S";
            line[8] = (char)('0' + left / 10);
            line[9] = (char)('0' + left % 10);
            a51_fb_text(row + 1, line);
            shown = left;
        }
    }
}
