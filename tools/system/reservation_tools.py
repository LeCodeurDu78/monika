"""Suivi des réservations réelles effectuées par Monika via le navigateur."""

import datetime

from core.db import db_path, get_connection, init_table

DB_PATH = db_path("reservations.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        provider TEXT,
        scheduled_at TEXT,
        party_size INTEGER,
        contact_name TEXT,
        contact_phone TEXT,
        contact_email TEXT,
        confirmation_reference TEXT,
        source_url TEXT,
        notes TEXT,
        status TEXT NOT NULL DEFAULT 'confirmed',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _parse_scheduled_at(scheduled_at: str) -> datetime.datetime:
    """Parse une date/heure ISO (ex: '2026-09-12T20:00:00')."""
    return datetime.datetime.fromisoformat(scheduled_at.strip())


def _format_row(row: tuple) -> str:
    (
        rid,
        title,
        provider,
        scheduled_at,
        party_size,
        contact_name,
        contact_phone,
        contact_email,
        confirmation_reference,
        source_url,
        notes,
        status,
        created_at,
    ) = row
    parts = [f"#{rid} [{status}] {title}"]
    if provider:
        parts.append(f"chez {provider}")
    if scheduled_at:
        parts.append(f"— {scheduled_at}")
    if party_size:
        parts.append(f"({party_size} pers.)")
    line = " ".join(parts)
    extra = []
    if confirmation_reference:
        extra.append(f"réf. {confirmation_reference}")
    if contact_name or contact_phone or contact_email:
        who = ", ".join(x for x in (contact_name, contact_phone, contact_email) if x)
        extra.append(f"contact : {who}")
    if source_url:
        extra.append(source_url)
    if notes:
        extra.append(notes)
    if extra:
        line += "\n    " + " | ".join(extra)
    return line


def reservation_control(
    action: str,
    title: str = "",
    provider: str = "",
    scheduled_at: str = "",
    party_size: int = 0,
    contact_name: str = "",
    contact_phone: str = "",
    contact_email: str = "",
    confirmation_reference: str = "",
    source_url: str = "",
    notes: str = "",
    duration_minutes: int = 120,
    add_to_calendar: bool = False,
    add_reminder: bool = False,
    reminder_minutes_before: int = 120,
    reservation_id: int = 0,
    limit: int = 10,
) -> str:
    """Gère l'archivage local des réservations web réellement effectuées par Monika."""
    _init_db()

    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "save":
                if not title.strip():
                    return "❌ Paramètre 'title' requis (ex: 'Table chez Le Petit Zinc')."
                parsed_dt = None
                if scheduled_at:
                    try:
                        parsed_dt = _parse_scheduled_at(scheduled_at)
                    except ValueError:
                        return (
                            f"❌ '{scheduled_at}' n'est pas une date/heure ISO valide "
                            "(ex: '2026-09-12T20:00:00')."
                        )

                cursor.execute(
                    """INSERT INTO reservations
                       (title, provider, scheduled_at, party_size, contact_name,
                        contact_phone, contact_email, confirmation_reference,
                        source_url, notes, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')""",
                    (
                        title.strip(),
                        provider.strip() or None,
                        parsed_dt.isoformat() if parsed_dt else None,
                        party_size or None,
                        contact_name.strip() or None,
                        contact_phone.strip() or None,
                        contact_email.strip() or None,
                        confirmation_reference.strip() or None,
                        source_url.strip() or None,
                        notes.strip() or None,
                    ),
                )
                conn.commit()
                new_id = cursor.lastrowid

                summary_lines = [f"✅ Réservation #{new_id} enregistrée : « {title.strip()} »"]
                if provider:
                    summary_lines.append(f"   Prestataire : {provider}")
                if scheduled_at:
                    summary_lines.append(f"   Date/heure : {scheduled_at}")
                if party_size:
                    summary_lines.append(f"   Personnes : {party_size}")
                if confirmation_reference:
                    summary_lines.append(f"   Référence de confirmation : {confirmation_reference}")

                # Ajout optionnel au calendrier
                if add_to_calendar:
                    if not parsed_dt:
                        summary_lines.append(
                            "   ⚠️ Impossible d'ajouter au calendrier : 'scheduled_at' manquant."
                        )
                    else:
                        try:
                            from tools.social.calendar_tools import calendar_control

                            end_dt = parsed_dt + datetime.timedelta(minutes=duration_minutes)
                            cal_result = calendar_control(
                                action="add",
                                summary=title.strip(),
                                start_time=parsed_dt.isoformat(),
                                end_time=end_dt.isoformat(),
                                location=provider.strip() or None,
                            )
                            summary_lines.append(f"   📅 Calendrier : {cal_result}")
                        except Exception as e:
                            summary_lines.append(f"   ⚠️ Échec de l'ajout au calendrier : {e}")

                # Ajout optionnel d'un rappel avant l'échéance
                if add_reminder:
                    if not parsed_dt:
                        summary_lines.append(
                            "   ⚠️ Impossible de créer un rappel : 'scheduled_at' manquant."
                        )
                    else:
                        try:
                            from tools.utils.reminder_tools import reminder_control

                            due_at = parsed_dt - datetime.timedelta(minutes=reminder_minutes_before)
                            rem_message = f"Réservation à venir : {title.strip()}"
                            if provider:
                                rem_message += f" ({provider})"
                            rem_result = reminder_control(
                                action="add",
                                message=rem_message,
                                due_at=due_at.isoformat(),
                            )
                            summary_lines.append(f"   ⏰ Rappel : {rem_result}")
                        except Exception as e:
                            summary_lines.append(f"   ⚠️ Échec de la création du rappel : {e}")

                return "\n".join(summary_lines)

            elif action == "list":
                cursor.execute(
                    """SELECT id, title, provider, scheduled_at, party_size, contact_name,
                              contact_phone, contact_email, confirmation_reference,
                              source_url, notes, status, created_at
                       FROM reservations
                       ORDER BY COALESCE(scheduled_at, created_at) DESC
                       LIMIT ?""",
                    (limit,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return "Aucune réservation enregistrée."
                return "Réservations enregistrées :\n" + "\n".join(_format_row(r) for r in rows)

            elif action == "get":
                if not reservation_id:
                    return "❌ Paramètre 'reservation_id' requis pour l'action 'get'."
                cursor.execute(
                    """SELECT id, title, provider, scheduled_at, party_size, contact_name,
                              contact_phone, contact_email, confirmation_reference,
                              source_url, notes, status, created_at
                       FROM reservations WHERE id = ?""",
                    (reservation_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return f"❌ Aucune réservation avec l'id {reservation_id}."
                return _format_row(row)

            elif action == "cancel":
                if not reservation_id:
                    return "❌ Paramètre 'reservation_id' requis pour l'action 'cancel'."
                cursor.execute(
                    "UPDATE reservations SET status = 'cancelled' WHERE id = ?",
                    (reservation_id,),
                )
                conn.commit()
                if cursor.rowcount == 0:
                    return f"❌ Aucune réservation avec l'id {reservation_id}."
                return (
                    f"✅ Réservation #{reservation_id} marquée comme annulée localement.\n"
                    "⚠️ Ceci ne fait qu'annuler l'enregistrement local : si une annulation "
                    "est nécessaire côté prestataire, il faut la faire via le navigateur "
                    "(browser_control) ou en contactant le prestataire."
                )

            elif action == "delete":
                if not reservation_id:
                    return "❌ Paramètre 'reservation_id' requis pour l'action 'delete'."
                cursor.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
                conn.commit()
                if cursor.rowcount == 0:
                    return f"❌ Aucune réservation avec l'id {reservation_id}."
                return f"✅ Réservation #{reservation_id} supprimée de l'historique local."

            return f"❌ Action inconnue : '{action}'."
    except Exception as e:
        return f"❌ Erreur base de données réservations : {e}"
