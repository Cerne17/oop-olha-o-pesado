# Skill: Debug ESP32-CAM init and streaming failures

## Objective
Diagnose and fix camera initialisation failures and frame streaming issues on
the AI Thinker ESP32-CAM.

## Symptoms this skill covers

| Symptom | Likely cause |
|---------|--------------|
| `[CAM] FATAL: camera init failed -- halting` | Ribbon cable loose or reversed |
| Serial monitor shows `=== Ready ===` but no frames arrive | WiFi not connected / computer IP:port mismatch |
| Frames arrive but image is corrupted or all black | Camera resolution or JPEG quality misconfigured |
| Frame rate is lower than expected | JPEG size too large for UDP throughput |

---

## Step 1 -- Ribbon cable

The OV2640 camera module attaches to the ESP32-CAM via a flat ribbon cable.

1. Power off the board.
2. Gently lift the ribbon cable lock tab on the camera connector.
3. Remove the ribbon cable.
4. Reinsert the ribbon cable fully -- all contacts must be inside the connector,
   gold contacts facing the board (downward on the AI Thinker layout).
5. Press the lock tab back down firmly.
6. Power on and check the serial monitor:
   ```
   === CAM ESP32 booting ===
   [CAM] WiFi IP: 192.168.1.43
   [CAM] UDP listening on port 5006
   === Ready ===
   ```
   If `FATAL: camera init failed` still appears, try reseating once more or
   swap the camera module.

---

## Step 2 -- Confirm firmware is running (not bootloader)

After flashing:
- Remove the GPIO0--GND jumper.
- Press **RST** or power-cycle.

If the serial monitor shows no output or only garbage, see
[debug_serial.md](debug_serial.md).

---

## Step 3 -- Verify frames are being sent (verbose check)

With the board booted and WiFi connected, start the computer in Phase 3:
```bash
python -m computer.main --phase 3
```

Expected log lines from `CamReceiver`:
```
[cam-rx] connected
[cam-rx] IMAGE_CHUNK seq=1 frame_id=0 chunk 0/0
```

If no `IMAGE_CHUNK` lines appear:
- Confirm `PHASE_CONFIGS[3].cam_port` in `computer/main.py` matches the IP
  printed by the CAM on boot. See [debug_cam_comm.md](debug_cam_comm.md).
- Check that `CamReceiver` thread is alive (no `HEARTBEAT timeout` log).

---

## Step 4 -- Adjust resolution and JPEG quality

Files: `cam/src/communication/CamComm.cpp` lines 328-329.

```cpp
config.frame_size   = FRAMESIZE_QVGA;   // 320x240
config.jpeg_quality = 15;               // 0=best quality (largest), 63=lowest
```

| Setting | Effect |
|---------|--------|
| Increase `jpeg_quality` (e.g. 20-30) | Smaller JPEG, more frames fit in UDP bandwidth |
| Decrease `jpeg_quality` (e.g. 5-10) | Larger JPEG, higher image quality |
| `FRAMESIZE_VGA` | 640x480 -- much larger file, may saturate the UDP link |

After editing, rebuild and reflash:
```bash
cd cam
pio run --target upload
```

---

## Step 5 -- Adjust target frame rate

File: `cam/src/main.cpp`.

```cpp
static constexpr float TARGET_FPS = 6.0f;
```

Reduce `TARGET_FPS` if frames are being dropped:
```cpp
static constexpr float TARGET_FPS = 3.0f;
```

After editing, rebuild and reflash.

---

## Reference: camera pin map (AI Thinker -- hardcoded in firmware)

These do not need to be changed for the standard AI Thinker board:

| Signal | GPIO |
|--------|------|
| PWDN   | 32   |
| XCLK   | 0    |
| SIOD   | 26   |
| SIOC   | 27   |
| D7-D2  | 35, 34, 39, 36, 21, 19, 18, 5 |
| VSYNC  | 25   |
| HREF   | 23   |
| PCLK   | 22   |

Source: `cam/src/communication/CamComm.cpp` lines 9-26.
