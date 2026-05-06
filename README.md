# Input Lag Fixer

**A transparent Windows latency-tuning utility for competitive gaming, benchmarking, and repeatable rollback.**

[![Build](https://img.shields.io/badge/build-configured-blue?style=flat-square)](.github/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](#license)
[![Version](https://img.shields.io/badge/version-2.1.0-blue?style=flat-square)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?style=flat-square&logo=windows)](#supported-windows-versions)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python)](requirements.txt)

Input Lag Fixer is an open-source Windows utility that applies a small set of reversible operating-system latency tweaks commonly used during competitive-gaming benchmark sessions. It focuses on measurable and explainable changes: timer-resolution requests, Game Bar/Game DVR policy changes, process priority assignment, and local input-message-queue maintenance for the tool's own process.

> **Honesty note:** this repository does not claim impossible latency reductions, anti-cheat bypasses, or universal FPS gains. Benchmark numbers in this README are an example measurement format and should be reproduced on your own hardware before drawing conclusions.

---

## Table of Contents

- [Input Lag Fixer](#input-lag-fixer)
  - [What It Does](#what-it-does)
    - [Timer Resolution Request](#timer-resolution-request)
    - [HPET, TSC, ACPI, and Clock Sources](#hpet-tsc-acpi-and-clock-sources)
    - [Game Bar and Game DVR Policy](#game-bar-and-game-dvr-policy)
    - [Input Message Queue Maintenance](#input-message-queue-maintenance)
    - [Game Process Priority](#game-process-priority)
    - [Backup and Restore](#backup-and-restore)
  - [What It Does Not Do](#what-it-does-not-do)
  - [Benchmarking](#benchmarking)
  - [Screenshots](#screenshots)
  - [Installation](#installation)
    - [Install a Pre-Built EXE](#install-a-pre-built-exe)
    - [Run from Source](#run-from-source)
    - [Build Your Own EXE](#build-your-own-exe)
  - [Usage](#usage)
    - [GUI Mode](#gui-mode)
    - [CLI Mode](#cli-mode)
    - [Restore Original Settings](#restore-original-settings)
  - [Supported Games](#supported-games)
  - [Supported Windows Versions](#supported-windows-versions)
  - [Safety Model](#safety-model)
  - [Technical Details](#technical-details)
    - [Timer APIs](#timer-apis)
    - [Registry APIs](#registry-apis)
    - [Process APIs](#process-apis)
    - [Message Queue APIs](#message-queue-apis)
    - [Rollback Design](#rollback-design)
  - [Project Structure](#project-structure)
  - [Configuration](#configuration)
  - [Logging](#logging)
  - [FAQ](#faq)
  - [Contributing](#contributing)
  - [Changelog](#changelog)
  - [Credits and Acknowledgments](#credits-and-acknowledgments)
  - [License](#license)
  - [Contact and Support](#contact-and-support)

---

## What It Does

Input Lag Fixer applies latency-related Windows settings in a controlled, logged, and reversible way. Each optimization is implemented as an independent step, so a failure in one step can be rolled back without leaving the rest of the system in an ambiguous state.

### Timer Resolution Request

Windows schedules timer callbacks at a system timer resolution. Historically, many applications requested a 1 ms timer period through multimedia timer APIs, while newer Windows versions handle timer coalescing and per-process timer resolution differently. Input Lag Fixer can request a lower timer interval for the current session to reduce latency in workloads that are sensitive to scheduler wake-up granularity.

The implementation attempts to:

1. Query the current, minimum, and maximum timer resolution through `NtQueryTimerResolution`.
2. Request a target resolution through `NtSetTimerResolution`.
3. Log the actual resolution granted by the kernel.
4. Release the request during restore or program shutdown.

This does not force the game engine to process input faster. It may help if a game, overlay, benchmark tool, controller mapper, or polling component relies on waitable timers, sleeps, or short periodic callbacks.

### HPET, TSC, ACPI, and Clock Sources

High Precision Event Timer (HPET), Time Stamp Counter (TSC), and ACPI power-management timers are separate concepts from timer resolution. They relate to how Windows measures time and schedules events. Modern Windows systems usually choose an appropriate clock source automatically.

Input Lag Fixer **does not** change boot configuration flags such as `useplatformclock`, `disabledynamictick`, or `tscsyncpolicy` because those settings can have hardware-specific side effects and require reboot-level changes. The tool documents those concepts for benchmarkers but intentionally limits itself to safer runtime APIs and reversible registry policy changes.

### Game Bar and Game DVR Policy

Windows Game Bar, Game DVR, and background capture features can add hooks, overlays, background services, storage writes, and capture-related work during gameplay. Input Lag Fixer can disable the common per-user and policy registry values used by Game DVR and capture features.

The tool backs up all registry values before changing them. When restore is selected, the original values are written back if they existed. If a value did not exist before optimization, it is removed during restore rather than blindly set to a default.

Commonly managed values include:

- `HKCU\System\GameConfigStore\GameDVR_Enabled`
- `HKCU\System\GameConfigStore\GameDVR_FSEBehaviorMode`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR\AppCaptureEnabled`
- `HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR\AllowGameDVR`

### Input Message Queue Maintenance

Every GUI thread has a message queue. A poorly behaved overlay, macro tool, benchmark companion, or launcher can accumulate messages if it stops pumping them. Input Lag Fixer only drains benign pending messages from its **own** GUI thread during optimization progress updates. It does not inject into games, hook games, alter another process' input stream, or clear another application's queue.

The implementation uses `PeekMessageW` in a bounded loop to avoid blocking. This keeps the utility responsive while long-running optimization checks are performed.

### Game Process Priority

Windows assigns CPU scheduling priority based on process priority class and thread priority. Input Lag Fixer can set a detected game process to `HIGH_PRIORITY_CLASS` or `ABOVE_NORMAL_PRIORITY_CLASS` through the standard Windows process APIs.

The default is **Above Normal**, not **Realtime**. Realtime priority can starve drivers, audio threads, desktop composition, and security software. The application refuses to set realtime priority because doing so is unsafe for general users.

Process priority is temporary. It resets when the process exits and can be restored manually while the process is running.

### Backup and Restore

Before changing a supported registry value, Input Lag Fixer writes a JSON backup file containing:

- registry hive
- registry path
- value name
- value type
- original value
- whether the value existed
- timestamp
- tool version

Restore mode reads the backup and reverses every change. If a restore item fails, it is logged and displayed to the user so manual remediation is possible.

---

## What It Does Not Do

Input Lag Fixer intentionally avoids high-risk or deceptive behavior:

- It does **not** bypass anti-cheat systems.
- It does **not** inject DLLs into games.
- It does **not** patch game memory.
- It does **not** spoof hardware identifiers.
- It does **not** modify kernel drivers.
- It does **not** hide from antivirus or EDR tools.
- It does **not** disable Defender automatically.
- It does **not** promise universal latency improvements.

If a tool claims it is an "undetectable latency bypass" or asks you to disable antivirus, do not run it.

---

## Benchmarking

Latency is hardware-, driver-, game-, and measurement-method dependent. The following table is an **example reproducible reporting format**, not a claim that these exact numbers will happen on every system.

Recommended measurement methods:

- NVIDIA LDAT, Reflex Analyzer, or equivalent hardware
- High-speed camera at 1000 FPS or higher
- Same monitor refresh rate, same game scene, same driver version
- At least 30 samples per test case
- Median and 95th percentile reported separately

| Game | Before Median (ms) | After Median (ms) | Example Improvement | Example Test System |
|---|---:|---:|---:|---|
| Counter-Strike 2 | 24.8 | 22.9 | 7.7% | Ryzen 7 7800X3D, RTX 4070 Ti, 240 Hz, Win 11 23H2 |
| Valorant | 18.6 | 17.9 | 3.8% | Ryzen 7 7800X3D, RTX 4070 Ti, 240 Hz, Win 11 23H2 |
| Fortnite | 31.2 | 29.4 | 5.8% | Core i7-13700K, RTX 4080, 240 Hz, Win 11 23H2 |
| Apex Legends | 33.5 | 31.8 | 5.1% | Ryzen 5 7600X, RX 7800 XT, 165 Hz, Win 10 22H2 |
| Overwatch 2 | 21.4 | 20.6 | 3.7% | Core i5-12600K, RTX 3060 Ti, 144 Hz, Win 11 23H2 |

Example formula:

```text
percentage_improvement = ((before_ms - after_ms) / before_ms) * 100
```

When publishing results, include:

1. CPU and motherboard.
2. GPU and driver version.
3. Mouse polling rate.
4. Monitor refresh rate and VRR status.
5. Windows build number.
6. Game version.
7. Whether overlays were enabled.
8. Sample size and measurement device.

---

## Screenshots

The repository uses descriptive placeholder images until a release build captures real screens.

![Main application dashboard showing dark theme, game selector, optimization status, and restore button](docs/images/main-dashboard-placeholder.png)

![Settings panel with timer resolution, Game DVR, process priority, and logging options](docs/images/settings-panel-placeholder.png)

![Benchmark report view showing before and after latency results for multiple games](docs/images/benchmark-report-placeholder.png)

---

## Installation

### Install a Pre-Built EXE

1. Open the repository's **Releases** page.
2. Download `InputLagFixer-Setup.exe` or `InputLagFixer-Portable.zip`.
3. Verify the SHA-256 hash if one is provided for the release.
4. Right-click the executable and select **Run as administrator**.
5. Review the settings before applying optimizations.

The portable version stores configuration under:

```text
%APPDATA%\InputLagFixer\
```

### Run from Source

Install Python 3.11 or newer, then run:

```powershell
git clone https://github.com/example/input-lag-fixer.git
cd input-lag-fixer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python input_lag_fixer.py
```

For CLI mode:

```powershell
python input_lag_fixer.py --cli --list-games
python input_lag_fixer.py --cli --optimize --game cs2
python input_lag_fixer.py --cli --restore
```

### Build Your Own EXE

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name InputLagFixer input_lag_fixer.py
```

The built executable will be created under:

```text
dist\InputLagFixer.exe
```

---

## Usage

### GUI Mode

1. Start the tool as administrator.
2. Select a game from the dropdown.
3. Open **Settings** and confirm which optimizations are enabled.
4. Click **Run Optimization**.
5. Watch the progress bar and status text.
6. Launch or focus your game.
7. Use **Restore** after the session if you want to revert registry policies and process priorities.

### CLI Mode

List supported game definitions:

```powershell
python input_lag_fixer.py --cli --list-games
```

Apply optimizations for a detected game:

```powershell
python input_lag_fixer.py --cli --optimize --game valorant
```

Restore original settings:

```powershell
python input_lag_fixer.py --cli --restore
```

Print version:

```powershell
python input_lag_fixer.py --version
```

### Restore Original Settings

Restore mode:

- releases timer-resolution requests
- writes backed-up registry values back
- removes registry values that did not exist before optimization
- resets tracked game processes to normal priority when possible
- writes a restore report to the log

If restore fails for a registry key because a policy is managed by your organization, contact your IT administrator.

---

## Supported Games

The built-in list is intentionally small and uses process names for detection:

| Key | Game | Process |
|---|---|---|
| `cs2` | Counter-Strike 2 | `cs2.exe` |
| `valorant` | Valorant | `VALORANT-Win64-Shipping.exe` |
| `fortnite` | Fortnite | `FortniteClient-Win64-Shipping.exe` |
| `apex` | Apex Legends | `r5apex.exe` |
| `overwatch2` | Overwatch 2 | `Overwatch.exe` |

You can add custom games in `config.json`.

---

## Supported Windows Versions

| Version | Support |
|---|---|
| Windows 11 23H2+ | Supported |
| Windows 11 22H2 | Supported |
| Windows 10 22H2 | Supported |
| Windows Server | Not tested |
| Windows 8.1 or older | Not supported |

The application checks the OS at startup and warns if it is not running on Windows 10/11.

---

## Safety Model

The safest latency-tuning tool is one that makes few changes, explains them, and can undo them. Input Lag Fixer follows these principles:

1. **No hidden behavior.** Every step is logged.
2. **No anti-cheat bypassing.** Standard Windows APIs only.
3. **No realtime priority.** The scheduler must remain healthy.
4. **No automatic antivirus disabling.** Security software stays enabled.
5. **No boot configuration edits.** Reboot-level timer settings are not touched.
6. **Rollback first.** Backups are created before writes.
7. **Bounded operations.** Message pumping and process scanning use limits.
8. **User consent.** Optimizations are applied only after the user clicks a button or passes CLI flags.

---

## Technical Details

### Timer APIs

The timer-resolution wrapper dynamically loads `ntdll.dll`, locates `NtQueryTimerResolution` and `NtSetTimerResolution`, and calls them with `ctypes`. These functions are not part of the stable Win32 API contract, so errors are handled conservatively and logged.

The tool stores the requested timer value and releases it at shutdown by calling `NtSetTimerResolution(target, FALSE, current)`.

### Registry APIs

Registry writes use Python's `winreg` module on Windows. The tool opens keys with the minimum required access for each operation. HKLM policy writes require administrator rights, while HKCU writes usually do not.

Before every registry change:

1. The existing value is queried.
2. A backup entry is written to JSON.
3. The new value is written.
4. The value is read back for verification.

### Process APIs

Game detection uses `psutil.process_iter` and avoids opening unnecessary handles. Priority changes use `psutil.Process.nice()` on Windows, mapping to Windows priority classes.

Accepted priority classes:

- Normal
- Above Normal
- High

Rejected priority classes:

- Realtime

### Message Queue APIs

The GUI pumps its own pending messages using Tkinter's event loop. A `ctypes` wrapper for `PeekMessageW` is included for diagnostic use, but it only targets the current thread and does not alter game input.

### Rollback Design

Rollback is idempotent. Running restore multiple times should not create additional damage. Missing backup files are treated as a warning rather than a fatal error.

---

## Project Structure

```text
input-lag-fixer/
├── .github/
│   └── workflows/
│       └── build.yml
├── docs/
│   └── TECHNICAL.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── input_lag_fixer.py
├── requirements.txt
└── setup.py
```

---

## Configuration

Default configuration path:

```text
%APPDATA%\InputLagFixer\config.json
```

Example:

```json
{
  "timer_resolution_100ns": 10000,
  "disable_game_dvr": true,
  "set_process_priority": true,
  "priority_class": "above_normal",
  "selected_game": "cs2",
  "log_level": "INFO",
  "custom_games": []
}
```

Validation rules:

- `timer_resolution_100ns` must be between 5000 and 156250.
- `priority_class` must be `normal`, `above_normal`, or `high`.
- game keys must be lowercase letters, numbers, underscores, or hyphens.
- process names must end in `.exe`.

---

## Logging

Logs are written to:

```text
%APPDATA%\InputLagFixer\logs\input_lag_fixer.log
```

The logger uses:

- console output for CLI mode
- rotating file handler
- timestamps
- log level names
- operation identifiers
- exception tracebacks for unexpected failures

---

## FAQ

### 1. Is this safe?

The tool uses documented or widely understood Windows APIs and backs up registry values before changing them. It avoids risky operations such as realtime priority, driver installation, DLL injection, Defender disabling, or boot configuration edits.

### 2. Will this bypass anti-cheat?

No. It does not bypass, evade, or interfere with anti-cheat systems. It only uses normal operating-system APIs. Some anti-cheat vendors may still dislike system-tuning utilities running during competitive matches, so check your game's rules before using any optimizer.

### 3. Can this trigger antivirus false positives?

Source-mode execution should not. A bundled EXE made with PyInstaller can sometimes trigger heuristic warnings because many unrelated programs also use PyInstaller. Build from source if you want maximum transparency.

### 4. Should I use this on a laptop?

You can, but lower timer resolution and higher process priority may increase power usage and heat. Use AC power, monitor temperatures, and restore settings after the session.

### 5. Which Windows versions are supported?

Windows 10 22H2 and Windows 11 22H2/23H2 are supported. Older versions are not supported because timer behavior, Game DVR policies, and security defaults differ.

### 6. How do I uninstall it?

Run **Restore** first, then delete the application folder. If installed through a package manager, uninstall through that package manager. Configuration and logs are stored under `%APPDATA%\InputLagFixer`.

### 7. How can I verify it is open source?

Read `input_lag_fixer.py`, build your own executable with PyInstaller, and compare behavior with the logs. The tool does not require network access.

### 8. Will it improve FPS?

Not necessarily. It targets latency-related behavior, not rendering throughput. Some systems may see no measurable change.

### 9. Why not force HPET off?

Because HPET behavior is hardware-specific and boot-level changes can degrade performance on some machines. This tool avoids those changes by design.

### 10. Why not use realtime priority?

Realtime priority can starve critical system threads. That can cause audio dropouts, mouse freezes, driver instability, and hard-to-debug stutter.

### 11. Does it need administrator rights?

Administrator rights are required for HKLM policy writes and reliable process priority changes. The GUI shows a warning if it is not elevated.

### 12. Does it require internet access?

No. The application performs local checks and local configuration writes only.

---

## Contributing

Contributions are welcome when they make the tool safer, more transparent, easier to test, or better documented.

### Code Style

- Follow PEP 8.
- Use type hints on every function.
- Use Google-style docstrings for public APIs.
- Keep Windows API wrappers small and tested.
- Avoid global mutable state where practical.

### Commit Conventions

Use Conventional Commits:

```text
feat: add configurable priority class
fix: restore missing GameDVR registry values correctly
docs: expand timer-resolution explanation
test: add config validation coverage
```

### Pull Request Process

1. Open an issue describing the change.
2. Add or update tests.
3. Run linting and unit tests locally.
4. Update documentation when behavior changes.
5. Submit a PR with a concise summary and risk assessment.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full changelog.

Recent highlights:

- `2.1.0`: GUI settings panel, structured rollback report, improved CLI flags.
- `2.0.0`: new optimization engine and backup format.
- `1.3.0`: process-priority controls and game definitions.
- `1.0.0`: initial timer-resolution and Game DVR controls.

---

## Credits and Acknowledgments

This project builds on public Windows API documentation, Python's standard library, the psutil project, and the work of latency researchers who publish reproducible measurement methodology.

Special thanks to:

- Python maintainers
- psutil maintainers
- Tkinter/Tcl/Tk contributors
- Windows performance-analysis community
- Competitive players who publish reproducible benchmarks instead of unverifiable claims

---

## License

Input Lag Fixer is released under the MIT License. See [LICENSE](LICENSE).

---

## Contact and Support

Use GitHub Issues for:

- reproducible bugs
- documentation errors
- feature requests
- benchmark methodology improvements

Do not open issues requesting:

- anti-cheat bypasses
- hidden execution
- Defender disabling
- hardware-ID spoofing
- game memory patching
