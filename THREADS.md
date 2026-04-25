# Threading Model

The Python `computer/` package is fully multithreaded. The main thread never
blocks on I/O or computation — it only waits for a stop condition (ESC key or
SIGINT). All real work happens in daemon threads that are started by each
module's `start()` method and stopped by its `stop()` method.

---

## Phase 1 & 2 — Manual control

```
Main thread
  |
  +-- keyboard-pub          (KeyboardController._publish_loop)
  |       |
  |       | ControlSignal (synchronous notify, no thread crossing)
  |       v
  +-- [pynput listener]     (keyboard.Listener — spawned by pynput)
  |
  +-- robot-tx              (RobotSender._tx_loop)
```

| Thread | Name | Owner class | Loop method |
|--------|------|-------------|-------------|
| Publish loop | `keyboard-pub` | `KeyboardController` | `_publish_loop` |
| OS key listener | *(pynput internal)* | `keyboard.Listener` | internal |
| Robot TX | `robot-tx` | `RobotSender` | `_tx_loop` |
| Main | *(unnamed)* | `main()` | ESC poll |

### What each thread does

**`keyboard-pub`**
Runs at 20 Hz (configurable via `publish_rate_hz`). On every tick it reads the
current `_pressed` set, computes a `ControlSignal` using the arrow-key angle
formula, and calls `_notify_control()`. That call is **synchronous** — it
directly invokes `RobotSender.on_control()` on this thread, which just drops
the signal into a `queue.Queue(maxsize=1)` and returns immediately.

**pynput listener**
Spawned internally by `keyboard.Listener.start()`. Receives raw OS keyboard
events and updates the `_pressed` set via `_on_press` / `_on_release`
callbacks. This is the only thread that touches `_pressed` via writes; all
other reads take a snapshot copy first.

**`robot-tx`**
Blocks on `cmd_queue.get(timeout=interval)`. When a `ControlSignal` arrives it
serialises it into a `CONTROL_REF` binary frame and writes it to the transport.
If the queue stays empty for a full interval it sends a `HEARTBEAT` frame
instead, keeping the robot's watchdog alive. Uses a newest-wins queue
(`maxsize=1`): if a new signal arrives before the previous one is consumed, the
old one is evicted.

**Main thread**
Polls `keyboard.is_esc_pressed` every 100 ms. On ESC (or SIGINT/SIGTERM) it
calls `_shutdown()`, which sets stop events, joins worker threads, and exits.

---

## Phase 3 — Autonomous vision

```
Main thread (stats loop every 5 s)
  |
  +-- cam-rx                (CamReceiver._rx_loop)
  |       |
  |       | Frame (synchronous notify, crosses into vision-worker's queue)
  |       v
  +-- vision-worker         (VisionProcessor._worker_loop)   [stub]
  |       |
  |       | FrameResult (synchronous notify -> on_result -> on_control)
  |       v
  +-- robot-tx              (RobotSender._tx_loop)
```

| Thread | Name | Owner class | Loop method |
|--------|------|-------------|-------------|
| CAM RX | `cam-rx` | `CamReceiver` | `_rx_loop` |
| Vision worker | `vision-worker` | `VisionProcessor` | `_worker_loop` |
| Robot TX | `robot-tx` | `RobotSender` | `_tx_loop` |
| Main | *(unnamed)* | `main()` | stats poll |

### What each thread does

**`cam-rx`**
Calls `transport.receive_available()` (non-blocking) in a tight loop with a
5 ms sleep when no data is available. Feeds raw bytes into a `FrameDecoder`
state machine. When a complete wire frame arrives:

- `IMAGE_CHUNK` — passes header + JPEG bytes to `ImageAssembler`. When
  `ImageAssembler` signals a complete image it calls `_notify_frame(frame)`,
  which synchronously calls `VisionProcessor.on_frame()`. That method drops
  the `Frame` into the vision worker's `queue.Queue(maxsize=2)` and returns
  immediately, so `cam-rx` is never stalled by vision processing time.
  Then it sends an `ACK` back to the CAM.
- `HEARTBEAT` — records receive timestamp; replies with its own `HEARTBEAT`
  at most once per second.
- Unknown / bad CRC — sends `ACK` with error status.

Also runs a heartbeat watchdog: if no HEARTBEAT arrives for 5 s it logs a
warning (it does not disconnect — the CAM firmware handles that side).

**`vision-worker`** *(stub — to be implemented)*
Dequeues `Frame` objects, runs each registered `Detector`, assembles a
`FrameResult`, and calls `_notify_result(result)`. That synchronously calls
`BlobFollowerStrategy.on_result()`, which computes a `ControlSignal` and calls
`_notify_control()`, which in turn calls `RobotSender.on_control()`. The entire
chain from dequeue to enqueue into `robot-tx` runs on this thread. Newest-wins
queuing at both ends ensures neither the vision frame queue nor the robot
command queue ever accumulates stale data.

**`robot-tx`**
Identical behaviour to the manual-mode description above.

**Main thread**
Sleeps 5 s, prints stats from `CamReceiver.stats()` and `RobotSender.stats()`,
then sleeps again. Has no functional role — it only keeps the process alive and
provides a periodic health readout.

---

## Queue boundaries

The only points where data crosses thread boundaries are explicit queues:

| Queue | Producer thread | Consumer thread | Overflow policy |
|-------|-----------------|-----------------|-----------------|
| `VisionProcessor._frame_queue` | `cam-rx` (via `on_frame`) | `vision-worker` | newest wins — oldest evicted |
| `RobotSender._cmd_queue` | `keyboard-pub` or `vision-worker` (via `on_control`) | `robot-tx` | newest wins — oldest evicted |

All other calls between modules (`_notify_frame`, `_notify_result`,
`_notify_control`) are **synchronous method calls on the calling thread** —
they return immediately because the callee only enqueues and does not do any
I/O or heavy computation inline.

---

## Thread safety notes

- `_pressed` (`KeyboardController`) — written by the pynput listener, read by
  `keyboard-pub`. Reads always take a snapshot copy (`self._pressed.copy()`)
  before iterating, which is safe for CPython's GIL-protected `set` operations.
- Sequence counters (`_seq` in `CamReceiver` and `RobotSender`) — protected
  by a `threading.Lock` via `_next_seq()`.
- Stop signals — all loops check a `threading.Event` (`_stop_event`) rather
  than a plain boolean so that the flag write is visible across threads without
  relying on the GIL.
- All worker threads are created as **daemon threads** (`daemon=True`), so they
  are automatically killed if the main thread exits unexpectedly without calling
  `stop()`.
