/*
 * HEROLTE (Galaxy S7, Exynos 8890) WiFi: Broadcom BCM4359 on PCIe0.
 *
 * Full driver stages (see WIFI-S7-HARDWARE.md):
 *   1. PCIe link training  <- this file implements
 *   2. BAR allocation + bus mastering
 *   3. BCM4359 firmware loading (bcmdhd FullMAC)
 *   4. 802.11 / IO80211Controller integration
 *
 * Hardware (stock S7 DTB, exynos8890-pcie @ 0x15660000):
 *   elbi    = 0x15660000  (application registers)
 *   phy     = 0x15630000  (PHY registers)
 *   sysreg  = 0x15601044  (system register)
 *   dbi     = 0x157a0000  (DBI / config space base)
 *   pcs     = 0x156f0000  (PCS)
 *   config  = 0x1c000000  (PCIe config space)
 *   IRQ = 0xcc, MSI base = 0xc8, 1 lane.
 *
 * Register offsets derived from the Samsung Linux driver (pci-exynos.c
 * + pci-exynos8890.c + pci-exynos8890_cal.c).
 *
 * Enable with boot arg wifiprobe=1. Prints link status and device ID.
 */
#if defined(ARM64_BOARD_CONFIG_HEROLTE)
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include <machine/machine_routines.h>
#include <pexpert/pexpert.h>

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);

/* Register offsets (from pci-exynos8890.c) */
#define PCIE_SOFT_CORE_RESET        0x000
#define PCIE_ELBI_LTSSM_ENABLE      0x004  /* LTSSM enable (write 0x1) */
#define PCIE_APP_LTSSM_ENABLE       0x004
#define PCIE_ELBI_RDLH_LINKUP       0x008  /* linkup status: bits [4:0] */
#define PCIE_APP_REQ_EXIT_L1_MODE   0x010
#define PCIE_QCH_SEL                0x014
#define PCIE_L1_BUG_FIX_ENABLE      0x018
#define PCIE_LINKDOWN_RST_CTRL_SEL  0x01c
#define PCIE_PM_DSTATE              0x020
#define PCIE_APP_REQ_EXIT_L1_MODE_BIT 0
#define APP_REQ_EXIT_L1_MODE        (1 << 0)
#define L1_REQ_NAK_CONTROL_MASTER   (1 << 1)
#define PCIE_LINKDOWN_RST_MANUAL    0x1
#define CLOCK_NOT_GATING            0x1
#define CLOCK_GATING_MASK           0x3
#define PCIE_ELBI_LTSSM_DISABLE     0x0
#define PCIE_ELBI_LTSSM_ENABLE_VAL  0x1

#define PCIE0_ELBI_PA   0x15660000u
#define PCIE0_PHY_PA    0x15630000u
#define PCIE0_SYSREG_PA 0x15601044u
#define PCIE0_DBI_PA    0x157a0000u
#define PCIE0_PCS_PA    0x156f0000u
#define PCIE0_CFG_PA    0x1c000000u
#define PCIE0_IRQ       0xcc
#define MAX_TIMEOUT     1000

static vm_offset_t pcie_elbi, pcie_dbi, pcie_cfg, pcie_pcs;

static uint32_t
pcie_rd(vm_offset_t base, uint32_t off)
{
	uint32_t v = *(volatile uint32_t *)(base + off);
	__asm__ volatile ("dmb oshld" ::: "memory");
	return v;
}

static void
pcie_wr(vm_offset_t base, uint32_t off, uint32_t v)
{
	__asm__ volatile ("dmb oshst" ::: "memory");
	*(volatile uint32_t *)(base + off) = v;
	__asm__ volatile ("dsb osh" ::: "memory");
}

static void
udelay_approx(uint32_t us)
{
	/* Busy-wait using the architected timer (26 MHz). */
	uint64_t t0, freq = 26000000;
	__asm__ volatile ("mrs %0, cntfrq_el0" : "=r" (freq));
	if (!freq) freq = 26000000;
	__asm__ volatile ("isb; mrs %0, cntpct_el0" : "=r" (t0));
	uint64_t target = t0 + (us * freq / 1000000);
	uint64_t now;
	do {
		__asm__ volatile ("isb; mrs %0, cntpct_el0" : "=r" (now));
	} while (now < target);
}

