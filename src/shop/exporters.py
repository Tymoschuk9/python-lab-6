from __future__ import annotations
import json
from pathlib import Path

def export_order(order: dict, path: Path) -> None:
    path.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
