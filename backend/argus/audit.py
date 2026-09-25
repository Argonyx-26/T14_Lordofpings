"""Append-only, hash-chained audit log of operator actions (tampering breaks the chain)."""
import hashlib
import json
import time
from pathlib import Path

from argus import settings

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path = settings.CACHE_DIR / "audit.jsonl"):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, **fields) -> dict:
        entries = self.entries()
        prev = entries[-1]["hash"] if entries else GENESIS
        body = {"wall_time": time.time(), **fields, "prev_hash": prev}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(body) + "\n")
        return body

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries():
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["prev_hash"] != prev:
                return False
            if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True
