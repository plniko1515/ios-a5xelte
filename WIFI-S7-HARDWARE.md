# S7 (Exynos 8890) WiFi hardware reference

Extracted from the stock S7 (SM-G930F, XEO) boot.img DTB (G930FXXU8EVG3).

## WiFi chip
- Broadcom BCM4359 (FullMAC, bcmdhd protocol)
- Connected via PCIe0 (pcie0@157A0000), status = okay
- pcie1 (157B0000) is disabled

## PCIe0 controller (Exynos 8890)
- compatible: "samsung,exynos8890-pcie"
- reg (6 windows):
  - elbi    = 0x15660000, 0x1000  (ELBI / application registers)
  - phy     = 0x15630000, 0x1000  (PHY registers)
  - sysreg  = 0x15601044, 0x10    (system register / PMU)
  - dbi     = 0x157a0000, 0x1000  (DBI / configuration space)
  - pcs     = 0x156f0000, 0x128   (PCS)
  - config  = 0x1c000000, 0x10000 (PCIe config space)
- interrupts = 0xcc (204)
- MSI base = 0xc8
- 1 lane, ch-num = 0
- clocks: gate_pciewifi0, wifi0_dig_refclk, pcie_wifi0_tx0, pcie_wifi0_rx0
- pinctrl: clkreq_output

## Device tree nodes
- `wlan` (compatible "samsung,brcm-wlan"): gpios 0x94 0x03 0x01 0xe2 0x07 0x01
- `bluetooth` (compatible "broadcom,bcm4359"): gpios 0x94 0x07 0x00 0x5f 0x03 0x00 0x20 0x03 0x0f

## Firmware
- BCM4359 firmware: typically `bcmdhd_sta.bin` / `nvram.txt` from /vendor/firmware/
- Samsung uses bcmdhd (FullMAC) driver in the stock kernel

## Driver implementation stages
1. **PCIe link training** ✅ (herolte_wifi.c) — soft reset, LTSSM enable, linkup poll (from Linux exynos8890-pcie driver). Reads vendor/device ID and BAR0 from config space.
2. **PCIe device enumeration** — find BCM4359 (vendor 0x14e4, device 0x43ec), enable bus mastering, allocate BARs. TODO.
3. **Firmware loading** — load bcmdhd firmware + NVRAM into device RAM. TODO.
4. **bcmdhd FullMAC protocol** — control messages (ioctls) to the firmware, event handling. TODO.
5. **802.11 integration** — implement IO80211Controller/IO80211Interface subclasses, WPA supplicant glue. TODO.
6. **Network interface** — ifnet registration, packet TX/RX. TODO.

## GPU acceleration (Mali-T880 MP12)
Current state (herolte):
- Mali-T880 working for frame presentation (Panfrost, 3.3 ms/frame scaling).
- HeroGPU IOKit service (patch 0239) exposes GEM/submit to userspace.
- Mesa 25 Panfrost for iOS (workflow `mesa-ios`) — OpenGL ES from iOS apps (in progress).
- Full Metal/CoreAnimation acceleration requires Metal shim (Chlorophyll) on top of Mesa — ongoing upstream work.
- "Better GPU acceleration" = completing the Mesa/Panfrost integration so iOS rendering uses the GPU instead of CPU.

## GPU acceleration (Mali-T880, already working for presentation)
- Current: Mali-T880 MP12 used for scaling iOS frames to panel (3.3 ms/frame, Panfrost).
- HeroGPU IOKit service (patch 0239) exposes GEM/submit to userspace.
- Next: Mesa 25 Panfrost for iOS (workflow `mesa-ios`) → OpenGL ES from iOS apps.
- Full Metal/CoreAnimation acceleration requires Metal shim (Chlorophyll) on top of Mesa — ongoing upstream work.
