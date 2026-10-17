"""Écouteur Discord : Monika répond aux messages que ses utilisateurs autorisés lui envoient.

Fonctionnement : un thread de fond fait tourner le client Discord (discord.py, connexion « gateway »).
Chaque message accepté déclenche un tour de l'agent (process_user_message) avec un historique PAR salon,
puis la réponse est renvoyée sur Discord, découpée en messages de 2000 caractères maximum.

Pièces jointes : images, PDF, DOCX, texte et audio sont lus avant le tour de l'agent (voir
integrations/discord_attachments.py). Quand un outil lent tourne, une courte phrase d'attente est postée
dans le salon (drapeaux `lent` / `phrase_attente` des outils, voir tools/registry.py).

SÉCURITÉ : Monika peut lancer des commandes et lire des fichiers. Seuls les identifiants de
DISCORD_ALLOWED_USER_IDS sont écoutés ; tous les autres messages sont ignorés. Sont acceptés :
  - les messages privés (MP) d'un utilisateur autorisé ;
  - dans un serveur, ses messages qui @mentionnent le bot, ou qui sont dans DISCORD_LISTEN_CHANNEL_IDS.
"""

import asyncio
import re
import threading
from typing import Callable, Optional

import discord

from core.settings import settings
from integrations.discord_attachments import Attachment, build_message
from tools.social.discord_tools import _split_message, send_discord_message

RESET_COMMANDS = {"/reset", "!reset", "reset", "/nouveau", "!nouveau"}
_NO_MENTIONS = discord.AllowedMentions.none()  # une réponse ne doit jamais pinguer @everyone ni personne
RETRY_MIN_SECONDS = 5  # attente avant de retenter une connexion échouée (doublée à chaque échec)
RETRY_MAX_SECONDS = 60
_ERROR_REPLY ="Je n'ai pas réussi à traiter ça, une erreur interne s'est produite. Tu peux reformuler ou réessayer."


def parse_ids(raw: Optional[str]) -> list[int]:
    """Identifiants Discord d'une chaîne libre (virgules, espaces, guillemets...), sans doublon, dans l'ordre."""
    seen: list[int] = []
    for token in re.findall(r"\d{15,22}", raw or ""):
        if int(token) not in seen:
            seen.append(int(token))
    return seen


class _Client(discord.Client):
    def __init__(self, listener: "DiscordListener", intents: discord.Intents) -> None:
        super().__init__(intents=intents)
        self._listener = listener

    async def on_ready(self) -> None:
        print(f"✅ [Discord] Écoute active en tant que {self.user} ({len(self._listener.allowed)} utilisateur(s) autorisé(s)).")

    async def on_message(self, message: discord.Message) -> None:
        try:
            await self._listener.handle_message(message, self.user)
        except Exception as exc:  # une erreur sur un message ne doit pas arrêter l'écoute
            print(f"⚠️ [Discord] Erreur sur un message : {type(exc).__name__}: {exc}")


