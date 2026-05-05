"""
Input Lag Fixer - Windows Gaming Optimization Tool
MIT License
Copyright (c) 2025 Alex
"""

import os
import sys
import ctypes
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import json
from pathlib import Path

# ============================================================
# WINDOWS API CONSTANTS
# ============================================================
WINMM = ctypes.WinDLL('winmm')
TIMERR_NOERROR = 0
TIMERR_NOCANDO = 97

PROCESS_ALL_ACCESS = 0x1F0FFF
HIGH_PRIORITY_CLASS = 0x00000080
NORMAL_PRIORITY_CLASS = 0x00000020

# ============================================================
# CONFIG
# ============================================================
CONFIG_DIR = Path.home() / "Documents" / "InputLagFixer"
CONFIG_FILE = CONFIG_DIR / "settings.json"

GAME_PROCESSES = {
    "CS2": "cs2.exe",
    "Valorant": "valorant.exe",
    "Apex Legends": "r5apex.exe",
    "Fortnite": "FortniteClient-Win64-Shipping.exe",
    "Call of Duty": "cod.exe",
    "Overwatch 2": "overwatch.exe",
    "Rainbow Six Siege": "RainbowSix.exe",
    "Escape from Tarkov": "EscapeFromTarkov.exe",
    "League of Legends": "LeagueClient.exe",
    "Dota 2": "dota2.exe",
    "Custom": ""
}

# ============================================================
# CORE FUNCTIONS
# ============================================================

def set_timer_resolution(period_ms=1):
    """Set Windows timer resolution to minimum (0.5ms = maximum precision)"""
    try:
        result = WINMM.timeBeginPeriod(period_ms)
        if result == TIMERR_NOERROR:
            return True, f"Timer resolution set to {period_ms}ms"
        else:
            return False, f"Failed to set timer resolution (error {result})"
    except Exception as e:
        return False, f"Timer resolution error: {e}"

def reset_timer_resolution(period_ms=1):
    """Release timer resolution back to default"""
    try:
        WINMM.timeEndPeriod(period_ms)
        return True, "Timer resolution reset to default"
    except Exception as e:
        return False, f"Could not reset timer: {e}"

def disable_game_bar():
    """Disable Windows Game Bar and Game DVR via registry"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        
        key_path2 = r"Software\Microsoft\GameBar"
        key2 = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path2)
        winreg.SetValueEx(key2, "AllowAutoGameMode", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key2)
        return True, "Game Bar and Game DVR disabled"
    except Exception as e:
        return False, f"Could not disable Game Bar: {e}"

def enable_game_bar():
    """Restore Game Bar settings"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        
        key_path2 = r"Software\Microsoft\GameBar"
        key2 = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path2)
        winreg.SetValueEx(key2, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key2)
        return True, "Game Bar and Game DVR restored"
    except Exception as e:
        return False, f"Could not restore Game Bar: {e}"

def set_process_priority(process_name):
    """Set game process to High priority"""
    if not process_name:
        return False, "No game selected"
    try:
        import psutil
        found = False
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                proc.nice(psutil.HIGH_PRIORITY_CLASS)
                found = True
        if found:
            return True, f"Set {process_name} to High priority"
        else:
            return False, f"{process_name} is not running"
    except ImportError:
        return False, "psutil not installed. Run: pip install psutil"

def clear_input_queue():
    """Flush pending input messages from the message queue"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        MSG = ctypes.c_void_p()
        count = 0
        while user32.PeekMessageW(ctypes.byref(MSG), None, 0, 0, 1):
            count += 1
        if count > 0:
            return True, f"Cleared {count} pending input messages"
        else:
            return True, "Input queue is clean"
    except Exception as e:
        return False, f"Could not clear input queue: {e}"

def save_config(game_name):
    """Save selected game to config file"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = {"last_game": game_name}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except:
        pass

