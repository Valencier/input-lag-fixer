# Changelog

All notable changes to Input Lag Fixer are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows semantic versioning.

## [2.1.0] - 2026-05-06

### Added

- Added a dark themed Tkinter settings panel for timer resolution, Game DVR policy, process-priority, and logging options.
- Added CLI flags: `--cli`, `--optimize`, `--restore`, `--game`, `--list-games`, `--version`, and `--run-tests`.
- Added structured `OptimizationResult` and `ProgressEvent` objects for GUI and CLI reporting.
- Added bounded current-thread message-queue draining for application responsiveness diagnostics.
- Added built-in unit tests for configuration validation, game definitions, and utility functions.

### Changed

- Changed restore flow to be idempotent and tolerant of missing backup files.
- Changed default process priority target to `above_normal` rather than `high`.
- Improved logging with rotating file output and console thresholds.
- Expanded README safety language around anti-cheat compatibility and measurement methodology.

### Fixed

- Fixed configuration validation so unsupported `realtime` priority is rejected.
- Fixed custom game validation so process names must end with `.exe`.
- Fixed restore semantics for registry values that did not exist before optimization.

### Removed

- Removed any suggestion that boot-level HPET flags should be modified automatically.

## [2.0.0] - 2026-04-18

### Added

- Added `OptimizationEngine` to coordinate preflight, apply, verify, rollback, and restore phases.
- Added JSON registry backup format with timestamp, value type, and existence tracking.
- Added Windows API wrapper for `NtQueryTimerResolution` and `NtSetTimerResolution`.
- Added conservative Windows version and administrator-rights preflight checks.

### Changed

- Reworked registry operations into a dedicated `RegistryManager`.
- Reworked process discovery into a dedicated `ProcessManager`.
- Replaced ad-hoc print diagnostics with structured logging.
- Documented unsupported operations such as driver installation and anti-cheat bypasses.

### Fixed

- Fixed partial failures leaving Game DVR settings modified without a backup.
- Fixed timer-release logic to no-op when no timer request was active.
- Fixed unknown game keys returning ambiguous errors.

### Removed

- Removed prototype global configuration constants in favor of `AppConfig`.

## [1.4.0] - 2026-03-29

### Added

- Added GitHub Actions workflow for Windows build validation.
- Added PyInstaller packaging command for one-file executable builds.
- Added `setup.py` metadata and console entry point.
- Added documentation for supported Windows versions and log locations.

### Changed

- Changed project layout to separate docs, workflow, packaging, and runtime files.
- Improved README installation instructions for source and EXE usage.
- Standardized commit convention documentation around Conventional Commits.

### Fixed

- Fixed packaging metadata missing Windows classifiers.
- Fixed release notes lacking rollback-risk descriptions.
- Fixed typo in Game DVR registry path documentation.

### Removed

- Removed outdated notes about unsupported Windows 8.1 behavior.

## [1.3.0] - 2026-03-02

### Added

- Added `GameDefinition` dataclass with process name, window title, Steam App ID, installation hint, and notes.
- Added built-in game definitions for Counter-Strike 2, Valorant, Fortnite, Apex Legends, and Overwatch 2.
- Added process-priority application using `psutil`.
- Added safety guard preventing realtime priority selection.

### Changed

- Changed process lookup to use case-insensitive executable-name matching.
- Changed benchmark documentation to require system specs and measurement device details.
- Improved error handling for access-denied process enumeration.

### Fixed

- Fixed crashes when a target game was not running.
- Fixed process enumeration failures caused by short-lived processes.
- Fixed priority reset messaging when a process exits before verification.

### Removed

- Removed experimental thread-priority tuning because it required intrusive process/thread handling.

## [1.2.0] - 2026-02-10

### Added

- Added Game Bar and Game DVR registry policy toggles.
- Added backup entries for HKCU and HKLM registry values.
- Added restore support for values that were originally absent.
- Added administrator warning when HKLM writes are likely to fail.

### Changed

- Changed registry writes to use `CreateKeyEx` with minimal access.
- Improved user-facing warnings for organization-managed policy keys.
- Expanded technical documentation for registry values and security model.

### Fixed

- Fixed restore behavior that previously wrote defaults instead of original values.
- Fixed backup file encoding to always use UTF-8.
- Fixed error messages for missing registry keys.

### Removed

- Removed manual registry-edit instructions from the README in favor of automated restore.

## [1.1.0] - 2026-01-21

### Added

- Added timer-resolution query support.
- Added timer-resolution request and release support.
- Added log file output under the per-user application data directory.
- Added CLI version output.

### Changed

- Changed default timer target to 1 ms expressed as 10,000 units of 100 ns.
- Improved explanation of timer resolution versus clock source selection.
- Improved Windows-only import guards for non-Windows syntax checks.

### Fixed

- Fixed failure path when `ntdll.dll` bindings are unavailable.
- Fixed confusing terminology around minimum and maximum timer-resolution values.
- Fixed application exit code when CLI arguments are invalid.

### Removed

- Removed prototype sleep-loop benchmark because it was not a valid latency measurement.

## [1.0.0] - 2025-12-15

### Added

- Added initial project scaffold.
- Added README with safety model, installation guide, and FAQ.
- Added Tkinter GUI prototype.
- Added configuration file creation with defaults.
- Added MIT license.

### Changed

- No changes; initial release.

### Fixed

- No fixes; initial release.

### Removed

- No removals; initial release.
