"""Split world_detail.html tab content into partials."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
p = root / "src/novel_world/web/templates/world_detail.html"
lines = p.read_text(encoding="utf-8").splitlines()
start = next(i for i, l in enumerate(lines) if "_tab_saves.html" in l) + 1
chunk = "\n".join(lines[start:495])
out_dir = root / "src/novel_world/web/templates/world_detail"
out_dir.mkdir(exist_ok=True)

pattern = re.compile(r'(\s*<div class="tab-panel[^"]*" data-panel="(\w+)">)')
splits = pattern.split(chunk)
world_body = splits[0].strip()
(out_dir / "_tab_world.html").write_text(
    '<div class="tab-panel active" data-panel="world">\n' + world_body + "\n</div>\n",
    encoding="utf-8",
)
for i in range(1, len(splits), 3):
    header, name, body = splits[i], splits[i + 1], splits[i + 2]
    (out_dir / f"_tab_{name}.html").write_text((header + body).strip() + "\n", encoding="utf-8")

new_lines = lines[:start] + ["", "  </div>", "  </div>", "</div>"] + lines[499:]
p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("Wrote partials:", sorted(out_dir.glob("_tab_*.html")))
