"""One user-facing progress source; source tests never imply product acceptance."""

import html
import json
from pathlib import Path

ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "docs/migration/SOURCE_TO_TARGET.json").is_file()
)
SOURCE = ROOT / "progress/ILERLEME_TABLOSU.json"


def load_progress():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    ids = [area["id"] for area in data["areas"]]
    modules = {module for area in data["areas"] for module in area["modules"]}
    if len(ids) != len(set(ids)) or modules != {f"MOD-{i:03}" for i in range(1, 17)}:
        raise ValueError("PROGRESS_MUST_COVER_FULL_ARCHITECTURE")
    return data


def estimated_total(data):
    return 5 * round(sum(a["estimated_percent"] for a in data["areas"]) / len(data["areas"]) / 5)


def acceptance_text(data):
    flow = data["first_flow_acceptance"]
    return (
        f"%{round(100 * flow['completed'] / flow['total'])} ({flow['completed']}/{flow['total']})"
    )


def render_progress_html():
    data = load_progress()
    def esc(value):
        return html.escape(str(value), quote=True)
    rows = "".join(
        "<tr>"
        + "".join(
            '<th scope="row">' + esc(area["title"]) + "</th>"
            if key == "title"
            else "<td>"
            + ("~%" + esc(area[key]) if key == "estimated_percent" else esc(area[key]))
            + "</td>"
            for key in ("title", "estimated_percent", "status", "ready", "missing", "next_step")
        )
        + "</tr>"
        for area in data["areas"]
    )
    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>İlerleme · AI Proje Ofisi</title><link rel="stylesheet" href="/tasks.css">'
        '<link rel="stylesheet" href="/progress.css"></head><body><header>'
        '<a class="brand" href="/">AI Proje Ofisi</a><nav aria-label="Ana gezinme">'
        '<a href="/progress" aria-current="page">İlerleme</a><a href="/tasks">Görevler</a>'
        '<a href="/office">Sanal ofis önizlemesi</a></nav></header><main>'
        '<h1>Proje ne durumda?</h1><p class="summary">' + esc(data["summary"]) + "</p>"
        '<p class="summary"><strong>Tahmini geliştirme: ~%'
        + str(estimated_total(data))
        + "</strong> · İlk gerçek iş akışının kabulü: "
        + esc(acceptance_text(data))
        + ".</p>"
        "<p>Son tablo güncellemesi: <time>" + esc(data["updated_at"]) + "</time>. "
        "Her alanın kendi kontrol tarihi ve kanıtı aşağıdaki ayrıntılarda bulunur.</p>"
        '<p class="legend">“Kısmen hazır”, kodun bir bölümünün hazır olduğunu söyler. '
        "“Gerçek bağlantı doğrulanmadı” veya “doğrulanmadı”, çalışan ürün kabulü olmadığı anlamına gelir. "
        "Yüzdeler kaba geliştirme tahminidir; ölçülmüş tamamlanma veya çalışan ürün oranı değildir. "
        + esc(data["estimate_note"])
        + "</p>"
        '<div class="progress-scroll" role="region" aria-label="Proje ilerleme tablosu" tabindex="0">'
        "<table><caption>Tüm mimarinin sade ilerleme tablosu</caption><thead><tr>"
        "<th>Alan</th><th>Tahmini gelişim</th><th>Durum</th><th>Hazır olan</th><th>Eksik olan</th><th>Sıradaki iş</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table></div>"
        '<details class="trace"><summary>Kontrol tarihleri ve mimari karşılıkları</summary><ul>'
        + "".join(
            "<li><strong>"
            + esc(a["title"])
            + "</strong> — "
            + esc(a["last_reviewed"])
            + "; "
            + esc(", ".join(a["modules"]))
            + ". "
            + esc(a["estimate_basis"])
            + " "
            + esc(a["evidence_scope"])
            + " Kanıt: "
            + esc(", ".join(a["evidence"]))
            + "</li>"
            for a in data["areas"]
        )
        + "</ul></details><footer>Bu tablo her anlamlı geliştirme sonunda güncellenir. "
        "Sayfa, kayıtlı son durumu gösterir; arka planda otomatik ürün testi yapmaz. "
        "İlk çalışan yazılım işi, tam projenin tamamlanması değildir.</footer></main></body></html>"
    )


def render_markdown():
    data = load_progress()
    lines = [
        "# Proje ilerleme tablosu",
        "",
        f"Son güncelleme: {data['updated_at']}",
        "",
        data["summary"],
        "",
        f"**Tahmini geliştirme: ~%{estimated_total(data)}** · İlk gerçek iş akışının kabulü: **{acceptance_text(data)}**.",
        "",
        data["estimate_note"],
        "",
        "Bu tablo 16 mimari modülün tamamını sade başlıklarla kapsar. Kaynak: `ILERLEME_TABLOSU.json`. "
        "Her anlamlı geliştirmede ilgili satır, tarihi ve kanıtı güncellenir. Kod veya parça testi, gerçek ürün kabulü değildir. "
        "Belirsiz alanlar tamamlanmış sayılmaz. Yüzdeler kullanıcının istediği kaba tahminlerdir; ölçülmüş kabul değildir.",
        "",
        "| Alan | Tahmini gelişim | Durum | Hazır olan | Eksik olan | Sıradaki iş |",
        "|---|---|---|---|---|---|",
    ]
    for area in data["areas"]:
        lines.append(
            "| "
            + " | ".join(
                (("~%" + str(area[k])) if k == "estimated_percent" else str(area[k])).replace(
                    "|", "\\|"
                )
                for k in ("title", "estimated_percent", "status", "ready", "missing", "next_step")
            )
            + " |"
        )
    lines += ["", "## Kontrol ve kanıt tarihleri", ""]
    for a in data["areas"]:
        links = ", ".join(f"[{p}](../{p})" for p in a["evidence"])
        lines.append(
            f"- **{a['title']}** — {a['last_reviewed']}; {', '.join(a['modules'])}. {a['evidence_scope']} Kanıt: {links}"
        )
    lines += [
        "",
        "İlk çalışan yazılım işi ara teslimdir; tam 16 modül/PH-00–PH-06 kapsamı korunur. "
        "G0 OPEN; first13 0/13. Bu tablo yetki veya kabul üretmez.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    (ROOT / "progress/ILERLEME_TABLOSU.md").write_text(render_markdown(), encoding="utf-8")
    print("ILERLEME_TABLOSU.md güncellendi.")
