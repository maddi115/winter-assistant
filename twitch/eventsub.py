"""EventSub WebSocket: Twitch pushes every chat message to us. Reconnects by itself."""
import asyncio
import json

EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"


async def listen(helix, bot_id, channel_ids, on_event, log=print):
    try:
        from websockets.asyncio.client import connect
    except ImportError:                      # older websockets
        from websockets import connect
    url, need_subscribe, backoff = EVENTSUB_URL, True, 1
    while True:
        try:
            async with connect(url, max_size=2 ** 20) as ws:
                welcome = json.loads(await asyncio.wait_for(ws.recv(), 15))
                session = welcome["payload"]["session"]
                keepalive = session.get("keepalive_timeout_seconds") or 10
                if need_subscribe:
                    # must subscribe within 10s of the welcome
                    for login, cid in channel_ids.items():
                        await asyncio.to_thread(helix.subscribe_chat, session["id"], cid, bot_id)
                        log(f"👂 listening to #{login}")
                need_subscribe, backoff = False, 1
                while True:
                    m = json.loads(await asyncio.wait_for(ws.recv(), keepalive + 10))
                    kind = m["metadata"]["message_type"]
                    if kind == "notification":
                        if m["metadata"].get("subscription_type") == "channel.chat.message":
                            await on_event(m["payload"]["event"])
                    elif kind == "session_reconnect":
                        url = m["payload"]["session"]["reconnect_url"]   # subscriptions carry over
                        log("🔁 Twitch asked us to reconnect")
                        break
                    elif kind == "revocation":
                        log(f"⚠️  Twitch revoked a subscription: {m['payload']['subscription'].get('status')}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log(f"⚠️  Chat connection lost ({type(e).__name__}: {e}) - retrying in {backoff}s")
            await asyncio.sleep(backoff)
            url, need_subscribe, backoff = EVENTSUB_URL, True, min(backoff * 2, 60)
