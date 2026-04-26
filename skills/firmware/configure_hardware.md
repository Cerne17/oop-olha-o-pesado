# Skill: Configure hardware pins, Bluetooth names, and camera settings

## Objective
Change hardware configuration constants in the firmware: motor pin assignments,
Bluetooth device names, target frame rate, and camera image quality.

All changes require a rebuild and reflash to take effect.

---

## Robot ESP32 -- motor pins

File: `robot/src/main.cpp` lines 11-14.

```cpp
static constexpr WheelPins LEFT_WHEEL  = { .pwm = 14, .dir = 12 };
static constexpr WheelPins RIGHT_WHEEL = { .pwm = 15, .dir =  2 };
```

| Field | Description |
|-------|-------------|
| `pwm` | PWM output to H-bridge EN/STBY -- controls motor speed via duty cycle |
| `dir` | Logic output to H-bridge IN pins -- controls rotation direction |

**Common reason to change:** left and right wheels are swapped (robot turns the
wrong way). Swap `LEFT_WHEEL` and `RIGHT_WHEEL` assignments:

```cpp
// Before:
static constexpr WheelPins LEFT_WHEEL  = { .pwm = 14, .dir = 12 };
static constexpr WheelPins RIGHT_WHEEL = { .pwm = 15, .dir =  2 };

// After (swapped):
static constexpr WheelPins LEFT_WHEEL  = { .pwm = 15, .dir =  2 };
static constexpr WheelPins RIGHT_WHEEL = { .pwm = 14, .dir = 12 };
```

After editing:
```bash
cd robot
pio run --target upload
```

---

## Robot ESP32 -- Bluetooth device name

File: `robot/src/main.cpp`.

```cpp
static constexpr char BT_NAME[] = "RobotESP32";
```

Change the string to any name without spaces (spaces can cause pairing issues
on some hosts). The computer module must be updated to match:

File: `computer/main.py`, `PHASE_CONFIGS[2]` and `PHASE_CONFIGS[3]`:
```python
robot_port = "/dev/cu.MyNewName-SerialPort",   # macOS
```

After renaming, remove the old Bluetooth pairing from the host OS and re-pair
under the new name.

---

## ESP32-CAM -- Bluetooth device name

File: `cam/src/main.cpp`.

```cpp
static constexpr char BT_NAME[] = "RobotCAM";
```

Same procedure as robot: rename, update `computer/main.py` `PHASE_CONFIGS[3]`
`cam_port`, remove old pairing, re-pair.

---

## ESP32-CAM -- target frame rate

File: `cam/src/main.cpp`.

```cpp
CamComm cam(6.0f, "RobotCAM");
```

The first argument is `TARGET_FPS`. Reduce it if frames are being dropped:
```cpp
CamComm cam(3.0f, "RobotCAM");   // 3 fps -- lower BT load
```

The practical maximum over BT Classic SPP at QVGA JPEG quality 15 is around
6-8 fps. Increasing beyond that causes frame drops.

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

Higher resolution increases JPEG size and may saturate the BT link at 6 fps.
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
4. For BT name changes: re-pair and confirm the new name appears.
5. For CAM changes: start Phase 3 and observe frame rate in the computer logs.
