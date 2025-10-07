import hashlib
from typing import Optional

def vid(value: Optional[bytes]) -> Optional[bytes]:
    """Vraća hash vrednosti bloka (id bloka)."""
    if value is None:
        return None
    return hashlib.sha256(value).digest()