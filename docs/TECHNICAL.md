# Technical Architecture and Windows Latency Notes

This document explains the design of Input Lag Fixer and the Windows concepts behind each supported optimization. It is written for reviewers, contributors, benchmarkers, and users who want to verify exactly what the tool changes.

## 1. Architecture Overview

Input Lag Fixer is intentionally implemented as a single Python module with narrow manager classes rather than a large framework. The operational design is:

- Configuration is loaded from JSON and validated before use.
- Preflight checks verify platform support, elevation status, and required modules.
- Each optimization step reports progress and writes logs.
- Registry writes are preceded by structured backup entries.
- Runtime-only requests such as timer resolution are released during restore.
- Errors are captured as OptimizationResult objects for GUI and CLI display.

Primary classes:

- `AppConfig`: Dataclass that stores validated user settings.
- `GameDefinition`: Dataclass describing supported games and process names.
- `ConfigManager`: Loads and saves config.json.
- `BackupManager`: Loads and saves backup.json.
- `WindowsTimerResolution`: ctypes wrapper around ntdll timer-resolution functions.
- `WindowsMessageQueue`: ctypes wrapper for bounded current-thread message pumping.
- `RegistryManager`: Reads, writes, backs up, and restores registry values.
- `ProcessManager`: Finds game processes and applies safe priority classes.
- `OptimizationEngine`: Coordinates preflight, apply, verify, rollback, and restore.
- `InputLagFixerApp`: Tkinter GUI layer that delegates work to OptimizationEngine.

## 2. Windows Timer Resolution

Windows maintains timer infrastructure used by sleeps, waitable timers, scheduler wakeups, multimedia timers, and other timed operations. Timer resolution is usually expressed in 100 ns units at the NT API layer. A value of 10,000 means 1 ms. A value of 156,250 means 15.625 ms.

Historically, applications called `timeBeginPeriod(1)` to request a 1 ms system timer period. Modern Windows versions have changed the semantics in several ways, including more aggressive timer coalescing and per-process effects. For benchmark reproducibility, it is still useful to know whether a process requested a lower interval and whether the kernel granted it.

Input Lag Fixer uses:

```text
NtQueryTimerResolution(
    OUT MinimumResolution,
    OUT MaximumResolution,
    OUT CurrentResolution
)

NtSetTimerResolution(
    IN DesiredResolution,
    IN SetResolution,
    OUT CurrentResolution
)
```

The tool calls `NtQueryTimerResolution` during preflight and calls `NtSetTimerResolution(target, TRUE, current)` during optimization. Restore calls `NtSetTimerResolution(target, FALSE, current)` for the same target.

Important details:
- The functions are exported by ntdll.dll and called through ctypes.
- The API returns NTSTATUS values; zero means success.
- The requested value is not guaranteed to be granted exactly.
- Timer resolution does not change a game engine input pipeline by itself.
- Timer resolution can increase power usage because the system wakes more frequently.
- The request is runtime-only and does not modify boot configuration.

## 3. HPET vs TSC vs ACPI Timers

Timer resolution is different from the hardware clock source. Hardware and firmware expose several timing facilities. Windows chooses among them based on processor, chipset, firmware, virtualization state, and boot configuration.

### HPET

HPET is the High Precision Event Timer. It is a platform timer exposed by chipset/firmware. Some older tuning guides recommend forcing HPET on or off with `bcdedit /set useplatformclock`, but the effect is hardware-dependent. Forcing HPET can improve, degrade, or have no effect on measured latency. It can also affect power behavior and scheduling overhead.

### TSC

TSC is the processor Time Stamp Counter. Modern invariant TSC implementations are fast and stable across power states on most modern systems. Windows often prefers TSC-based timekeeping where reliable. Cross-core synchronization and virtualization can complicate interpretation.

### ACPI PM Timer

The ACPI power-management timer is older and typically slower to query than invariant TSC. It may appear in fallback scenarios or on older hardware.

### Project Policy

Input Lag Fixer does not run `bcdedit`, does not set `useplatformclock`, does not set `disabledynamictick`, and does not modify `tscsyncpolicy`. Those changes require reboot-level testing and can create system-specific regressions. Contributors should not add automatic boot configuration edits without a separate design review and a strong rollback plan.

## 4. Input Message Queue Mechanics

Windows GUI threads receive messages through per-thread message queues. Typical messages include keyboard input, mouse input, paint requests, timers, hotkeys, and application-defined messages. A responsive GUI thread repeatedly retrieves and dispatches messages using APIs such as:

- `GetMessageW`
- `PeekMessageW`
- `TranslateMessage`
- `DispatchMessageW`

A traditional Win32 loop looks like:

```c
while (GetMessage(&msg, NULL, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessage(&msg);
}
```

Input Lag Fixer does not touch another process message queue. It does not clear a game input queue. It only keeps its own GUI responsive during operations and exposes a bounded `PeekMessageW` wrapper for current-thread diagnostics.

The relevant `PeekMessageW` signature is:

```text
BOOL PeekMessageW(
    LPMSG lpMsg,
    HWND hWnd,
    UINT wMsgFilterMin,
    UINT wMsgFilterMax,
    UINT wRemoveMsg
)
```

The project uses `PM_REMOVE` only for the current thread and applies a strict limit to prevent infinite loops.

## 5. Process Priority Classes

Windows scheduling combines process priority class and thread priority level to calculate base priorities. A higher base priority can reduce the chance that a CPU-bound background process delays a game thread, but it can also starve important system work if misused.

Supported priority classes:

