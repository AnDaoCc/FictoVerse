import json

from novel_world.modules.character.services.chub_codec import parse_chub_bytes
from novel_world.modules.character.services.risu_codec import parse_risu_bytes


def test_chub_import() -> None:
    raw = json.dumps({"chub": True, "name": "Chub角色", "data": {"description": "d", "first_mes": "hi"}}).encode()
    card = parse_chub_bytes(raw)
    assert card.name == "Chub角色"


def test_risu_import() -> None:
    raw = json.dumps({"type": "risu", "name": "Risu角色", "description": "d", "greeting": "yo"}).encode()
    card = parse_risu_bytes(raw)
    assert card.name == "Risu角色"
