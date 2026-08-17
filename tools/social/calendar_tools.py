"""
tools/social/calendar_tools.py
-------------------------------
Consultation et création d'événements Google Calendar.
"""

import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CREDENTIALS_FILE = os.path.expanduser("~/.config/monika/credentials_calendar.json")
TOKEN_FILE = os.path.expanduser("~/.config/monika/token.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']

def _get_calendar_service():
    """Gère l'authentification OAuth2 auprès de l'API Google Calendar."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Fichier '{CREDENTIALS_FILE}' introuvable. Téléchargez vos identifiants OAuth 2.0 depuis la console Google Cloud."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def calendar_control(action: str, summary: str = None, start_time: str = None, end_time: str = None, limit: int = 5) -> str:
    """Gère la consultation et l'ajout d'événements dans Google Calendar."""
    try:
        service = _get_calendar_service()

        if action == "list":
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
                calendarId='primary', timeMin=now,
                maxResults=limit, singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            if not events:
                return "Aucun événement à venir trouvé."

            formatted = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary_text = event.get('summary', 'Sans titre')
                formatted.append(f"• {start} : {summary_text}")

            return "Prochains événements Google Calendar :\n" + "\n".join(formatted)

        elif action == "add":
            if not summary or not start_time or not end_time:
                return "Erreur : 'summary', 'start_time' et 'end_time' (format ISO: YYYY-MM-DDTHH:MM:SS) sont requis."

            event = {
                'summary': summary,
                'start': {'dateTime': start_time, 'timeZone': 'Europe/Paris'},
                'end': {'dateTime': end_time, 'timeZone': 'Europe/Paris'},
            }

            created_event = service.events().insert(calendarId='primary', body=event).execute()
            return f"Événement '{summary}' créé avec succès (Lien : {created_event.get('htmlLink')})."

        return "Action non reconnue."
    except Exception as e:
        return f"Erreur Google Calendar : {str(e)}"