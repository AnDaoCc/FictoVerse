from __future__ import annotations

import re
from typing import Iterator

_TOKEN_RE = re.compile(
    r"/(?P<cmd>[a-zA-Z_][\w-]*)"
    r'|"(?P<dq>[^"]*)"'
    r"|'(?P<sq>[^']*)'"
    r"|(?P<pipe>\|)"
    r"|(?P<ws>\s+)"
    r"|(?P<word>[^\s|/]+)"
)


def tokenize(script: str) -> list[str]:
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(script or ""):
        if m.group("cmd"):
            tokens.append("/" + m.group("cmd"))
        elif m.group("dq") is not None:
            tokens.append(m.group("dq"))
        elif m.group("sq") is not None:
            tokens.append(m.group("sq"))
        elif m.group("pipe"):
            tokens.append("|")
        elif m.group("word"):
            tokens.append(m.group("word"))
    return tokens
