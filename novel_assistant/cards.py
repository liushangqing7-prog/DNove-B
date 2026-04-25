from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


@dataclass
class SettingCard:
    path: Path
    meta: Dict
    body: str
    proposals: List[str] = field(default_factory=list)


def parse_front_matter(content: str) -> Tuple[Dict, str]:
    if not content.startswith("---\n"):
        return {}, content
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, content
    meta_raw = parts[0].replace("---\n", "", 1)
    body = parts[1]
    try:
        meta = yaml.safe_load(meta_raw) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, body


def dump_front_matter(meta: Dict, body: str) -> str:
    meta_text = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    return f"---\n{meta_text}---\n{body}"


class CardRepository:
    def __init__(self, cards_dir: Path):
        self.cards_dir = cards_dir
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    def list_cards(self) -> List[SettingCard]:
        cards: List[SettingCard] = []
        for pattern in ("*.char.md", "*.world.md", "*.outline.md"):
            for file in self.cards_dir.glob(pattern):
                content = file.read_text(encoding="utf-8")
                meta, body = parse_front_matter(content)
                cards.append(SettingCard(path=file, meta=meta, body=body))
        return sorted(cards, key=lambda c: c.path.name)

    def save_card(self, card: SettingCard) -> None:
        card.path.write_text(dump_front_matter(card.meta, card.body), encoding="utf-8")

    def search(self, keyword: str) -> List[SettingCard]:
        results = []
        for c in self.list_cards():
            if keyword.lower() in c.body.lower() or keyword.lower() in str(c.meta).lower():
                results.append(c)
        return results
