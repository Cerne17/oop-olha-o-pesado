---
name: sanitize-cpp
description: Sanitize and refactor C++ firmware files for readability and correctness. Use when code has opaque or foreign-language field names, magic number status codes, undocumented hardware truth tables, unannotated state machine enums, single-use lambdas that should be named methods, dense bitwise operations, or stale comments after renames.
---

# Skill: Sanitize C++ firmware code

## Objective
Improve readability and correctness of C++ firmware without changing behaviour.

## Key files
| File | What to check |
|------|---------------|
| `robot/src/types/MotorTypes.h` | Hardware struct field names, truth-table docs |
| `robot/src/types/Protocol.h` | Magic status codes, dense bitwise ops, missing enums |
| `robot/src/control/WheelController.h/.cpp` | Lambdas, incomplete operations, stale comments |
| `robot/src/communication/RobotComm.h/.cpp` | Enum annotation, magic buffer sizes, stale task names |
| `robot/src/main.cpp` | Pin constant clarity, struct initialiser legibility |

---

## Checklist

### 1. Naming
- [ ] Field names describe **what the pin/value does**, not what it was called elsewhere
  - Bad: `esq` (Portuguese "left"), `dir` (ambiguous direction)
  - Good: `left`, `right` — the rotation direction when that pin is HIGH
  - Rule: if removing the comment still leaves the name clear, the name is good
- [ ] Raw integer status/error codes replaced with typed enums
  - Bad: `_sendAck(seq, 1)` — what is 1?
  - Good: `_sendAck(seq, AckStatus::CRC_ERROR)`
- [ ] After any rename, grep for stale occurrences in comments, task names, and docstrings
  ```bash
  grep -rn "old_name" robot/src/
  ```

### 2. Documentation
- [ ] Hardware structs document all meaningful I/O state combinations as a truth table
  - Pattern: H-bridge pins `en / right / left` → rows for forward / reverse / coast / brake
  - Include the "never do this" row (e.g. both direction pins HIGH = short-circuit)
- [ ] State machine enum values have an inline comment: what byte or condition each state waits for
  - Pattern: `WAIT_START_2,  // got 0xCA, waiting for 0xFE`
- [ ] Dense bitwise operations have a one-line explanation
  - Pattern: CRC inner loop — note polynomial name and what the MSB check does
- [ ] Multi-byte little-endian serialization is annotated `// little-endian`
- [ ] Magic buffer sizes reference the protocol constants they derive from
  - Pattern: `// max frame = OVERHEAD(13) + MAX_PAYLOAD(16) = 29; 256 gives headroom`

### 3. Code structure
- [ ] Single-use lambdas inside methods → named private static method in the class
  - Bad: `auto slew = [](float cur, float tgt) -> float { ... };`
  - Good: `static float _slew(float current, float target);` declared in `.h`, defined in `.cpp`
- [ ] Operations that should be symmetric are symmetric — check against `begin()` as the reference
  - Pattern: `emergencyStop()` must zero the same pins `begin()` initialises; missing one = latent bug

### 4. Process
1. Read **all** related `.h` and `.cpp` files before touching anything
2. List every issue, grouped by: naming / documentation / structure
3. Apply renames with `replace_all: true` — never rename one occurrence while leaving others
4. After each rename, grep the full `robot/src/` tree to confirm zero stale references
5. Commit in atomic groups — one commit per concern (naming, docs, structure)

---

## Verification
```bash
# No stale old field names
grep -rn "\.esq\|\.dir\b" robot/src/

# No raw ACK status literals
grep -n "_sendAck.*[, ][012])" robot/src/communication/RobotComm.cpp

# Firmware still builds
cd robot && pio run
```
