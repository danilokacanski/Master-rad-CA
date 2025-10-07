import asyncio, random, time, hashlib
from enum import Enum, auto
from typing import Any, Dict, Optional, List, Tuple
from .message import Message, MsgType
from .gossip import Gossip
from .utils import vid
from colorama import Fore, Style, init

init(autoreset=True)  # automatski reset boja posle svake linije


class Step(Enum):
    PROPOSE = auto()
    PREVOTE = auto()
    PRECOMMIT = auto()


class Node:
    def __init__(self, pid: str, vp: int, net: Gossip, all_ids: List[str], power_map: Dict[str, int]):
        self.pid = pid
        self.vp = vp
        self.net = net
        self.inbox = net.inboxes[pid]
        self.all_ids = all_ids
        self.power_map = power_map

        # Tendermint state
        self.height = 0
        self.round = 0
        self.step = Step.PROPOSE

        self.locked_value: Optional[bytes] = None
        self.locked_round: int = -1
        self.valid_value: Optional[bytes] = None
        self.valid_round: int = -1

        self.decisions: Dict[int, bytes] = {}
        self.msg_log: List[Message] = []

        # timeout parametri
        self.init_prop = 0.2
        self.init_prev = 0.2
        self.init_pcom = 0.2
        self.delta = 0.05

        self.prevotes: Dict[Tuple[int,int,Optional[bytes]], int] = {}
        self.precoms: Dict[Tuple[int,int,Optional[bytes]], int] = {}

    # ---- utili ----
    def proposer(self, h: int, r: int) -> str:
        expanded = []
        for pid, p in self.power_map.items():
            expanded += [pid] * p
        idx = (h * 1000003 + r) % len(expanded)
        return expanded[idx]

    def total_power(self) -> int:
        return sum(self.power_map.values())

    def f(self) -> int:
        n = self.total_power()
        return (n - 1) // 3

    def two_f_plus_one(self) -> int:
        return 2 * self.f() + 1

    def valid(self, v: Optional[bytes]) -> bool:
        return v is not None

    def short_hash(self, v: Optional[bytes]) -> str:
        if v is None:
            return "nil"
        return hashlib.sha256(v).hexdigest()[:6]

    def get_value(self) -> bytes:
        payload = f"h={self.height},r={self.round},from={self.pid},rnd={random.random()}".encode()
        return payload

    # ---- logging ----
    def log(self, color, phase, msg):
        print(f"{color}[{time.strftime('%H:%M:%S')}] {self.pid} {phase} | {msg}{Style.RESET_ALL}")

    # ---- core broadcast ----
    async def bcast(self, m: Message):
        self.msg_log.append(m)
        short_v = self.short_hash(m.value)
        phase = m.typ.name
        if m.typ == MsgType.PROPOSAL:
            self.log(Fore.BLUE, "📤 PROPOSAL", f"h={m.height}, r={m.round}, v={short_v}")
        elif m.typ == MsgType.PREVOTE:
            self.log(Fore.YELLOW, "🗳️ PREVOTE", f"h={m.height}, r={m.round}, v={short_v}")
        elif m.typ == MsgType.PRECOMMIT:
            self.log(Fore.MAGENTA, "🔒 PRECOMMIT", f"h={m.height}, r={m.round}, v={short_v}")
        await self.net.broadcast(self.pid, m)

    # ---- round management ----
    async def start_round(self, r: int):
        self.round = r
        self.step = Step.PROPOSE
        proposer = self.proposer(self.height, self.round)
        print(Fore.CYAN + f"\n----- [HEIGHT={self.height}] Round {r} START by proposer={proposer} -----" + Style.RESET_ALL)
        if proposer == self.pid:
            v = self.valid_value if self.valid_value is not None else self.get_value()
            await self.bcast(Message(MsgType.PROPOSAL, self.height, self.round, self.pid, v, self.valid_round, self.vp))
        asyncio.create_task(self.on_timeout_propose(self.height, self.round))

    # ---- timeouts ----
    async def on_timeout_propose(self, h: int, r: int):
        await asyncio.sleep(self.init_prop + r * self.delta)
        if h == self.height and r == self.round and self.step == Step.PROPOSE:
            self.log(Fore.YELLOW, "⏰ TIMEOUT", f"no valid proposal → PREVOTE nil")
            await self.bcast(Message(MsgType.PREVOTE, self.height, self.round, self.pid, None, vp=self.vp))
            self.step = Step.PREVOTE
            asyncio.create_task(self.on_timeout_prevote(self.height, self.round))

    async def on_timeout_prevote(self, h: int, r: int):
        await asyncio.sleep(self.init_prev + r * self.delta)
        if h == self.height and r == self.round and self.step == Step.PREVOTE:
            self.log(Fore.MAGENTA, "⏰ TIMEOUT", f"no quorum → PRECOMMIT nil")
            await self.bcast(Message(MsgType.PRECOMMIT, self.height, self.round, self.pid, None, vp=self.vp))
            self.step = Step.PRECOMMIT
            asyncio.create_task(self.on_timeout_precommit(self.height, self.round))

    async def on_timeout_precommit(self, h: int, r: int):
        await asyncio.sleep(self.init_pcom + r * self.delta)
        if h == self.height and r == self.round:
            self.log(Fore.CYAN, "↩️ NEXT ROUND", f"moving to round {self.round + 1}")
            await self.start_round(self.round + 1)

    # ---- handling messages ----
    async def handle(self, m: Message):
        self.msg_log.append(m)
        if m.typ == MsgType.PROPOSAL and m.height == self.height and m.round == self.round and self.step == Step.PROPOSE:
            v = m.value
            if self.valid(v) and (self.locked_round == -1 or self.locked_value == v):
                await self.bcast(Message(MsgType.PREVOTE, self.height, self.round, self.pid, vid(v), vp=self.vp))
            else:
                await self.bcast(Message(MsgType.PREVOTE, self.height, self.round, self.pid, None, vp=self.vp))
            self.step = Step.PREVOTE
            asyncio.create_task(self.on_timeout_prevote(self.height, self.round))
            return

        if m.typ == MsgType.PREVOTE and m.height == self.height:
            k = (m.height, m.round, m.value)
            self.prevotes[k] = self.prevotes.get(k, 0) + m.vp
            if self.prevotes[k] >= self.two_f_plus_one() and self.step.value <= Step.PREVOTE.value:
                if m.value is not None and self.step != Step.PRECOMMIT:
                    cand = None
                    for mm in reversed(self.msg_log):
                        if mm.typ == MsgType.PROPOSAL and mm.height == self.height and mm.round == m.round:
                            if vid(mm.value) == m.value:
                                cand = mm.value
                                break
                    if cand is not None and self.valid(cand):
                        self.locked_value = cand
                        self.locked_round = self.round
                        self.log(Fore.MAGENTA, "🔒 LOCKED", f"v={self.short_hash(cand)} at r={self.round}")
                        await self.bcast(Message(MsgType.PRECOMMIT, self.height, self.round, self.pid, m.value, vp=self.vp))
                        self.step = Step.PRECOMMIT
                        self.valid_value = cand
                        self.valid_round = self.round
                        asyncio.create_task(self.on_timeout_precommit(self.height, self.round))
            return

        if m.typ == MsgType.PRECOMMIT and m.height == self.height:
            k = (m.height, m.round, m.value)
            self.precoms[k] = self.precoms.get(k, 0) + m.vp
            if m.value is not None and self.precoms[k] >= self.two_f_plus_one():
                prop = None
                for mm in reversed(self.msg_log):
                    if mm.typ == MsgType.PROPOSAL and mm.height == self.height and mm.round == m.round:
                        if vid(mm.value) == m.value:
                            prop = mm.value
                            break
                if prop is not None and self.valid(prop) and self.decisions.get(self.height) is None:
                    self.decisions[self.height] = prop
                    self.log(Fore.GREEN, "✅ DECIDED",
                             f"value={self.short_hash(prop)} at h={self.height}, r={m.round}")
                    print(Fore.GREEN + "=" * 60 + Style.RESET_ALL)
                    # await asyncio.sleep(0.2)  # for more consistent print
                    self.height += 1
                    self.round = 0
                    self.step = Step.PROPOSE
                    self.locked_value = None
                    self.locked_round = -1
                    self.valid_value = None
                    self.valid_round = -1
                    self.prevotes.clear()
                    self.precoms.clear()
                    self.msg_log.clear()
                    await self.start_round(0)
            return

    # ---- main loop ----
    async def run(self, stop_event):
        await self.start_round(0)
        loop = asyncio.get_event_loop()
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(loop.run_in_executor(None, self.inbox.get), timeout=0.1)
                await self.handle(msg)
            except asyncio.TimeoutError:
                continue