"""
tools/social/contact_tools.py
------------------------------
Gestionnaire de carnet d'adresses pour Monika.
"""

import os
import json

CONTACTS_FILE = os.path.expanduser("~/.config/monika/contacts.json")


def _load_contacts() -> dict:
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_contacts(contacts: dict):
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)


def manage_contacts(action: str, name: str = "", phone_number: str = "") -> str:
    """Gère le carnet d'adresses de Monika.

    Args:
        action: 'add' (ajouter/modifier), 'get' (chercher), 'list' (tout afficher), 'delete' (supprimer).
        name: Le nom du contact (ex: 'Adam', 'Maman', 'Paul').
        phone_number: Le numéro au format international (ex: '+33612345678').
    """
    contacts = _load_contacts()
    clean_name = name.strip().lower()

    if action == "add":
        if not name or not phone_number:
            return "❌ Veuillez fournir un nom et un numéro au format international (+33...)."

        num = phone_number.strip()
        if not num.startswith("+"):
            return "❌ Le numéro doit commencer par '+' et inclure l'indicatif (ex: '+33612345678')."

        contacts[clean_name] = {
            "display_name": name.strip(),
            "phone": num
        }
        _save_contacts(contacts)
        return f"✅ Contact '{name.strip()}' enregistré avec le numéro {num} !"

    elif action == "get":
        if clean_name in contacts:
            c = contacts[clean_name]
            return f"📱 Contact trouvé : {c['display_name']} -> {c['phone']}"
        return f"❌ Aucun contact trouvé pour '{name}'."

    elif action == "list":
        if not contacts:
            return "📖 Le carnet d'adresses est vide."
        res = ["📖 **Carnet d'adresses :**"]
        for c in contacts.values():
            res.append(f"- **{c['display_name']}** : {c['phone']}")
        return "\n".join(res)

    elif action == "delete":
        if clean_name in contacts:
            del contacts[clean_name]
            _save_contacts(contacts)
            return f"🗑️ Contact '{name}' supprimé."
        return f"❌ Contact '{name}' introuvable."

    return "❌ Action inconnue. Actions valides : 'add', 'get', 'list', 'delete'."


def get_phone_by_name(name: str) -> str:
    """Récupère un numéro à partir d'un nom, avec correspondance partielle en repli."""
    contacts = _load_contacts()
    clean_name = name.strip().lower()
    if clean_name in contacts:
        return contacts[clean_name]["phone"]

    for key, data in contacts.items():
        if clean_name in key:
            return data["phone"]

    return ""