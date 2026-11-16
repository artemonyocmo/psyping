import asyncio
import base64
import subprocess
from typing import Dict, Any, Tuple, Optional
from .base import BaseChannel

class DesktopToastChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "desktop_toast"

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        try:
            # Escape single quotes for PowerShell
            safe_title = f"PsyPing • {category.capitalize()}".replace("'", "''")
            safe_text = text.replace("'", "''")
            
            # PowerShell WinRT Toast script with audio sound
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $nodes = $template.GetElementsByTagName('text')
            $nodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null
            $nodes.Item(1).AppendChild($template.CreateTextNode('{safe_text}')) | Out-Null
            
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe')
            $notifier.Show($toast)
            """
            
            # Encode script as UTF-16LE base64 to ensure 100% Cyrillic safety
            script_bytes = ps_script.encode("utf-16le")
            b64_cmd = base64.b64encode(script_bytes).decode("ascii")
            
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-EncodedCommand", b64_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                return True, None
            else:
                err = stderr.decode("utf-8", errors="replace").strip()
                return False, f"PowerShell Toast failed (code {proc.returncode}): {err}"
        except Exception as e:
            return False, f"Desktop toast exception: {str(e)}"
