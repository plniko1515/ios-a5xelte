# S7 (Exynos 8890) GPU acceleration status

## Hardware
- Mali-T880 MP12 (Midgard 4th gen), 650 MHz, 12 cores
- Already working for frame presentation (Panfrost-based, 3.3 ms/frame)

## What works (herolte patches 0225-0247)
- GPU power-up, MMU, job slots, tiler
- Hand-assembled Midgard shaders, textures, bilinear scaling
- CPU presentation path: iOS frame (828x1792 @2x) scaled to panel (1440x2560) by GPU
- HeroGPU IOKit service (patch 0239): GetParam, CreateBO/FreeBO/MapBO, Submit
- OpenGL ES from iOS via Mesa 25 Panfrost (self-test: triangle, textured quad, 159 fps at 256x256)
- Native app installation via "drop zone" in USERDATA

## What does NOT work yet
- **Metal/CoreAnimation on GPU**: iOS uses Metal for CoreAnimation rendering. The herolte port uses CPU rendering (CoreAnimation software path). Metal acceleration requires:
  1. Mesa 25 Panfrost compiled for iOS (workflow `mesa-ios`, not in this repo)
  2. Metal shim (Chlorophyll) on top of Panfrost's Gallium driver
  3. Hooking CoreAnimation's render server to use the Metal device
- This is the upstream's next milestone (etap 2/3). Not a kernel driver issue — it's a userspace (Mesa + Metal) porting effort.

## GPU-related patches already in repo
- 0225: mali-t880-probe
- 0226: mali-first-job
- 0227: mali-fragment-clear
- 0228: mali-mfbd
- 0229: mali-tiler-disabled
- 0230: mali-whole-panel
- 0231: mali-gpu-copy
- 0232: mali-first-triangle
- 0233: mali-triangle-alpha
- 0234: mali-textured-quad
- 0235: gpu-present
- 0237: xr-canvas-gpu-bars
- 0239: herogpu-user-client
- 0243: herogpu-t880-quirks
- 0245: herogl-backboardd-eagl-shim
- 0247: gpu-job-barrier

## Next steps for "better GPU acceleration"
1. Complete Mesa 25 Panfrost iOS build (workflow `mesa-ios`) — already partially done.
2. Integrate HeroGPU as DRM/KMS backend for Mesa.
3. Port Chlorophyll (Metal-on-Gallium) to use Panfrost.
4. Hook CoreAnimation render server to use Metal device.
This is a multi-month userspace effort, not a kernel change.
