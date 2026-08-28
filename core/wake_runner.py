"""Point d'entrée invoqué par le planificateur natif de l'OS."""

import argparse

from core.wake_store import main_process_is_alive


def main() -> None:
    parser = argparse.ArgumentParser(description="Réveil ponctuel de Monika (planificateur natif de l'OS).")
    parser.add_argument("--kind", required=True, choices=["reminder", "task", "briefing"])
    parser.add_argument("--id", type=int, default=0)
    args = parser.parse_args()

    if main_process_is_alive():
        return

    from core.wake_handlers import handle_wake

    handle_wake(args.kind, args.id)


if __name__ == "__main__":
    main()
