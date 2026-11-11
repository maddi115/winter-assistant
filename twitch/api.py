"""The 3 Helix calls the bot needs: look up user ids, subscribe to chat, send a message."""
from twitch.http import request, HTTPError

HELIX = "https://api.twitch.tv/helix"


class Helix:
    def __init__(self, client_id, token):
        self.client_id, self.token = client_id, token

    def _call(self, method, path, **kw):
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self.token.access}", "Client-Id": self.client_id}
            try:
                return request(method, HELIX + path, headers=headers, **kw)[1]
            except HTTPError as e:
                if e.status == 401 and attempt == 1:
                    self.token.refresh()          # expired -> refresh once and retry
                    continue
                raise

    def user_ids(self, logins):
        q = "&".join(f"login={l.lower()}" for l in logins)
        data = self._call("GET", f"/users?{q}").get("data", [])
        return {u["login"]: u["id"] for u in data}

    def channel_info(self, broadcaster_ids):
        """{id: "title · category"} - what's on stream, so the AI isn't guessing."""
        q = "&".join(f"broadcaster_id={b}" for b in broadcaster_ids)
        out = {}
        for d in self._call("GET", f"/channels?{q}").get("data", []):
            bits = [x for x in (d.get("title", "").strip(), d.get("game_name", "").strip()) if x]
            out[d.get("broadcaster_id")] = " · ".join(bits)[:160]
        return out

    def subscribe_chat(self, session_id, broadcaster_id, bot_id):
        return self._call("POST", "/eventsub/subscriptions", body={
            "type": "channel.chat.message", "version": "1",
            "condition": {"broadcaster_user_id": broadcaster_id, "user_id": bot_id},
            "transport": {"method": "websocket", "session_id": session_id}})

    def send(self, broadcaster_id, bot_id, text, reply_to=None):
        """Returns (sent, reason). Twitch can drop a message (AutoMod, slow mode, followers-only...)."""
        body = {"broadcaster_id": broadcaster_id, "sender_id": bot_id, "message": text}
        if reply_to:
            body["reply_parent_message_id"] = reply_to
        try:
            d = self._call("POST", "/chat/messages", body=body).get("data", [{}])[0]
        except HTTPError as e:
            return False, str(e.body.get("message", e))
        if d.get("is_sent"):
            return True, ""
        drop = d.get("drop_reason") or {}
        return False, drop.get("message") or drop.get("code") or "dropped"