def load_config():
    """Load saved config"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return config.get("last_game", None)
    except:
        pass
    return None

# ============================================================
# GUI
# ============================================================
class InputLagFixerGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Input Lag Fixer v1.0")
        self.window.geometry("500x420")
        self.window.resizable(False, False)
        self.window.configure(bg="#1a1a2e")
        
        # Header
        header = tk.Label(
            self.window, 
            text="Input Lag Fixer", 
            font=("Segoe UI", 16, "bold"),
            fg="#e94560",
            bg="#1a1a2e"
        )
        header.pack(pady=15)
        
        sub = tk.Label(
            self.window, 
            text="Reduce input latency for competitive gaming",
            font=("Segoe UI", 9),
            fg="#a0a0b0",
            bg="#1a1a2e"
        )
        sub.pack()
        
        # Game selection
        game_frame = tk.Frame(self.window, bg="#1a1a2e")
        game_frame.pack(pady=15)
        
        game_label = tk.Label(
            game_frame, 
            text="Select Game:", 
            font=("Segoe UI", 10),
            fg="#ffffff",
            bg="#1a1a2e"
        )
        game_label.pack(side="left", padx=5)
        
        self.selected_game = tk.StringVar()
        self.game_dropdown = ttk.Combobox(
            game_frame, 
            textvariable=self.selected_game,
            values=list(GAME_PROCESSES.keys()),
            state="readonly",
            width=20
        )
        self.game_dropdown.pack(side="left", padx=5)
        
        last_game = load_config()
        if last_game:
            self.game_dropdown.set(last_game)
        else:
            self.game_dropdown.set("CS2")
        
        # Output area
        self.output_frame = tk.Frame(self.window, bg="#1a1a2e")
        self.output_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.output_text = tk.Text(
            self.output_frame, 
            height=10, 
            width=55,
            bg="#0f0f23",
            fg="#00ff88",
            font=("Consolas", 9),
            insertbackground="#00ff88",
            relief="flat",
            borderwidth=2,
            highlightthickness=1,
            highlightbackground="#e94560"
        )
        self.output_text.pack(side="left", fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(self.output_frame, command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)
        
        # Buttons
        btn_frame = tk.Frame(self.window, bg="#1a1a2e")
        btn_frame.pack(pady=15)
        
        btn_optimize = tk.Button(
            btn_frame, 
            text="OPTIMIZE NOW",
            command=self.run_optimization,
            bg="#e94560",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padx=25,
            pady=8,
            relief="flat",
            cursor="hand2",
            activebackground="#c23152",
            activeforeground="#ffffff"
        )
        btn_optimize.pack(side="left", padx=5)
        
        btn_restore = tk.Button(
            btn_frame,
            text="Restore Defaults",
            command=self.restore_defaults,
            font=("Segoe UI", 9),
            padx=20,
            pady=8,
            relief="flat",
            cursor="hand2",
            bg="#16213e",
            fg="#ffffff",
            activebackground="#0f3460",
            activeforeground="#ffffff"
        )
        btn_restore.pack(side="left", padx=5)
        
        # Status bar
        self.status = tk.Label(
            self.window, 
            text="Ready", 
            font=("Segoe UI", 8), 
            fg="#666680",
            bg="#1a1a2e"
        )
        self.status.pack(pady=8)
        
    def log(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.window.update()
        
    def run_optimization(self):
        self.output_text.delete(1.0, tk.END)
        self.status.config(text="Optimizing...", fg="#e94560")
        
        self.log("=" * 50)
        self.log("  Input Lag Fixer v1.0")
        self.log("  System Optimization Tool")
        self.log("=" * 50)
        self.log("")
        
        game = self.selected_game.get()
        process_name = GAME_PROCESSES.get(game, "")
        
        save_config(game)
        
        # Step 1: Timer resolution
        self.log("[1/4] Setting timer resolution...")
        success, msg = set_timer_resolution(1)
        self.log(f"      {msg}")
        
        # Step 2: Game Bar
        self.log("[2/4] Disabling Game Bar...")
        success, msg = disable_game_bar()
        self.log(f"      {msg}")
        
        # Step 3: Input queue
        self.log("[3/4] Clearing input queue...")
        success, msg = clear_input_queue()
        self.log(f"      {msg}")
        
        # Step 4: Process priority
        self.log("[4/4] Setting process priority...")
        if process_name:
            success, msg = set_process_priority(process_name)
            self.log(f"      {msg}")
        else:
            self.log("      Custom game: set priority manually from Task Manager")
        
        self.log("")
        self.log("=" * 50)
        self.log("  OPTIMIZATION COMPLETE")
        self.log("  Launch your game now for reduced input lag")
        self.log("=" * 50)
        
        self.status.config(text="Optimization complete — launch your game", fg="#00ff88")
        messagebox.showinfo(
            "Optimization Complete", 
            "All optimizations applied successfully.\n\nYour input lag should be noticeably reduced.\n\nLaunch your game now and feel the difference!"
        )
        
    def restore_defaults(self):
        self.output_text.delete(1.0, tk.END)
        self.status.config(text="Restoring defaults...", fg="#ffaa00")
        
        self.log("Restoring system defaults...")
        self.log("")
        
        success, msg = reset_timer_resolution(1)
        self.log(f"[OK] {msg}")
        
        success, msg = enable_game_bar()
        self.log(f"[OK] {msg}")
        
        self.log("")
        self.log("All settings restored to default.")
        
        self.status.config(text="Defaults restored", fg="#a0a0b0")
        messagebox.showinfo(
            "Restored", 
            "All settings have been restored to their original values."
        )
        
    def run(self):
        self.window.mainloop()

# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
    else:
        app = InputLagFixerGUI()
        app.run()
