import hashlib
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

class MsgType(Enum):
    PROPOSAL = auto()
    PREVOTE = auto()
    PRECOMMIT = auto()

@dataclass
class Message:
    typ: MsgType
    height: int
    round: int
    from_id: str
    value: Optional[bytes]  # PROPOSAL nosi blok, PREVOTE/PRECOMMIT nose id(v) ili None
    valid_round: int = -1
    vp: int = 1  # voting power pošiljaoca