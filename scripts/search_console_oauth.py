#!/usr/bin/env python3
"""Obtient un `refresh_token` OAuth Search Console, une fois pour toutes.

Gratuit, sans carte bancaire. Étapes préalables (voir aussi section 10 de
`.env.example`) :

1. Créez (ou réutilisez) un projet sur https://console.cloud.google.com/
2. Activez l'API « Search Console API » (menu « API et services » → « Bibliothèque »)
3. Menu « Identifiants » → « Créer des identifiants » → « ID client OAuth »
   → type d'application « Application de bureau »
4. Copiez le Client ID / Client secret dans votre `.env` :
       SEARCH_CONSOLE_CLIENT_ID=...
       SEARCH_CONSOLE_CLIENT_SECRET=...
5. Ajoutez votre blog comme propriété dans https://search.google.com/search-console
   (le compte Google utilisé à l'étape 6 doit avoir accès à cette propriété)

Utilisation :
    python scripts/search_console_oauth.py

Le script ouvre votre navigateur pour l'autorisation Google, récupère le code
via un petit serveur local (aucune donnée n'est envoyée ailleurs qu'à Google),
puis affiche le `refresh_token` à coller dans `SEARCH_CONSOLE_REFRESH_TOKEN`.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_PORT}/callback"

_received_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Capture le `code` renvoyé par Google, puis affiche une page de confirmation."""

    def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
        global _received_code
        query = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in query:
            _received_code = query["code"][0]
            self.wfile.write(
                b"<html><body><h2>Autorisation recue, vous pouvez fermer cet onglet.</h2></body></html>"
            )
        else:
            self.wfile.write(
                f"<html><body><h2>Autorisation refusee : {query}</h2></body></html>".encode()
            )

    def log_message(self, *args) -> None:  # silence les logs HTTP par défaut
        pass


def main() -> int:
    client_id = os.environ.get("SEARCH_CONSOLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SEARCH_CONSOLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "Renseignez SEARCH_CONSOLE_CLIENT_ID et SEARCH_CONSOLE_CLIENT_SECRET\n"
            "(dans .env, puis `export $(cat .env | xargs)`, ou en variables d'environnement)\n"
            "avant de lancer ce script.",
            file=sys.stderr,
        )
        return 1

    params = {
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",  # indispensable pour obtenir un refresh_token
        "prompt": "consent",       # force le renvoi d'un refresh_token même si déjà autorisé
    }
    auth_url = f"{_AUTH_URL}?{urlencode(params)}"
    print(f"Ouverture du navigateur pour l'autorisation Google…\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", _PORT), _CallbackHandler)
    print(f"En attente de la redirection sur {_REDIRECT_URI} …")
    server.handle_request()  # traite une seule requête (le callback), puis rend la main

    if not _received_code:
        print("Aucun code d'autorisation reçu.", file=sys.stderr)
        return 1

    response = requests.post(
        _TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": _received_code,
            "grant_type": "authorization_code",
            "redirect_uri": _REDIRECT_URI,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        print(f"Échec de l'échange du code : HTTP {response.status_code} — {response.text}", file=sys.stderr)
        return 1

    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        print(
            "Aucun refresh_token renvoyé : Google n'en délivre un qu'à la première autorisation.\n"
            "Révoquez l'accès sur https://myaccount.google.com/permissions puis relancez ce script.",
            file=sys.stderr,
        )
        return 1

    print("\nAjoutez cette ligne à votre .env :\n")
    print(f"SEARCH_CONSOLE_REFRESH_TOKEN={refresh_token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
