# Skill: Debug CAM firmware communication

## Objective
Diagnose issues on the ESP32-CAM — camera initialisation failures, JPEG
streaming problems, heartbeat timeouts, or the computer not receiving frames.

## Key files
| File | Role |
|------|------|
| `cam/src/communication/CamComm.h` | Task declarations, RX state machine |
| `cam/src/communication/CamComm.cpp` | `_cameraTask`, `_rxTask`, `_sendChunk`, `_dispatchFrame` |
| `cam/src/types/Protocol.h` | `MsgType` enum, `ImageChunkHeader`, CRC, frame constants |
| `cam/src/main.cpp` | `TARGET_FPS`, `BT_NAME` config |

## Step-by-step

### 1. Open the serial monitor
```bash
cd cam
pio device monitor --baud 115200
```
Expected boot sequence:
```
=== CAM ESP32 booting ===
[CAM] Bluetooth started as 'RobotCAM'
=== Ready ===
```

If you see `[CAM] FATAL: camera init failed — halting`, the camera hardware
is not detected. Common causes:
- AI Thinker board not selected in `cam/platformio.ini` (`board = esp32cam`).
- GPIO0 held low (flash mode) — release and power-cycle.
- Physical camera ribbon cable is loose or reversed.

### 2. Confirm Bluetooth connection
The `_cameraTask` only runs when `_bt_connected == true`.
`_bt_connected` is set in `_dispatchFrame` when a `HEARTBEAT` is received from
the computer (`CamComm.cpp:291`).

Check the computer side: `CamReceiver` sends a `HEARTBEAT` reply whenever the
CAM sends one (`cam_receiver.py:144-149`). If the computer never sends a
heartbeat, the CAM will never start streaming.

Add a temporary log in `CamComm.cpp:_cameraTask`:
```cpp
Serial.printf("[CAM] bt_connected=%d, capturing frame\n", (int)_bt_connected);
```

### 3. Diagnose missing frames on the computer
If `CamReceiver.stats()['rx_images']` stays at 0:

a) **Chunks arriving but assembly times out** — `pending` > 0 in stats.
   Check `IMAGE_CHUNK_DATA_SIZE` (512) matches on both sides:
   - C++: `cam/src/types/Protocol.h:31`
   - Python: `computer/communication/protocol.py:43`

b) **No chunks arriving at all** — `rx_frames` stays 0.
   Confirm the computer's `SerialTransport` is open and pointing at the
   correct `/dev/cu.RobotCAM-*` port in `PHASE_CONFIGS[3]`.

c) **Chunks arriving with CRC errors** — `rx_frames` increases but
   `rx_images` does not. Check baud rate and cable quality.
   To verify CRC independently, add a print in `CamComm.cpp:_sendChunk`
   to log the last two bytes of the sent buffer (the CRC).

### 4. Diagnose heartbeat timeout (streaming paused)
The CAM pauses streaming when `millis() - _last_hb_rx_ms > HEARTBEAT_TIMEOUT_MS`
(default 5000 ms, `CamComm.h:22`).

The computer sends heartbeats in `CamReceiver._rx_loop` — at most once per
second when a HEARTBEAT arrives from the CAM. If the CAM never sees a reply,
it pauses.

Check the computer is actually receiving CAM heartbeats:
```python
# temporary probe in cam_receiver.py:_rx_loop
elif t == CamMsg.HEARTBEAT:
    print("[DBG] received CAM HEARTBEAT, sending reply")
```

### 5. Tune frame rate and JPEG quality
In `cam/src/main.cpp`:
```cpp
static constexpr float TARGET_FPS  = 6.0f;   // lower to reduce BT bandwidth
```
In `CamComm.cpp:_initCamera`:
```cpp
config.jpeg_quality = 15;          // 0=best, 63=worst; lower = larger file
config.frame_size   = FRAMESIZE_QVGA;   // 320x240
```
Reduce `TARGET_FPS` or increase `jpeg_quality` number if the BT link is saturated.

### 6. Check chunk size and `total_chunks` calculation
`CamComm.cpp:70-71`:
```cpp
uint16_t total_chunks = (uint16_t)((total_size + Protocol::IMAGE_CHUNK_DATA_SIZE - 1)
                                   / Protocol::IMAGE_CHUNK_DATA_SIZE);
```
This is ceiling integer division. Verify it matches the Python assembler
(`computer/communication/assembler.py`). Off-by-one here causes the last chunk
to be missing and the assembler to time out.

## Invariants
- `HEARTBEAT_TIMEOUT_MS = 5000` on the CAM side vs. the computer's watchdog
  warning at 5 s (`cam_receiver.py:110`). They must be close but the computer
  warning is informational — the CAM actually pauses the stream.
- `_bt_connected` is only set `true` by receiving a HEARTBEAT. It is set
  `false` by the watchdog. These are the only two state transitions.
- The `_tx_mutex` guards all BT writes in both `_cameraTask` and
  `_sendHeartbeat`. Never call `_bt.write()` without it.

## Verification
```bash
cd cam && pio run --target upload
python -m computer.main --phase 3
# computer stats loop should show rx_images increasing every ~150ms (6 FPS)
```
