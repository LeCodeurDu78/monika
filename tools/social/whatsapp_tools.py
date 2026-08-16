"""
tools/whatsapp_tools.py
-----------------------
Envoi de messages WhatsApp fiables via Playwright.
"""

import os
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from tools.social.contact_tools import get_phone_by_name

# Dossier où Playwright va stocker les cookies de session WhatsApp
SESSION_DIR = os.path.expanduser("~/.config/monika/.monika_whatsapp_session")


def send_whatsapp_message(recipient: str, message: str) -> str:
    """Envoie un message WhatsApp de manière déterministe."""
    try:
        target = recipient.strip()
        phone_number = target if target.startswith("+") else get_phone_by_name(target)

        if not phone_number:
            return f"❌ Erreur : Le contact '{target}' est introuvable."

        # Nettoyage du numéro
        clean_phone = phone_number.replace("+", "").replace(" ", "")
        url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={quote(message)}"

        with sync_playwright() as p:
            # Lancement d'un navigateur Firefox persistant
            context = p.firefox.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=True,  # Mettre à True si vous souhaitez que ce soit 100% invisible
                args=["--start-maximized"]
            )
            page = context.new_page()
            page.goto(url)

            # Attente explicite de l'apparition du bouton 'Envoyer' (icône d'envoi)
            print("⏳ Attente du chargement de WhatsApp Web...")

            # Selector pour le bouton d'envoi de WhatsApp Web
            send_button_selector = 'button[aria-label="Envoyer"], button[aria-label="Send"]'

            # Attend jusqu'à 30 secondes que le bouton d'envoi soit prêt
            page.wait_for_selector(send_button_selector, timeout=30000)

            # Clic direct sur le bouton
            page.click(send_button_selector)

            # Petite pause pour s'assurer que le paquet réseau est parti
            page.wait_for_timeout(2000)
            context.close()

        return f"✅ Message WhatsApp envoyé avec succès à {target} ({phone_number}) !"

    except Exception as e:
        return f"❌ Échec de l'envoi WhatsApp : {str(e)}"