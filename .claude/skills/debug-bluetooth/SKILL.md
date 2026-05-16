---
name: debug-bluetooth
description: Debug Bluetooth-related issues. Note: neither the Robot ESP32 nor the ESP32-CAM uses Bluetooth anymore — both communicate over UDP/WiFi. Use when BT debugging is needed for a different component, or to understand historical context.
---

# Skill: Debug Bluetooth — Historical / Not applicable

> **Note**: As of the current firmware, neither the Robot ESP32 nor the ESP32-CAM
> uses Bluetooth Classic SPP. Both boards communicate over **UDP/WiFi**.
>
> - Robot: UDP on port 5005 (`robot/src/communication/RobotComm.cpp`)
> - CAM: UDP on port 5006 (`cam/src/communication/CamComm.cpp`)
>
> For WiFi/UDP connection issues use:
> - `/debug-robot-comm` — robot firmware connection and protocol
> - `/debug-cam-comm` — CAM firmware connection and streaming
> - `/debug-udp` — UDP-specific issues (no datagrams, CRC, watchdog)

## If you still need BT debugging (unrelated component)

Consult git history for the pre-UDP firmware (before the WiFi migration) or
refer to `DIAGNOSIS.md` which documents the BT SPP handshake overflow bug that
was the root cause of the migration.
