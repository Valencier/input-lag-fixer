# Contributing to Input Lag Fixer

Thank you for considering a contribution. This project is intentionally conservative: safety, transparency, rollback, and reproducible benchmarking matter more than aggressive tweaks.

## Code of Conduct

By participating, you agree to use respectful, technical, and good-faith communication. Harassment, discriminatory language, threats, or requests for anti-cheat bypasses are not welcome.

## Reporting Bugs

Open a GitHub issue with the following information:

1. Input Lag Fixer version.
2. Windows version and build number.
3. CPU, GPU, motherboard, and mouse polling rate.
4. Whether the tool was run as administrator.
5. Exact action taken: GUI or CLI command.
6. Expected result.
7. Actual result.
8. Relevant log excerpt from `%APPDATA%\InputLagFixer\logs\input_lag_fixer.log`.
9. Whether restore was attempted and whether it succeeded.

Do not include secrets, account tokens, full user-profile paths containing private names if avoidable, or unrelated crash dumps.

## Suggesting Features

Feature requests should include:

- The exact Windows setting or API involved.
- Whether the change is reversible.
- Whether administrator rights are required.
- Known anti-cheat or platform-policy considerations.
- A proposed test plan.
- Links to official Microsoft documentation when possible.

Feature requests for the following will be closed:

- anti-cheat bypasses
- hidden execution
- disabling antivirus
- kernel driver installation
- hardware-ID spoofing
- game memory patching
- realtime priority defaults

## Development Environment Setup

Use Windows 10 22H2 or Windows 11 22H2+ for runtime testing.

```powershell
git clone https://github.com/example/input-lag-fixer.git
cd input-lag-fixer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python input_lag_fixer.py --run-tests
```

On non-Windows systems, only syntax checks and platform-neutral unit tests are expected to pass.

## Code Style Guide

- Follow PEP 8.
- Use type hints on every function.
- Use Google-style docstrings for public functions and classes.
- Prefer dataclasses for structured application state.
- Keep Windows API wrappers small, explicit, and documented.
- Use `pathlib.Path` instead of string path manipulation.
- Use the project logger instead of `print`, except in CLI output helpers.
- Avoid broad `except Exception` unless the exception is logged and a user-safe result is returned.
- Do not add network access without a separate design discussion.

## Commit Message Conventions

Use Conventional Commits:

```text
feat: add custom game validation
fix: restore absent registry values correctly
docs: explain NtSetTimerResolution units
test: add config validation tests
build: update PyInstaller workflow
refactor: split registry backup serialization
```

Allowed common types:

- `feat`
- `fix`
- `docs`
- `test`
- `build`
- `ci`
- `refactor`
- `chore`

## Pull Request Process

1. Open or reference an issue.
2. Keep the PR focused on one behavior change.
3. Add tests for platform-neutral logic.
4. Add manual Windows test notes for Windows-only logic.
5. Update `README.md`, `docs/TECHNICAL.md`, or `CHANGELOG.md` when behavior changes.
6. Confirm restore behavior for any setting you add.
7. Include screenshots for GUI changes.

## Testing Requirements

Run:

```powershell
python input_lag_fixer.py --run-tests
python -m py_compile input_lag_fixer.py setup.py
```

Recommended optional checks:

```powershell
ruff check .
black --check .
mypy input_lag_fixer.py
```

For Windows behavior changes, include manual test notes:

- Was the process elevated?
- Which registry keys changed?
- Was a backup written?
- Did restore return the exact original values?
- Were logs clear enough for troubleshooting?
