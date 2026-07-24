# -*- coding: utf-8 -*-
"""
Persistent storage for already-alerted signal keys (duplicate-alert
suppression) that survives Streamlit Community Cloud restarts / redeploys,
where the local filesystem is ephemeral and resets on every rebuild/sleep-wake.

Backends:
  1. GitHub Gist  — true persistence across restarts/redeploys. Needs a
     GitHub Personal Access Token (scope: "gist") + a gist_id.
  2. Local file    — works for local `streamlit run` sessions, but resets
     whenever the app container is rebuilt on cloud hosting. Used
     automatically when no token/gist_id is configured.
"""

import json
import os
import time
from typing import Optional, Set

import requests

GIST_FILENAME = "satya_alerted_breakouts.json"
MAX_ENTRIES = 5000


class GistStore:
    backend_name = "GitHub Gist (persistent across restarts)"

    def __init__(self, token: str, gist_id: str):
        self.token = token
        self.gist_id = gist_id
        self.url = f"https://api.github.com/gists/{gist_id}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def load(self) -> Set[str]:
        try:
            r = requests.get(self.url, headers=self.headers, timeout=8)
            r.raise_for_status()
            files = r.json().get("files", {})
            f = files.get(GIST_FILENAME)
            if not f:
                return set()
            content = f.get("content", "{}")
            return set(json.loads(content).get("keys", []))
        except Exception:
            return set()

    def save(self, keys: Set[str]) -> bool:
        trimmed = list(keys)[-MAX_ENTRIES:]
        payload = {
            "files": {
                GIST_FILENAME: {
                    "content": json.dumps({"keys": trimmed, "saved_at": time.time()})
                }
            }
        }
        try:
            r = requests.patch(self.url, headers=self.headers, json=payload, timeout=8)
            return r.status_code == 200
        except Exception:
            return False


class FileStore:
    backend_name = "Local file (resets on cloud restart — set up a Gist for permanence)"

    def __init__(self, path: str):
        self.path = path

    def load(self) -> Set[str]:
        if not os.path.exists(self.path):
            return set()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return set(json.load(f).get("keys", []))
        except Exception:
            return set()

    def save(self, keys: Set[str]) -> bool:
        trimmed = list(keys)[-MAX_ENTRIES:]
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"keys": trimmed, "saved_at": time.time()}, f)
            return True
        except Exception:
            return False


def create_gist(token: str) -> Optional[str]:
    """Creates a new *secret* gist to use as the alert store. Returns the new gist_id, or None on failure."""
    url = "https://api.github.com/gists"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    payload = {
        "description": "Satya Trading — RSI Divergence Notifier alert store (do not delete)",
        "public": False,
        "files": {GIST_FILENAME: {"content": json.dumps({"keys": []})}},
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=8)
        if r.status_code == 201:
            return r.json().get("id")
    except Exception:
        pass
    return None


def get_store(github_token: str, gist_id: str, local_path: str):
    """Picks GitHub Gist storage when both a token and gist_id are available,
    otherwise falls back to a local JSON file."""
    if github_token and gist_id:
        return GistStore(github_token, gist_id)
    return FileStore(local_path)
