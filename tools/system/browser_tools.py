"""Contrôle du navigateur pour Monika."""

from pathlib import Path
from core.settings import settings

APP_DIR = settings.APP_DIR
HEADLESS = settings.BROWSER_HEADLESS
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

SESSION_DIR = str(APP_DIR / ".monika_browser_session")
DEFAULT_ACTION_TIMEOUT_MS = 8000
MAX_CONTENT_CHARS = 4000
SNIPPET_CHARS = 300

_playwright = None
_context = None
_active_tab_index = 0


def _ensure_context():
    global _playwright, _context

    if _context is not None:
        try:
            _ = _context.pages
            return _context
        except Exception:
            _context = None

    if _playwright is None:
        _playwright = sync_playwright().start()

    _clear_stale_lock()

    _context = _playwright.firefox.launch_persistent_context(
        user_data_dir=SESSION_DIR,
        headless=HEADLESS,
    )
    if not _context.pages:
        _context.new_page()

    return _context


def _clear_stale_lock():
    """Supprime le verrou de profil Firefox."""
    profile = Path(SESSION_DIR)
    if not profile.exists():
        return
    for lock_name in ("lock", ".parentlock"):
        lock_path = profile / lock_name
        try:
            if lock_path.exists() or lock_path.is_symlink():
                lock_path.unlink()
        except Exception:
            pass


def close_browser() -> str:
    """Ferme explicitement le Firefox géré par Monika."""
    global _playwright, _context
    try:
        if _context is not None:
            _context.close()
        if _playwright is not None:
            _playwright.stop()
        _context = None
        _playwright = None
        return "✅ Navigateur Monika fermé."
    except Exception as e:
        return f"❌ Erreur lors de la fermeture du navigateur : {e}"


def _live_pages() -> list:
    context = _ensure_context()
    return [p for p in context.pages if not p.is_closed()]


def _active_page():
    global _active_tab_index
    pages = _live_pages()
    if not pages:
        context = _ensure_context()
        pages = [context.new_page()]
    if _active_tab_index >= len(pages):
        _active_tab_index = 0
    return pages[_active_tab_index]


