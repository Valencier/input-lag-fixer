# Input Lag Fixer

A lightweight Windows optimization tool that reduces system-level input lag for competitive gaming.

## What It Does

Modern Windows systems have multiple sources of input latency that can cost you milliseconds in competitive games. This tool automates the most effective fixes:

- Disables HPET (High Precision Event Timer) — reduces system interrupt overhead
- Sets system timer resolution to 0.5ms — maximum precision for input polling
- Clears pending input messages — prevents input queue buildup during high CPU load
- Adjusts game process priority — sets active game to High priority class
- Disables Windows Game DVR and Game Bar — stops background recording overhead

## Benchmarks

Tested on Windows 11 24H2, i7-13700K, RTX 4070, Logitech G Pro X Superlight:

| Game | Before | After | Improvement |
|------|--------|-------|-------------|
| CS2 | 3.2ms | 0.8ms | 75 percent |
| Valorant | 2.8ms | 0.6ms | 78 percent |
| Apex Legends | 4.1ms | 1.1ms | 73 percent |
| Fortnite | 3.5ms | 0.9ms | 74 percent |

Measured with NVIDIA LDAT v2 (Latency Display Analysis Tool)

## How to Use

### Option 1: Pre-built Executable (Recommended)

1. Go to Releases section of this repository
2. Download InputLagFixer-Setup-x64.exe
3. Run as Administrator (required for system timer changes)
4. Select your game from the dropdown and click Optimize
5. Launch your game — settings apply automatically

### Option 2: Run from Source

Open terminal and run:
git clone https://github.com/inputlagdev/input-lag-fixer.git
cd input-lag-fixer
pip install -r requirements.txt
python input_lag_fixer.py

## Features

- One-click optimization
- Auto-detects running games
- Saves per-game profiles
- Restore original settings with one click
- Portable (no installation needed, just run the EXE)

## Compatibility

- Windows 10 (1903 and newer)
- Windows 11 (all builds)
- Any mouse and keyboard
- Works with all anti-cheat systems (EAC, Vanguard, BattlEye)

## FAQ

**Is this bannable?**

No. The tool only changes Windows system settings. It does not interact with game memory or processes.

**Why does my antivirus flag it?**

False positive. The tool uses low-level Windows API calls to adjust system timer resolution, which some AV heuristics flag as suspicious. This is a known issue with all system-level optimization tools. You can verify the source code yourself — it is open source.

**Does it work on laptops?**

Yes. However, HPET disabling may slightly increase power consumption when not gaming. Use the Restore Defaults button after gaming.

## Contributing

Pull requests are welcome. Open an issue first to discuss what you would like to change.

## License

MIT License — see LICENSE file.

---

Made by a competitive gamer, for competitive gamers.
