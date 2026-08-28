"""One-off repair: deduplicate near_misses.jsonl keeping only the first occurrence
of each (scan_date, symbol) pair. Idempotent — safe to re-run.
"""
import json
from pathlib import Path

PATH = Path("data/reversal_tracking/near_misses.jsonl")

lines = [l.strip() for l in PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
before = len(lines)

seen: set = set()
kept = []
for line in lines:
    r = json.loads(line)
    key = (r["scan_date"], r["symbol"])
    if key not in seen:
        seen.add(key)
        kept.append(line)

PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")

print(f"Before: {before} rows")
print(f"After:  {len(kept)} rows")
print(f"Removed: {before - len(kept)} duplicate rows")
