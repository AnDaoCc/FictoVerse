from __future__ import annotations

from novel_world.web.credits import AUTHOR_CREDIT_LINE


def test_author_credit_line_contains_contact_fields() -> None:
    assert "962233391" in AUTHOR_CREDIT_LINE
    assert "B站安岛Cc" in AUTHOR_CREDIT_LINE
    assert "259523153" in AUTHOR_CREDIT_LINE
