---
name: debug-cam-comm
description: Debug CAM firmware communication issues — camera init failures, JPEG streaming problems, heartbeat timeouts, or the computer not receiving frames over UDP/WiFi. Use when ESP32-CAM is not streaming, frames are missing or corrupt, or the watchdog pauses streaming.
---

# Skill: Debug CAM firmware communication

## Objective
Diagnose issues on the ESP32-CAM — camera initialisation failures, JPEG
streaming problems, heartbeat timeouts, or the computer not receiving frames.

## Key files
| File | Role |
|------|------|
| `cam/src/communication/CamComm.h` | Task declarations, RX state machine, `_client_known` flag |
| `cam/src/communication/CamComm.cpp` | `_cameraTask`, `_udpTask`, `_sendChunk`, `_dispatchFrame` |
| `cam/src/types/Protocol.h` | `MsgType` enum, `ImageChunkHeader`, CRC, frame constants |
| `cam/src/main.cpp` | `TARGET_FPS`, `UDP_PORT` config |

## Step-by-step

### 1. Open the serial monitor
```bash
cd cam
pio device monitor --baud 115200
```
Expected boot sequence:
```
=== CAM ESP32 booting ===
[CAM] WiFi IP: 192.168.1.43
[CAM] UDP listening on port 5006
=== Ready ===
```

If you see `[CAM] FATAL: camera init failed — halting`, the camera hardware
is not detected. Common causes:
- AI Thinker board not selected in `cam/platformio.ini` (`board = esp32cam`).
- GPIO0 held low (flash mode) — release and power-cycle.
- Physical camera ribbon cable is loose or reversed.

If WiFi never connects (dots printed indefinitely):
- Check `cam/src/credentials.h` SSID/PASS. The file is gitignored; copy from
  `credentials.example.h` and fill in your credentials, then reflash.

### 2. Confirm the computer can reach the CAM
The `_cameraTask` only streams when `_client_known == true`.
`_client_known` is set in `_dispatchFrame` when a `HEARTBEAT` is received from
the computer (`CamComm.cpp`).

Check `PHASE_CONFIGS[3].cam_port` in `computer/main.py` matches the IP printed
on boot:
```python
cam_port = "192.168.1.43:5006",
```

Check the computer side: `CamReceiver` sends a `HEARTBEAT` reply whenever the
CAM sends one (`cam_receiver.py:144-149`). If the computer never sends a
heartbeat, the CAM will never start streaming.

Add a temporary log in `CamComm.cpp:_cameraTask`:
```cpp
Serial.printf("[CAM] client_known=%d, capturing frame\n", (int)_client_known);
```

### 3. Diagnose missing frames on the computer
If `CamReceiver.stats()['rx_images']` stays at 0:

a) **Chunks arriving but assembly times out** — `pending` > 0 in stats.
   Check `IMAGE_CHUNK_DATA_SIZE` (512) matches on both sides:
   - C++: `cam/src/types/Protocol.h:31`
   - Python: `computer/communication/protocol.py:43`

b) **No chunks arriving at all** — `rx_frames` stays 0.
   Confirm `PHASE_CONFIGS[3].cam_port` IP:port matches the CAM's boot output.
   Ensure computer and CAM are on the same WiFi network.

c) **Chunks arriving with CRC errors** — `rx_frames` increases but
   `rx_images` does not. Check UDP packet fragmentation (JPEG chunk size
   `IMAGE_CHUNK_DATA_SIZE=512` + header overhead stays well under typical MTU).
   To verify CRC independently, add a print in `CamComm.cpp:_sendChunk`
   to log the last two bytes of the sent buffer (the CRC).

### 4. Diagnose heartbeat timeout (streaming paused)
The CAM pauses streaming when `millis() - _last_hb_rx_ms > HEARTBEAT_TIMEOUT_MS`
(default 5000 ms, `CamComm.h`).

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
static constexpr float TARGET_FPS = 6.0f;   // lower to reduce UDP bandwidth
```
In `CamComm.cpp:_initCamera`:
```cpp
config.jpeg_quality = 15;          // 0=best, 63=worst; lower = larger file
config.frame_size   = FRAMESIZE_QVGA;   // 320x240
```
Reduce `TARGET_FPS` or increase `jpeg_quality` number if the UDP link is saturated.

### 6. Check chunk size and `total_chunks` calculation
`CamComm.cpp`:
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
- `_client_known` is only set `true` by receiving a HEARTBEAT. It is set
  `false` by the watchdog. These are the only two state transitions.
- `_tx_mutex` guards all UDP writes in both `_cameraTask` and
  `_sendHeartbeat`. Never send without it.

## Verification
```bash
cd cam && pio run --target upload
python -m computer.main --phase 3
# computer stats loop should show rx_images increasing every ~150ms (6 FPS)
```
