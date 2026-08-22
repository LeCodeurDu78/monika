"""Envoi de messages WhatsApp fiables via Playwright."""

from urllib.parse import quote
from config import APP_DIR
from playwright.sync_api import sync_playwright
from tools.social.contact_tools import get_phone_by_name

SESSION_DIR = str(APP_DIR / ".monika_whatsapp_session")


def send_whatsapp_message(recipient: str, message: str) -> str:
    """Envoie un message WhatsApp de manière déterministe."""
    try:
        target = recipient.strip()
        phone_number = target if target.startswith("+") else get_phone_by_name(target)

        if not phone_number:
            return f"❌ Erreur : Le contact '{target}' est introuvable."

        clean_phone = phone_number.replace("+", "").replace(" ", "")
        url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={quote(message)}"

        with sync_playwright() as p:
            context = p.firefox.launch_persistent_context(
                user_data_dir=SESSION_DIR, headless=True, args=["--start-maximized"]
            )
            page = context.new_page()
            page.goto(url)

            print("⏳ Attente du chargement de WhatsApp Web...")
            send_button_selector = 'button[aria-label="Envoyer"], button[aria-label="Send"]'
            page.wait_for_selector(send_button_selector, timeout=30000)
            page.click(send_button_selector)
            page.wait_for_timeout(2000)
            context.close()

        return f"✅ Message WhatsApp envoyé avec succès à {target} ({phone_number}) !"

    except Exception as e:
        return f"❌ Échec de l'envoi WhatsApp : {str(e)}"