class DiscordListener:
    def __init__(self, process: Callable[..., str]) -> None:
        """`process(messages, on_wait=...)` exécute un tour de l'agent sur la liste de messages et renvoie la réponse."""
        self._process = process
        self.allowed: list[int] = parse_ids(settings.DISCORD_ALLOWED_USER_IDS)
        self.channels: set[int] = set(parse_ids(settings.DISCORD_LISTEN_CHANNEL_IDS))
        self._histories: dict[int, list] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[discord.Client] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    # --- cycle de vie ------------------------------------------------------------------
    def start(self) -> bool:
        if not settings.DISCORD_BOT_TOKEN:
            print("⚠️ [Discord] Écoute désactivée : DISCORD_BOT_TOKEN n'est pas défini dans .env.")
            return False
        if not self.allowed:
            print(
                "⚠️ [Discord] Écoute désactivée : DISCORD_ALLOWED_USER_IDS est vide. Sans liste d'utilisateurs "
                "autorisés, n'importe qui pourrait piloter ton ordinateur ; ajoute ton identifiant Discord."
            )
            return False
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="discord-listener")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stopping = True
        loop, client = self._loop, self._client
        if loop is not None and client is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop).result(timeout=5)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:
            print(f"⚠️ [Discord] Écoute arrêtée : {type(exc).__name__}: {exc}")

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        intents = discord.Intents.default()
        intents.message_content = settings.DISCORD_MESSAGE_CONTENT_INTENT
        delay = RETRY_MIN_SECONDS
        while not self._stopping:
            # Un client fermé ne peut pas être relancé : on en crée un neuf à chaque tentative.
            self._client = _Client(self, intents)
            try:
                # Après une première connexion réussie, discord.py se reconnecte tout seul (reconnect=True).
                await self._client.start(settings.DISCORD_BOT_TOKEN)
            except discord.LoginFailure:
                print("❌ [Discord] Jeton invalide : vérifie DISCORD_BOT_TOKEN dans .env.")
                return
            except discord.PrivilegedIntentsRequired:
                print(
                    "❌ [Discord] Intent privilégié refusé : active « Message Content Intent » dans le portail "
                    "développeur (onglet Bot), ou mets DISCORD_MESSAGE_CONTENT_INTENT=false."
                )
                return
            except Exception as exc:  # réseau absent au démarrage, panne Discord...
                if self._stopping:
                    return
                print(f"⚠️ [Discord] Connexion impossible ({type(exc).__name__}) : nouvelle tentative dans {delay:.0f} s.")
            finally:
                await self._client.close()
            for _ in range(int(delay)):  # attente découpée pour que stop() soit pris en compte vite
                if self._stopping:
                    return
                await asyncio.sleep(1)
            delay = min(delay * 2, RETRY_MAX_SECONDS)

    def notify_owner(self, text: str) -> None:
        """Envoie un message privé au premier utilisateur autorisé (ex. résultat d'une tâche planifiée)."""
        if not self.allowed:
            return
        result = send_discord_message(str(self.allowed[0]), text)
        if result.startswith("❌"):
            print(f"⚠️ [Discord] Notification non envoyée : {result}")

    # --- traitement d'un message ---------------------------------------------------------
    async def handle_message(self, message, bot_user) -> bool:
        """Traite un message Discord. Renvoie True s'il a été accepté et traité."""
        author = message.author
        if author.bot or author.id == bot_user.id:
            return False

        is_dm = message.guild is None
        mentioned = any(user.id == bot_user.id for user in message.mentions)
        if not is_dm and not (mentioned or message.channel.id in self.channels):
            return False  # message de salon qui ne nous concerne pas
        if author.id not in self.allowed:
            print(f"🚫 [Discord] Message ignoré : utilisateur non autorisé ({author.id}).")
            return False

        text = re.sub(rf"<@!?{bot_user.id}>", "", message.content or "").strip()
        attachments = list(message.attachments)
        if not text and not attachments:
            return False

        key = message.channel.id
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:  # un message à la fois par salon, dans l'ordre d'arrivée
            if text.lower() in RESET_COMMANDS:
                self._histories.pop(key, None)
                await message.channel.send("🧹 Conversation réinitialisée.", allowed_mentions=_NO_MENTIONS)
                return True

            loop = asyncio.get_running_loop()
            async with message.channel.typing():
                if attachments:
                    text = await self._with_attachments(text, attachments, loop)
                print(f"💬 [Discord] {author}: {text[:300]}{'…' if len(text) > 300 else ''}")
                on_wait = self._wait_notifier(message.channel, loop)
                reply = await loop.run_in_executor(None, self._turn, key, text, on_wait)
            print(f"💬 [Discord] Monika: {reply[:300]}{'…' if len(reply) > 300 else ''}")
            for chunk in _split_message(reply) or ["…"]:
                await message.channel.send(chunk, allowed_mentions=_NO_MENTIONS)
        return True

    # --- pièces jointes ------------------------------------------------------------------
    async def _download_attachments(self, attachments) -> tuple[list[Attachment], list[str]]:
        """Télécharge les pièces jointes dans les limites configurées ; renvoie (gardées, motifs des ignorées)."""
        max_files = settings.DISCORD_ATTACHMENT_MAX_FILES
        max_mb = settings.DISCORD_ATTACHMENT_MAX_MB
        max_bytes = int(max_mb * 1024 * 1024)
        kept: list[Attachment] = []
        skipped: list[str] = []
        for att in attachments:
            if len(kept) >= max_files:
                skipped.append(f"{att.filename} (au plus {max_files} fichiers lus par message)")
                continue
            if att.size > max_bytes:
                skipped.append(f"{att.filename} ({att.size / (1024 * 1024):.1f} Mo, au-dessus de la limite de {max_mb:g} Mo)")
                continue
            try:
                data = await att.read()
            except Exception as exc:
                skipped.append(f"{att.filename} (téléchargement impossible : {type(exc).__name__})")
                continue
            kept.append(Attachment(att.filename, data, att.content_type or ""))
        return kept, skipped

    async def _with_attachments(self, text: str, attachments, loop: asyncio.AbstractEventLoop) -> str:
        """Texte de l'utilisateur complété par le contenu de ses pièces jointes (vision, PDF, Whisper...)."""
        if not settings.DISCORD_ATTACHMENTS_ENABLED:
            note = f"[{len(attachments)} pièce(s) jointe(s) reçue(s) : lecture des fichiers désactivée (DISCORD_ATTACHMENTS_ENABLED=false)]"
            return f"{text}\n{note}".strip()
        kept, skipped = await self._download_attachments(attachments)
        # Vision, extraction PDF et Whisper sont bloquants : hors de la boucle asyncio.
        return await loop.run_in_executor(None, build_message, text, kept, skipped)

    # --- phrase d'attente ----------------------------------------------------------------
    def _wait_notifier(self, channel, loop: asyncio.AbstractEventLoop):
        """Fonction `on_wait(phrase)` qui poste la phrase d'attente dans le salon (appelée depuis un autre thread)."""

        def notify(phrase: str) -> None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    channel.send(phrase, allowed_mentions=_NO_MENTIONS), loop
                )
                future.result(timeout=10)
            except Exception as exc:
                print(f"⚠️ [Discord] Phrase d'attente non envoyée : {type(exc).__name__}: {exc}")

        return notify

    def _turn(self, key: int, text: str, on_wait: Optional[Callable[[str], None]] = None) -> str:
        """Un tour de l'agent (bloquant : appelé hors de la boucle asyncio)."""
        messages = self._histories.setdefault(key, [])
        snapshot = list(messages)  # si le tour échoue, on revient à un historique cohérent
        messages.append({"role": "user", "content": text})
        try:
            return self._process(messages, on_wait=on_wait) or "Action terminée sans message retourné."
        except Exception as exc:
            messages[:] = snapshot
            print(f"⚠️ [Discord] Erreur de traitement : {type(exc).__name__}: {exc}")
            return _ERROR_REPLY