int herolte_wifi_init(void)
{
	uint32_t probe = 0;
	PE_parse_boot_argn("wifiprobe", &probe, sizeof(probe));
	if (probe != 1)
		return 0;

	pcie_elbi = ml_io_map(PCIE0_ELBI_PA, 0x1000);
	pcie_dbi  = ml_io_map(PCIE0_DBI_PA, 0x1000);
	pcie_cfg  = ml_io_map(PCIE0_CFG_PA, 0x10000);
	pcie_pcs  = ml_io_map(PCIE0_PCS_PA, 0x200);

	if (!pcie_elbi || !pcie_dbi || !pcie_cfg) {
		printf("herolte_wifi: ml_io_map failed\n");
		return ENOMEM;
	}

	printf("herolte_wifi: PCIe0 mapped (elbi=%p dbi=%p cfg=%p pcs=%p)\n",
	       (void*)pcie_elbi, (void*)pcie_dbi, (void*)pcie_cfg, (void*)pcie_pcs);

	/* Step 1: avoid checking rx elecidle when accessing DBI */
	if (pcie_pcs)
		pcie_wr(pcie_pcs, 0xEC, pcie_rd(pcie_pcs, 0xEC) | (1 << 3));

	/* Step 2: soft core reset (low then high) */
	pcie_wr(pcie_elbi, PCIE_SOFT_CORE_RESET, 0x0);
	udelay_approx(20);
	pcie_wr(pcie_elbi, PCIE_SOFT_CORE_RESET, 0x1);

	/* Step 3: APP_REQ_EXIT_L1_MODE + L1 NAK control */
	uint32_t val = pcie_rd(pcie_elbi, PCIE_APP_REQ_EXIT_L1_MODE);
	val |= APP_REQ_EXIT_L1_MODE;
	val |= L1_REQ_NAK_CONTROL_MASTER;
	pcie_wr(pcie_elbi, PCIE_APP_REQ_EXIT_L1_MODE, val);
	pcie_wr(pcie_elbi, PCIE_LINKDOWN_RST_CTRL_SEL, PCIE_LINKDOWN_RST_MANUAL);

	/* Q-Channel support: disable clock gating */
	val = pcie_rd(pcie_elbi, PCIE_QCH_SEL);
	val &= ~CLOCK_GATING_MASK;
	val |= CLOCK_NOT_GATING;
	pcie_wr(pcie_elbi, PCIE_QCH_SEL, val);

	/* Step 4: L1 bug fix enable */
	pcie_wr(pcie_elbi, PCIE_L1_BUG_FIX_ENABLE, 0x1);

	/* Step 5: assert LTSSM enable */
	pcie_wr(pcie_elbi, PCIE_APP_LTSSM_ENABLE, PCIE_ELBI_LTSSM_ENABLE_VAL);

	/* Step 6: poll linkup (LTSSM state 0x0d..0x14 = link up) */
	int count = 0;
	uint32_t linkup;
	do {
		linkup = pcie_rd(pcie_elbi, PCIE_ELBI_RDLH_LINKUP) & 0x1f;
		if (linkup >= 0x0d && linkup <= 0x14)
			break;
		count++;
		udelay_approx(10);
	} while (count < MAX_TIMEOUT);

	if (count >= MAX_TIMEOUT) {
		printf("herolte_wifi: link NOT up (LTSSM=0x%02x) after %d tries\n", linkup, count);
	} else {
		printf("herolte_wifi: link UP (LTSSM=0x%02x) after %d tries\n", linkup, count);
	}

	/* Step 7: read PCIe config space (vendor/device ID at offset 0) */
	uint32_t id = *(volatile uint32_t *)(pcie_cfg + 0x00);
	printf("herolte_wifi: config space [0x00] = 0x%08x (expect 0x43ec14e4 for BCM4359)\n", id);

	/* Read BAR0 from config space offset 0x10 */
	uint32_t bar0 = *(volatile uint32_t *)(pcie_cfg + 0x10);
	printf("herolte_wifi: BAR0 = 0x%08x\n", bar0);

	/* Restore phy_pcs rx elecidle check */
	if (pcie_pcs)
		pcie_wr(pcie_pcs, 0xEC, pcie_rd(pcie_pcs, 0xEC) & ~(1 << 3));

	/* TODO: BAR allocation, bus mastering enable, BCM4359 firmware load,
	 * bcmdhd FullMAC init, IO80211Controller registration. */

	return 0;
}

int herolte_wifi_probe(void)
{
	return herolte_wifi_init();
}
#endif /* ARM64_BOARD_CONFIG_HEROLTE */
EOF
echo "written"