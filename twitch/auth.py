"""Log the BOT account in with Twitch's Device Code Flow (no password, no client secret).

  python tools/twitch_bot.py --login
    -> open the link, type the code, approve while signed in as the bot account.
The token is saved to twitch_token.json (git-ignored) and refreshed automatically.
"""
import json
import time
from pathlib import Path

from twitch.http import request, HTTPError

SCOPES = "user:read:chat user:write:chat"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def save(path, tok):
    p = Path(path)
    p.write_text(json.dumps(tok, indent=2))
    try:
        p.chmod(0o600)          # only you can read it
    except OSError:
        pass


def device_login(client_id, path):
    _, d = request("POST", DEVICE_URL, form={"client_id": client_id, "scopes": SCOPES})
    print("\n🔑 Sign in as your BOT account (not your main), then open:\n")
    print(f"   {d['verification_uri']}")
    print(f"\n   code: {d['user_code']}   (expires in {d['expires_in'] // 60} min)\n")
    interval = d.get("interval", 5)
    deadline = time.time() + d["expires_in"]
    while time.time() < deadline:
        time.sleep(interval)
        try:
            _, tok = request("POST", TOKEN_URL, form={
                "client_id": client_id, "scopes": SCOPES, "device_code": d["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        except HTTPError as e:
            msg = str(e.body.get("message", "")).lower()
            if "pending" in msg:
                continue
            if "slow_down" in msg:
                interval += 5
                continue
            raise SystemExit(f"❌ Login failed: {e.body}")
        info = validate(tok["access_token"])
        tok["login"], tok["user_id"] = info["login"], info["user_id"]
        save(path, tok)
        print(f"✅ Logged in as {info['login']} - token saved to {path}")
        return tok
    raise SystemExit("❌ Code expired - run --login again")


def validate(access_token):
    """{'login','user_id','scopes','expires_in'} or None if the token is dead."""
    try:
        _, info = request("GET", VALIDATE_URL, headers={"Authorization": f"OAuth {access_token}"})
        return info
    except HTTPError as e:
        if e.status == 401:
            return None
        raise


def refresh(client_id, path, tok):
    # public clients refresh without a secret
    _, new = request("POST", TOKEN_URL, form={
        "client_id": client_id, "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    tok = dict(tok, access_token=new["access_token"],
               refresh_token=new.get("refresh_token", tok["refresh_token"]))
    save(path, tok)
    return tok


class Token:
    """Keeps a working access token; refreshes it when Twitch says it expired."""

    def __init__(self, client_id, path):
        self.client_id, self.path = client_id, path
        tok = load(path)
        if not tok:
            raise SystemExit("❌ No bot login yet. Run:  python tools/twitch_bot.py --login")
        self.tok = tok
        info = validate(tok["access_token"])
        if info is None:
            self.refresh()
            info = validate(self.tok["access_token"])
        missing = set(SCOPES.split()) - set(info.get("scopes", []))
        if missing:
            raise SystemExit(f"❌ Token is missing {missing}. Run --login again.")
        self.login, self.user_id = info["login"], info["user_id"]

    @property
    def access(self):
        return self.tok["access_token"]

    def refresh(self):
        try:
            self.tok = refresh(self.client_id, self.path, self.tok)
        except HTTPError as e:
            raise SystemExit(f"❌ Couldn't refresh the login ({e}). Run --login again.")