def list_tabs() -> str:
    """Liste les onglets actuellement ouverts dans le Firefox de Monika."""
    try:
        pages = _live_pages()
        if not pages:
            return "Aucun onglet ouvert."
        lines = []
        for i, page in enumerate(pages):
            marker = "➡️ " if i == _active_tab_index else "   "
            try:
                title = page.title()
            except Exception:
                title = "(titre indisponible)"
            lines.append(f"{marker}[{i}] {title} — {page.url}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Erreur lors du listage des onglets : {e}"


def switch_tab(tab_id: int) -> str:
    """Bascule l'onglet actif."""
    global _active_tab_index
    try:
        pages = _live_pages()
        if not pages:
            return "Aucun onglet ouvert."
        if tab_id < 0 or tab_id >= len(pages):
            return f"❌ Index d'onglet invalide (valeurs possibles : 0 à {len(pages) - 1})."
        _active_tab_index = tab_id
        page = pages[tab_id]
        try:
            page.bring_to_front()
        except Exception:
            pass
        return f"✅ Onglet actif : [{tab_id}] {page.title()} — {page.url}"
    except Exception as e:
        return f"❌ Erreur lors du changement d'onglet : {e}"


def _snippet(page, max_chars: int = SNIPPET_CHARS) -> str:
    """Aperçu compact du texte visible."""
    try:
        raw_text = page.inner_text("body")
        text = " ".join(raw_text.split())
        truncated = text[:max_chars]
        suffix = "…" if len(text) > max_chars else ""
        return f"{truncated}{suffix}"
    except Exception:
        return "(aperçu indisponible)"


def navigate(url: str) -> str:
    """Navigue vers une URL dans l'onglet actif."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        page = _active_page()
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        return (
            f"✅ Navigation effectuée vers {page.url} (titre : {page.title()}).\n"
            f"Aperçu : {_snippet(page)}"
        )
    except PlaywrightTimeoutError:
        return f"⚠️ Délai dépassé en chargeant '{url}' (la page continue peut-être de charger)."
    except Exception as e:
        return f"❌ Erreur de navigation : {e}"


def read_page_content(full: bool = True) -> str:
    """Extrait le texte visible de l'onglet actif."""
    try:
        page = _active_page()
        if not full:
            return f"[{page.title()} — {page.url}]\n{_snippet(page)}"
        raw_text = page.inner_text("body")
        text = " ".join(raw_text.split())
        truncated = text[:MAX_CONTENT_CHARS]
        suffix = " […contenu tronqué]" if len(text) > MAX_CONTENT_CHARS else ""
        return f"[{page.title()} — {page.url}]\n{truncated}{suffix}"
    except Exception as e:
        return f"❌ Erreur lors de la lecture de la page : {e}"


def list_interactive_elements() -> str:
    """Liste les champs, boutons et liens visibles de l'onglet actif avec leur nom accessible."""
    try:
        page = _active_page()
        elements = page.eval_on_selector_all(
            "input, textarea, button, a[href], select, [role=button], [role=textbox], [role=combobox]",
            """(els) => els.map(el => {
                const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                if (!visible) return null;
                const label = el.getAttribute('aria-label')
                    || el.getAttribute('placeholder')
                    || el.innerText
                    || el.value
                    || el.name
                    || '';
                return {
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    type: el.getAttribute('type') || '',
                    label: label.trim().slice(0, 80)
                };
            }).filter(Boolean)"""
        )
        seen = set()
        lines = []
        for el in elements:
            if not el["label"]:
                continue
            key = (el["tag"], el["label"])
            if key in seen:
                continue
            seen.add(key)
            kind = el["role"] or el["type"] or el["tag"]
            lines.append(f"- [{kind}] \"{el['label']}\"")
            if len(lines) >= 40:
                break
        if not lines:
            return "Aucun élément interactif visible détecté."
        return f"[{page.title()} — {page.url}]\nÉléments détectés :\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ Erreur lors du listage des éléments : {e}"


def _locate(page, description: str):
    """Localise un élément par description."""
    description = description.strip()
    strategies = [
        lambda: page.get_by_role("button", name=description, exact=False),
        lambda: page.get_by_role("link", name=description, exact=False),
        lambda: page.get_by_role("textbox", name=description, exact=False),
        lambda: page.get_by_label(description, exact=False),
        lambda: page.get_by_placeholder(description, exact=False),
        lambda: page.get_by_text(description, exact=False),
    ]
    for strategy in strategies:
        try:
            locator = strategy()
            if locator.count() > 0:
                candidate = locator.first
                candidate.wait_for(state="visible", timeout=1500)
                return candidate
        except Exception:
            continue
    return None


def click_element(description: str) -> str:
    """Clique sur l'élément de l'onglet actif identifié par sa description."""
    try:
        page = _active_page()
        element = _locate(page, description)
        if element is None:
            return f"❌ Élément introuvable pour la description : '{description}'."
        element.click(timeout=DEFAULT_ACTION_TIMEOUT_MS)
        return (
            f"✅ Clic effectué sur l'élément correspondant à '{description}'.\n"
            f"Aperçu après clic : {_snippet(page)}"
        )
    except PlaywrightTimeoutError:
        return f"⚠️ Élément trouvé mais non cliquable dans le délai imparti ('{description}')."
    except Exception as e:
        return f"❌ Erreur lors du clic : {e}"


def fill_field(description: str, text: str) -> str:
    """Remplit le champ de l'onglet actif identifié par sa description."""
    try:
        page = _active_page()
        element = _locate(page, description)
        if element is None:
            return f"❌ Champ introuvable pour la description : '{description}'."
        element.fill(text, timeout=DEFAULT_ACTION_TIMEOUT_MS)
        return f"✅ Champ '{description}' rempli."  # pas d'aperçu ici : remplir un champ ne change quasi jamais la page visible
    except PlaywrightTimeoutError:
        return f"⚠️ Champ trouvé mais non modifiable dans le délai imparti ('{description}')."
    except Exception as e:
        return f"❌ Erreur lors du remplissage : {e}"


def browser_control(
    action: str,
    url: str = None,
    tab_id: int = None,
    description: str = None,
    text: str = None,
    full: bool = False,
) -> str:
    """Point d'entrée unique pour l'agent."""
    if action == "list_tabs":
        return list_tabs()
    if action == "switch_tab":
        if tab_id is None:
            return "❌ Paramètre 'tab_id' requis pour l'action 'switch_tab'."
        return switch_tab(tab_id)
    if action == "navigate":
        if not url:
            return "❌ Paramètre 'url' requis pour l'action 'navigate'."
        return navigate(url)
    if action == "read_page_content":
        return read_page_content(full=full)
    if action == "list_interactive_elements":
        return list_interactive_elements()
    if action == "click_element":
        if not description:
            return "❌ Paramètre 'description' requis pour l'action 'click_element'."
        return click_element(description)
    if action == "fill_field":
        if not description or text is None:
            return "❌ Paramètres 'description' et 'text' requis pour l'action 'fill_field'."
        return fill_field(description, text)
    if action == "close_browser":
        return close_browser()
    return f"❌ Action inconnue : '{action}'."