# Skill: Configure hardware pins, UDP port, and camera settings

## Objective
Change hardware configuration constants in the firmware: motor pin assignments,
UDP listen port, target frame rate, and camera image quality.

All changes require a rebuild and reflash to take effect.

---

## Robot ESP32 -- motor pins

File: `robot/src/main.cpp` lines 11-14.

```cpp
static constexpr WheelPins LEFT_WHEEL  = { .en = 14, .right = 12, .left = 13 };
static constexpr WheelPins RIGHT_WHEEL = { .en = 15, .right =  2, .left =  4 };
```

| Field | Description |
|-------|-------------|
| `en` | PWM output to H-bridge EN/STBY — controls motor speed via duty cycle |
| `right` | HIGH = motor spins clockwise (drive right) |
| `left` | HIGH = motor spins counter-clockwise (drive left); always complement of `right` |

**Common reason to change:** left and right wheels are swapped (robot turns the
wrong way). Swap `LEFT_WHEEL` and `RIGHT_WHEEL` assignments:

```cpp
// After (swapped):
static constexpr WheelPins LEFT_WHEEL  = { .en = 15, .right =  2, .left =  4 };
static constexpr WheelPins RIGHT_WHEEL = { .en = 14, .right = 12, .left = 13 };
```

After editing:
```bash
cd robot
pio run --target upload
```

---

## Robot ESP32 -- UDP listen port

File: `robot/src/main.cpp`.

```cpp
static constexpr uint16_t UDP_PORT = 5005;
```

Update `computer/main.py` `PHASE_CONFIGS[2]` and `PHASE_CONFIGS[3]` to match:
```python
robot_port = "192.168.1.42:5005",
```

---

## ESP32-CAM -- UDP listen port

File: `cam/src/main.cpp`.

```cpp
static constexpr uint16_t UDP_PORT = 5006;
```

Update `computer/main.py` `PHASE_CONFIGS[3]` `cam_port` to match:
```python
cam_port = "192.168.1.43:5006",
```

---

## ESP32-CAM -- target frame rate

File: `cam/src/main.cpp`.

```cpp
static constexpr float TARGET_FPS = 6.0f;
```

Reduce `TARGET_FPS` if frames are being dropped due to UDP bandwidth:
```cpp
static constexpr float TARGET_FPS = 3.0f;   // 3 fps -- lower UDP load
```

---

## ESP32-CAM -- image resolution and JPEG quality

File: `cam/src/communication/CamComm.cpp` lines 328-329.

```cpp
config.frame_size   = FRAMESIZE_QVGA;   // 320x240
config.jpeg_quality = 15;               // 0=highest quality/largest, 63=lowest
```

### Resolution options

| Constant | Resolution | Typical JPEG size |
|----------|------------|-------------------|
| `FRAMESIZE_QQVGA` | 160x120 | ~5 KB |
| `FRAMESIZE_QVGA`  | 320x240 | ~15 KB (default) |
| `FRAMESIZE_VGA`   | 640x480 | ~50 KB |

Higher resolution increases JPEG size and may saturate the UDP link at 6 fps.
If you increase resolution, also reduce `TARGET_FPS` or increase `jpeg_quality`.

### Quality trade-off

| `jpeg_quality` | File size | Visual quality |
|----------------|-----------|----------------|
| 5-10 | Large | High |
| 15 (default) | Medium | Acceptable |
| 25-40 | Small | Visibly compressed |

After editing `CamComm.cpp`:
```bash
cd cam
pio run --target upload
```

---

## WheelController rate limiter (robot)

File: `robot/src/control/WheelController.cpp` (or `.h`).

```cpp
static constexpr float MAX_DELTA_PER_TICK = 0.02f;   // at CONTROL_HZ=50
```

At 50 Hz, this gives a ramp time of `1.0 / (50 * 0.02) = 1 second` from 0 to
full speed. If motion feels too sluggish, increase this constant:

```cpp
static constexpr float MAX_DELTA_PER_TICK = 0.05f;   // ~0.4 s ramp
```

If motion is jerky (too abrupt), decrease it:
```cpp
static constexpr float MAX_DELTA_PER_TICK = 0.01f;   // ~2 s ramp
```

After editing, rebuild and reflash:
```bash
cd robot
pio run --target upload
```

---

## Verification

After any configuration change:

1. Flash the board (see above).
2. Open the serial monitor and confirm `=== Ready ===`.
3. For pin changes: send a CONTROL_REF and observe physical wheel behaviour.
4. For port changes: update `PHASE_CONFIGS` in `computer/main.py` to match.
5. For CAM changes: start Phase 3 and observe frame rate in the computer logs.
