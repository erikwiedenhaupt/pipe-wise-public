# backend/core/ws_manager.py
from __future__ import annotations
import asyncio
from typing import Dict, Set, Any
from fastapi import WebSocket
from datetime import datetime, timezone
import json

class DebugWSManager:
    def __init__(self) -> None:
        self._channels: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            for ch, conns in list(self._channels.items()):
                if ws in conns:
                    conns.remove(ws)
                if not conns:
                    self._channels.pop(ch, None)

    async def broadcast(self, channel: str, event: Any) -> None:
        # Skip if no listeners
        async with self._lock:
            conns = list(self._channels.get(channel, []))
        if not conns:
            return
        payload = {
            "at": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        msg = json.dumps(payload, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for d in dead:
                    for ch, conns in list(self._channels.items()):
                        if d in conns:
                            conns.remove(d)
                        if not conns:
                            self._channels.pop(ch, None)