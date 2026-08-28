"""Intégration avec le planificateur natif de l'OS."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _wake_command() -> list[str]:
    return [sys.executable, "-m", "core.wake_runner"]


def register_once(trigger_id: str, run_at: datetime, kind: str, ref_id: int = 0) -> None:
    """Enregistre un déclenchement natif PONCTUEL à `run_at` (rappel ou tâche planifiée 'once')."""
    try:
        _systemd_register(trigger_id, kind, ref_id, run_at=run_at)
    except Exception as e:
        print(f"⚠️ [native_scheduler] Échec de l'enregistrement natif ponctuel « {trigger_id} » : {e}")


def register_daily(trigger_id: str, time_of_day: str, kind: str, ref_id: int = 0) -> None:
    """Enregistre (idempotent) un déclenchement natif QUOTIDIEN à `time_of_day` ('HH:MM')."""
    try:
        _systemd_register(trigger_id, kind, ref_id, time_of_day=time_of_day)
    except Exception as e:
        print(f"⚠️ [native_scheduler] Échec de l'enregistrement natif quotidien « {trigger_id} » : {e}")


def unregister(trigger_id: str) -> None:
    """Retire un déclenchement natif précédemment enregistré (silencieux si absent)."""
    try:
        _systemd_unregister(trigger_id)
    except Exception as e:
        print(f"⚠️ [native_scheduler] Échec du retrait natif « {trigger_id} » : {e}")


# --- Linux : systemd --user (service + timer) ---------------------------------------------------

def _systemd_dir() -> Path:
    d = Path.home() / ".config" / "systemd" / "user"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _systemd_unit_name(trigger_id: str) -> str:
    return f"monika-{trigger_id}"


def _systemd_register(
    trigger_id: str, kind: str, ref_id: int, run_at: datetime | None = None, time_of_day: str | None = None
) -> None:
    unit = _systemd_unit_name(trigger_id)
    d = _systemd_dir()
    exec_start = subprocess.list2cmdline([*_wake_command(), "--kind", kind, "--id", str(ref_id)])

    service_content = (
        "[Unit]\n"
        f"Description=Monika - reveil natif ({trigger_id})\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={exec_start}\n"
        f"WorkingDirectory={PROJECT_ROOT}\n"
    )
    (d / f"{unit}.service").write_text(service_content)

    if run_at is not None:
        on_calendar = run_at.strftime("%Y-%m-%d %H:%M:%S")
        persistent = "false"
    else:
        on_calendar = f"*-*-* {time_of_day}:00"
        persistent = "true"

    timer_content = (
        "[Unit]\n"
        f"Description=Monika - minuterie native ({trigger_id})\n\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        f"Persistent={persistent}\n"
        f"Unit={unit}.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    (d / f"{unit}.timer").write_text(timer_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{unit}.timer"], check=True, capture_output=True)


def _systemd_unregister(trigger_id: str) -> None:
    unit = _systemd_unit_name(trigger_id)
    d = _systemd_dir()
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{unit}.timer"], check=False, capture_output=True)
    for suffix in (".timer", ".service"):
        p = d / f"{unit}{suffix}"
        if p.exists():
            p.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)