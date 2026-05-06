#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setuptools configuration for Input Lag Fixer."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from setuptools import setup
from setuptools.command.install import install


ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"
REQUIREMENTS = ROOT / "requirements.txt"


def read_long_description() -> str:
    """Read README.md for the package long description."""
    return README.read_text(encoding="utf-8") if README.exists() else ""


def read_install_requirements() -> List[str]:
    """Parse runtime requirements from requirements.txt.

    Development-only dependencies are intentionally excluded from install_requires.
    """
    if not REQUIREMENTS.exists():
        return ["psutil>=5.9.8"]
    requirements: List[str] = []
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        package_name = line.split(">=")[0].lower()
        if package_name in {"pyinstaller", "black", "ruff", "mypy"}:
            continue
        requirements.append(line)
    return requirements


class WindowsShortcutInstallCommand(install):
    """Custom install command that attempts to create a Windows desktop shortcut."""

    description = "install package and create a Windows desktop shortcut when possible"

    def run(self) -> None:
        """Run normal installation and then create a shortcut on Windows."""
        super().run()
        if os.name != "nt":
            return
        try:
            self._create_shortcut()
        except Exception as exc:  # pragma: no cover - depends on Windows shell COM.
            print(f"warning: could not create desktop shortcut: {exc}", file=sys.stderr)

    def _create_shortcut(self) -> None:
        """Create a desktop shortcut using Windows Script Host COM automation."""
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError:
            print("warning: pywin32 is not installed; skipping desktop shortcut", file=sys.stderr)
            return
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        shortcut_path = desktop / "Input Lag Fixer.lnk"
        python_exe = Path(sys.executable)
        script = ROOT / "input_lag_fixer.py"
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = str(python_exe)
        shortcut.Arguments = f'"{script}"'
        shortcut.WorkingDirectory = str(ROOT)
        shortcut.IconLocation = str(python_exe)
        shortcut.Description = "Input Lag Fixer"
        shortcut.save()


setup(
    name="input-lag-fixer",
    version="2.1.0",
    author="Input Lag Fixer contributors",
    author_email="maintainers@example.invalid",
    description="Transparent Windows latency tuning utility for competitive benchmark sessions.",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/example/input-lag-fixer",
    project_urls={
        "Documentation": "https://github.com/example/input-lag-fixer/blob/main/docs/TECHNICAL.md",
        "Source": "https://github.com/example/input-lag-fixer",
        "Issues": "https://github.com/example/input-lag-fixer/issues",
    },
    license="MIT",
    py_modules=["input_lag_fixer"],
    include_package_data=True,
    install_requires=read_install_requirements(),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "input-lag-fixer=input_lag_fixer:main",
        ],
    },
    cmdclass={"install": WindowsShortcutInstallCommand},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Win32 (MS Windows)",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: Microsoft :: Windows :: Windows 11",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
    keywords=[
        "windows",
        "latency",
        "timer-resolution",
        "game-dvr",
        "competitive-gaming",
        "benchmarking",
    ],
)
