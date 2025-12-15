import asyncio
from collections import defaultdict
from concurrent.futures import Future
from typing import DefaultDict

from fastapi import WebSocket


class NotificationWebsocketManager:
    def __init__(self):
        self._connections: DefaultDict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections:
                connections.discard(websocket)
                if not connections:
                    self._connections.pop(user_id, None)
        try:
            await websocket.close()
        except RuntimeError:
            pass

    async def send_to_user(self, user_id: int, message: dict) -> bool:
        async with self._lock:
            connections = list(self._connections.get(user_id, []))
        if not connections:
            return False
        delivered = False
        for websocket in connections:
            try:
                await websocket.send_json(message)
                delivered = True
            except RuntimeError:
                await self.disconnect(user_id, websocket)
        return delivered

    def schedule_send(self, user_id: int, message: dict) -> Future[bool] | None:
        if not self.has_connection(user_id) or self._loop is None:
            return None
        return asyncio.run_coroutine_threadsafe(self.send_to_user(user_id, message), self._loop)

    def has_connection(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))


notification_ws_manager = NotificationWebsocketManager()
