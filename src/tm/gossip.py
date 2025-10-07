import queue
import asyncio
import random
from .message import Message

class Gossip:
    def __init__(self):
        self.inboxes = {}

    def register(self, pid: str):
        # Svaka nit ima svoj thread-safe red (Queue)
        self.inboxes[pid] = queue.Queue()

    async def send(self, to: str, msg: Message):
        # Nasumično kašnjenje — simulacija mrežnog latency-ja
        await asyncio.sleep(random.uniform(0.01, 0.05))
        self.inboxes[to].put(msg)

    async def broadcast(self, from_id: str, msg: Message):
        # Šalje poruku svim čvorovima (uključujući i samog pošiljaoca)
        for pid in self.inboxes:
            await self.send(pid, msg)