| Project Value | Windows Meaning | Notes |
|---|---|---|
| `normal` | NORMAL_PRIORITY_CLASS | Default for most desktop applications. |
| `above_normal` | ABOVE_NORMAL_PRIORITY_CLASS | Conservative elevated setting and project default. |
| `high` | HIGH_PRIORITY_CLASS | Stronger setting for benchmark sessions. |

Unsupported:

| Value | Reason |
|---|---|
| `realtime` | Can starve drivers, desktop composition, audio, input, and security software. |

The implementation uses `psutil.Process.nice()` because psutil maps the request to Windows priority constants and handles process access errors cleanly.

## 6. Registry Keys Modified

Input Lag Fixer only modifies a small set of Game Bar/Game DVR-related values when that option is enabled.

| Hive | Path | Value | Type | Optimized Value | Effect |
|---|---|---|---|---:|---|
| HKCU | `System\GameConfigStore` | `GameDVR_Enabled` | REG_DWORD | 0 | Disables per-user Game DVR recording behavior. |
| HKCU | `System\GameConfigStore` | `GameDVR_FSEBehaviorMode` | REG_DWORD | 2 | Reduces fullscreen optimization/Game DVR interaction on some builds. |
| HKCU | `Software\Microsoft\Windows\CurrentVersion\GameDVR` | `AppCaptureEnabled` | REG_DWORD | 0 | Disables app capture for the current user. |
| HKLM | `SOFTWARE\Policies\Microsoft\Windows\GameDVR` | `AllowGameDVR` | REG_DWORD | 0 | Machine policy that disables Game DVR when permitted. |

Backup behavior:
- If a value exists, its original data and type are saved.
- If a value does not exist, the backup records existed=false.
- Restore writes existing values back with the original type.
- Restore deletes values that did not exist before optimization.
- Backup files are UTF-8 JSON under the application data directory.

## 7. Security Model

Administrator rights are needed for a subset of operations. The tool warns when it is not elevated rather than pretending every operation succeeded.

| Operation | Admin Needed | Why |
|---|---|---|
| HKCU Game DVR writes | Usually no | Current-user registry hive. |
| HKLM Game DVR policy writes | Yes | Machine-wide policy key. |
| Process priority change | Often yes | Access depends on target process integrity and ownership. |
| Timer resolution request | Usually no | Runtime request through ntdll. |
| Reading own config/logs | No | Per-user application data. |

The tool explicitly does not:
- disable Windows Defender
- add Defender exclusions
- install a kernel driver
- inject DLLs
- hook game input
- patch process memory
- hide from anti-cheat software
- contact a remote server

## 8. Performance Analysis Methodology

A useful latency benchmark must be repeatable. Software-only FPS counters do not measure end-to-end input latency. Recommended tools include NVIDIA LDAT, Reflex Analyzer-compatible monitors, photodiode rigs, or high-speed cameras.

Minimum report fields:
- CPU model and clock behavior
- GPU model and driver version
- motherboard and BIOS version
- mouse model and polling rate
- monitor model and refresh rate
- VRR/G-Sync/FreeSync state
- Windows version and build number
- game version and graphics settings
- overlay state
- sample count
- median, mean, and 95th percentile

Procedure:
1. Boot the system and wait for background startup tasks to settle.
2. Record baseline with no optimizer changes.
3. Apply one optimization category at a time for isolation.
4. Restart the game between runs if the game caches settings.
5. Collect at least 30 input-to-photon samples per condition.
6. Report both central tendency and tail latency.
7. Restore settings and rerun a sanity baseline when possible.

## 9. Failure and Rollback Strategy

Optimization is performed as a sequence of steps. If a step fails, the engine attempts partial rollback for completed steps. Runtime timer requests are released. Registry changes are restored from entries captured before writes. The result object records warnings and errors for display.

Rollback should be idempotent: running restore repeatedly should not damage the system. This is why the backup model distinguishes between absent values and existing values.

## 10. Contributor Checklist for New Optimizations

- [ ] Is the setting documented by Microsoft or well understood by Windows performance tooling?
- [ ] Can the original value be backed up exactly?
- [ ] Can restore be run more than once safely?
- [ ] Does the change require administrator rights?
- [ ] Could the change trigger anti-cheat or security-product concerns?
- [ ] Does the change affect battery life or thermals?
- [ ] Can the effect be benchmarked in isolation?
- [ ] Is the UI text honest about expected outcomes?

## 11. Glossary
- **100 ns unit:** The unit used by NT timer-resolution APIs. 10,000 units equal 1 ms.
- **ACPI:** Advanced Configuration and Power Interface, a firmware and OS power-management standard.
- **DPC:** Deferred Procedure Call, a Windows kernel mechanism used by drivers to defer work.
- **EDR:** Endpoint Detection and Response security software.
- **Game DVR:** Windows feature for recording and capturing gameplay.
- **HPET:** High Precision Event Timer, a platform hardware timer.
- **Input-to-photon latency:** Time from physical input to visible screen response.
- **NTSTATUS:** Status-code format returned by many Native API functions.
- **Scheduler:** Kernel component that chooses which thread runs on a CPU core.
- **TSC:** Time Stamp Counter, a CPU cycle/time counter used by modern systems.

## 12. References for Further Reading
- Microsoft Learn: Scheduling Priorities
- Microsoft Learn: Registry Functions
- Microsoft Learn: About Messages and Message Queues
- Windows Internals, Part 1 and Part 2
- NVIDIA LDAT and Reflex Analyzer documentation
