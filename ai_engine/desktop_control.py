import os
import subprocess
import ctypes
import re
from typing import Dict, Any, Tuple, Optional

# Windows Virtual Key Codes for Volume and Media Control
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

def send_virtual_key(vk_code: int):
    """Simulate Windows media key press using User32 keybd_event API."""
    try:
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[DESKTOP CONTROL ERROR] Virtual key send failed: {e}")
        return False

class DesktopActionService:
    """
    Desktop Action & System Automation Service for AIGIS.
    Allows opening authorized applications, folders, controlling volume & media, locking workstation, and sleeping.
    Mandates explicit confirmation for destructive actions (Shutdown, Restart, System modification).
    """

    ALLOWED_APPS = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "file manager": "explorer.exe",
        "vs code": "code",
        "vscode": "code",
        "code": "code",
        "spotify": "spotify.exe",
        "chrome": "chrome.exe",
        "browser": "msedge.exe",
        "edge": "msedge.exe",
        "cmd": "cmd.exe",
        "terminal": "wt.exe"
    }

    def __init__(self):
        # Maps session_id -> pending destructive action dict
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}

    def process_natural_command(self, session_id: str, prompt: str) -> Tuple[bool, str, Optional[str]]:
        """
        Interprets natural language prompt for desktop control actions.
        Returns: (handled_flag, reply_text, provider_name)
        """
        p = prompt.strip().lower()

        # 1. Check for Pending Confirmation Resolution first
        if session_id in self.pending_confirmations:
            pending = self.pending_confirmations[session_id]
            if any(confirm_kw in p for confirm_kw in ["confirm", "yes", "proceed", "do it", "sure", "ok"]):
                action_type = pending.get("action")
                del self.pending_confirmations[session_id]
                return self._execute_confirmed_action(action_type)
            elif any(cancel_kw in p for cancel_kw in ["cancel", "no", "abort", "stop", "don't"]):
                del self.pending_confirmations[session_id]
                return True, "Action cancelled, sir. Your system state remains unchanged.", "Desktop Control -> Action Cancelled"
            else:
                return True, f"Confirmation pending for action '{pending.get('action')}'. Reply 'CONFIRM' to proceed, or 'CANCEL' to abort, sir.", "Desktop Control -> Awaiting Confirmation"

        # 2. Check for Destructive / System Modifying Actions (Shutdown, Restart)
        if any(kw in p for kw in ["shutdown", "shut down", "turn off pc", "turn off computer"]):
            self.pending_confirmations[session_id] = {"action": "shutdown"}
            return True, "Are you sure you want to SHUTDOWN your workstation, sir? Reply CONFIRM to proceed or CANCEL to abort.", "Desktop Control -> Safety Interceptor"

        if any(kw in p for kw in ["restart", "reboot", "restart pc", "restart computer"]):
            self.pending_confirmations[session_id] = {"action": "restart"}
            return True, "Are you sure you want to RESTART your workstation, sir? Reply CONFIRM to proceed or CANCEL to abort.", "Desktop Control -> Safety Interceptor"

        # 3. Safe System Power States (Lock, Sleep)
        if any(kw in p for kw in ["lock workstation", "lock computer", "lock pc", "lock screen"]):
            return self.lock_workstation()

        if any(kw in p for kw in ["sleep pc", "sleep computer", "put pc to sleep", "suspend pc"]):
            return self.sleep_workstation()

        # 4. Volume Controls
        if "mute" in p:
            send_virtual_key(VK_VOLUME_MUTE)
            return True, "Volume muted, sir.", "Desktop Control -> Volume"
        elif "volume up" in p or "increase volume" in p or "louder" in p:
            for _ in range(5):
                send_virtual_key(VK_VOLUME_UP)
            return True, "Volume increased, sir.", "Desktop Control -> Volume"
        elif "volume down" in p or "decrease volume" in p or "lower volume" in p:
            for _ in range(5):
                send_virtual_key(VK_VOLUME_DOWN)
            return True, "Volume decreased, sir.", "Desktop Control -> Volume"

        # 5. Media Controls
        if any(kw in p for kw in ["play media", "pause media", "play music", "pause music", "toggle media"]):
            send_virtual_key(VK_MEDIA_PLAY_PAUSE)
            return True, "Media playback toggled, sir.", "Desktop Control -> Media"
        elif any(kw in p for kw in ["next track", "next song", "skip song"]):
            send_virtual_key(VK_MEDIA_NEXT_TRACK)
            return True, "Skipped to next track, sir.", "Desktop Control -> Media"
        elif any(kw in p for kw in ["previous track", "prev song", "previous song"]):
            send_virtual_key(VK_MEDIA_PREV_TRACK)
            return True, "Returned to previous track, sir.", "Desktop Control -> Media"

        # 6. Application Launching
        if p.startswith("open ") or p.startswith("launch ") or p.startswith("start "):
            target = re.sub(r"^(open|launch|start)\s+", "", p).strip()
            for app_key, app_binary in self.ALLOWED_APPS.items():
                if app_key in target:
                    return self.launch_app(app_key, app_binary)

            # Check if user is asking to open a specific folder
            if "folder" in target or "directory" in target or any(dir_kw in target for dir_kw in ["downloads", "documents", "desktop", "c drive"]):
                return self.open_folder_by_name(target)

        return False, "", None

    def _execute_confirmed_action(self, action_type: str) -> Tuple[bool, str, str]:
        """Executes a destructive action ONLY after explicit user confirmation."""
        try:
            if action_type == "shutdown":
                subprocess.Popen(["shutdown", "/s", "/t", "5"])
                return True, "Initiating system shutdown in 5 seconds, sir. Goodbye.", "Desktop Control -> Confirmed Action"
            elif action_type == "restart":
                subprocess.Popen(["shutdown", "/r", "/t", "5"])
                return True, "Initiating system restart in 5 seconds, sir.", "Desktop Control -> Confirmed Action"
        except Exception as e:
            return True, f"Failed to execute confirmed action: {e}", "Desktop Control -> Error"
        return False, "", ""

    def launch_app(self, app_name: str, binary_name: str) -> Tuple[bool, str, str]:
        """Launches an authorized Windows desktop application."""
        try:
            subprocess.Popen([binary_name], shell=True)
            return True, f"Opening {app_name.capitalize()}, sir.", "Desktop Control -> App Launcher"
        except Exception as e:
            return True, f"Could not launch {app_name}: {e}", "Desktop Control -> Error"

    def open_folder_by_name(self, folder_name: str) -> Tuple[bool, str, str]:
        """Opens common user folders in Windows Explorer."""
        user_profile = os.environ.get("USERPROFILE", "C:\\Users")
        target_path = None

        if "download" in folder_name:
            target_path = os.path.join(user_profile, "Downloads")
        elif "document" in folder_name:
            target_path = os.path.join(user_profile, "Documents")
        elif "desktop" in folder_name:
            target_path = os.path.join(user_profile, "Desktop")
        elif "c drive" in folder_name:
            target_path = "C:\\"

        if target_path and os.path.exists(target_path):
            try:
                subprocess.Popen(["explorer.exe", target_path])
                return True, f"Opening folder {target_path}, sir.", "Desktop Control -> Folder Explorer"
            except Exception as e:
                return True, f"Could not open directory: {e}", "Desktop Control -> Error"

        return False, "", ""

    def lock_workstation(self) -> Tuple[bool, str, str]:
        """Locks the Windows user session."""
        try:
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
            return True, "Locking workstation now, sir.", "Desktop Control -> Security"
        except Exception as e:
            return True, f"Failed to lock workstation: {e}", "Desktop Control -> Error"

    def sleep_workstation(self) -> Tuple[bool, str, str]:
        """Puts workstation into sleep mode."""
        try:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return True, "Entering sleep mode, sir.", "Desktop Control -> System Power"
        except Exception as e:
            return True, f"Failed to enter sleep mode: {e}", "Desktop Control -> Error"
