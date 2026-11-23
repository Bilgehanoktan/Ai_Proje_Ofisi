"""HTML generator for V1 Status and Workflow View Preview.
Dynamically parses UYGULAMA_DURUM_MATRISI.md and displays exact current findings,
pin hashes, and test results.
Distinguishes DEMO_SYNTHETIC view from authenticated PostgreSQL runtime.
Never claims G0 closure, first13 completion, or human acceptance.
"""

import hashlib
import html
import re
from pathlib import Path

ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "docs/migration/SOURCE_TO_TARGET.json").is_file()
)
MATRIX_PATH = ROOT / "progress/UYGULAMA_DURUM_MATRISI.md"
FRONTEND = ROOT / "product/frontend"


def parse_matrix_modules() -> list[dict]:
    """Dynamically parses the 16 module cards from UYGULAMA_DURUM_MATRISI.md."""
    if not MATRIX_PATH.is_file():
        return []

    content = MATRIX_PATH.read_text(encoding="utf-8")

    # First extract phases from Table 3 (Section 3) if available
    phase_by_mod = {}
    table_m = re.search(r"## 3\..*?\n([\s\S]*?)(?=## 4\.)", content)
    if table_m:
        for line in table_m.group(1).splitlines():
            if "MOD-" in line and "|" in line:
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 3:
                    mod_id_m = re.search(r"MOD-\d{3}", cols[0])
                    if mod_id_m:
                        phase_by_mod[mod_id_m.group(0)] = cols[2]

    modules = []

    # Regex to match module sections: ### MOD-XXX — Name
    pattern = r"### (MOD-\d{3}) — ([^\n\r]+)(.*?)(?=(?:### MOD-\d{3}|## 6\.|\Z))"
    matches = re.findall(pattern, content, re.DOTALL)

    for mod_id, mod_name, section_text in matches:
        mod_id_clean = mod_id.strip()
        phase = phase_by_mod.get(mod_id_clean)
        if not phase:
            phase_m = re.search(
                r"\|\s*Sıradaki görev\s*/\s*faz[^\n|]*\|\s*[^|\n]*/\s*([^|\n]+)\|", section_text
            )
            phase = phase_m.group(1).strip() if phase_m else "PH-00"

        status_m = re.search(r"\|\s*Antigravity durumu[^\n|]+\|\s*([^|\n]+)\|", section_text)
        status = status_m.group(1).strip() if status_m else "BELIRLENMEDI"

        codex_res_m = re.search(r"\|\s*Codex sonucu[^\n|]+\|\s*([^|\n]+)\|", section_text)
        codex_res = codex_res_m.group(1).strip() if codex_res_m else "BEKLIYOR"

        notes_m = re.search(r"\|\s*Açık kusur[^\n|]+\|\s*([^|\n]+)\|", section_text)
        notes = notes_m.group(1).strip() if notes_m else ""

        modules.append(
            {
                "id": mod_id_clean,
                "name": mod_name.strip(),
                "phase": phase,
                "status": status,
                "codex": codex_res,
                "notes": notes,
            }
        )

    return modules


def generate_preview_html(*, mode: str = "DEMO_SYNTHETIC") -> str:
    """Renders a fully responsive, accessible HTML status dashboard dynamically from UYGULAMA_DURUM_MATRISI.md."""
    modules = parse_matrix_modules()
    matrix_hash = (
        hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest()
        if MATRIX_PATH.is_file()
        else "NOT_FOUND"
    )

    def esc(v):
        return html.escape(str(v), quote=True)

    rows = ""
    for m in modules:
        rows += f"""
        <tr>
            <td><strong>{esc(m["id"])}</strong></td>
            <td>{esc(m["name"])}</td>
            <td><span class="badge phase">{esc(m["phase"])}</span></td>
            <td><span class="badge status">{esc(m["status"])}</span></td>
            <td><span class="badge codex">{esc(m["codex"])}</span></td>
            <td>{esc(m["notes"])}</td>
        </tr>
        """

    template = (FRONTEND / "office/scenes/dashboard.html").read_text(encoding="utf-8")
    phases = sorted({m["phase"] for m in modules})
    options = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in phases)
    return (
        template.replace(
            "__OFFICE_SCRIPT__",
            (FRONTEND / "office/engine/office-preview.js").read_text(encoding="utf-8"),
        )
        .replace("__MODULE_ROWS__", rows)
        .replace("__PHASE_OPTIONS__", options)
        .replace("__MODULE_COUNT__", str(len(modules)))
        .replace("__MATRIX_HASH__", esc(matrix_hash))
    )


if __name__ == "__main__":
    out_file = FRONTEND / "previews/preview.html"
    out_file.write_text(generate_preview_html(), encoding="utf-8")
    print(f"Generated dynamic preview at {out_file}")
