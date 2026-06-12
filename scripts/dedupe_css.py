from pathlib import Path

p = Path(r"d:\APPKF\小说世界书\src\novel_world\web\static\style.css")
text = p.read_text(encoding="utf-8")
marker = "/* ---- Markdown content in assistant bubbles ---- */"
first = text.find(marker)
second = text.find(marker, first + 1)
if second == -1:
    print("no duplicate found")
else:
    end = text.find(".thinking-content {", second)
    if end == -1:
        end = text.find(".attachment-bar {", second)
    new_text = text[:second] + text[end:]
    p.write_text(new_text, encoding="utf-8")
    print("removed duplicate block", second, end)
