"""Monta uma página única (HTML com dados embutidos) para prévia sem servidor.

    python scripts/montar_previa.py saida.html
"""
import json
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "docs"
css = (R / "style.css").read_text()
js = (R / "app.js").read_text()
html = (R / "index.html").read_text()
lcss = re.sub(r"url\(images/[^)]*\)", "none", (R / "vendor/leaflet.css").read_text())

# tema: padrão com data-theme
m = re.search(r"@media \(prefers-color-scheme: dark\) \{\n  :root \{(.*?)\n  \}\n\}", css, re.S)
extra_escuro = ("\n    --aviso-bg:#3a2c12;--aviso-fg:#f6dfa8;--aviso-bd:#5b4520;--teste-bg:#4a1b14;"
                "--teste-fg:#ffc9bf;--teste-bd:#7a2c22;--mapa-bg:#1d2a22;")
escuro = m.group(1) + extra_escuro
css = css.replace(m.group(0), '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {' + escuro
                  + '\n  }\n}\n:root[data-theme="dark"] {' + escuro + "\n}")
css = css.replace("  --sombra: 0 1px 2px rgb(0 0 0 / .06), 0 4px 16px rgb(0 0 0 / .05);",
                  "  --sombra: 0 1px 2px rgb(0 0 0 / .06), 0 4px 16px rgb(0 0 0 / .05);\n"
                  "  --aviso-bg:#fff1d6;--aviso-fg:#5a3a00;--aviso-bd:#f0d199;--teste-bg:#ffe1dc;--teste-fg:#6b1308;"
                  "--teste-bd:#f2b3a8;--mapa-bg:#dfe7d8;\n"
                  '  --fonte-titulo:"Archivo", system-ui, sans-serif;\n'
                  '  --fonte-texto:"Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;')
css = re.sub(r"@media \(prefers-color-scheme: dark\) \{\n  \.aviso \{.*?\n\}\n", "", css, flags=re.S)
css = css.replace("background: #fff1d6; color: #5a3a00; border: 1px solid #f0d199;",
                  "background: var(--aviso-bg); color: var(--aviso-fg); border: 1px solid var(--aviso-bd);")
css = css.replace(".aviso.teste { background: #ffe1dc; color: #6b1308; border-color: #f2b3a8; font-weight: 600; }",
                  ".aviso.teste { background: var(--teste-bg); color: var(--teste-fg); border-color: var(--teste-bd); font-weight: 600; }")
css = css.replace('font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;', "font: 16px/1.5 var(--fonte-texto);")
css = css.replace("h1 { margin", "h1 { font-family: var(--fonte-titulo); text-wrap: balance; margin")
css = css.replace(".bloco h2 { margin: 0; font-size: 18px; }", ".bloco h2 { margin: 0; font-size: 18px; font-family: var(--fonte-titulo); }")
lados = "padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));"
css = css.replace("padding: max(20px, env(safe-area-inset-top)) 16px 22px;", "padding-block: 20px 22px; " + lados)
css = css.replace("main { padding: 12px 16px 24px; }", "main { padding-block: 12px 24px; " + lados + " }")
css = css.replace(".avisos { padding: 12px 16px 0; }", ".avisos { padding-block: 12px 0; " + lados + " }")
css = css.replace(".rodape { padding: 0 16px max(24px, env(safe-area-inset-bottom));", ".rodape { padding-block: 0 24px; " + lados)
css = css.replace("background: #cfd8cc; }", "background: var(--mapa-bg); }")
css += ("\n.leaflet-container { background: var(--mapa-bg); }\n.cartao b { font-family: var(--fonte-titulo); }\n"
        "@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }\n")

dados = {k: json.loads((R / "data" / f).read_text()) for k, f in
         [("estado", "estado.json"), ("ti", "ti.geojson"), ("mun", "municipios.geojson"), ("zonas", "zonas.geojson"),
          ("ar", "ar.json"), ("lst", "lst.json"), ("lst_ti", "lst_ti.json")] if (R / "data" / f).exists()}
i, f = js.index("  Promise.all(["), js.index(".then(([estado, ti, mun, zonas, ar, lst, lstTi]) => {")
js = js[:i] + "  Promise.resolve([DADOS.estado, DADOS.ti, DADOS.mun, DADOS.zonas, DADOS.ar || null, DADOS.lst || null, DADOS.lst_ti || null])" + js[f:]
COM_MAPA = "--com-mapa" in sys.argv   # arquivo avulso: o navegador carrega o mapa de fundo
if not COM_MAPA:
    a, b = js.index("    fundos.mapa = L.tileLayer"), js.index('    const verde = css("--ti");')
    js = js[:a] + js[b:]

corpo = html[html.index("<body>") + 6:html.index('<script src="vendor/leaflet.js">')]
if not COM_MAPA:
  corpo = re.sub(r'\s*<div class="seg" role="group" aria-label="Fundo do mapa">.*?</div>', "", corpo, flags=re.S)
  corpo = corpo.replace('<div id="mapa" role="region" aria-label="Mapa dos focos"></div>',
                      '<div id="mapa" role="region" aria-label="Mapa dos focos"></div>\n    <p class="nota">Prévia sem mapa de fundo: '
                      "rios e imagem de satélite aparecem na versão publicada no GitHub Pages. Cada foco tem link para o "
                      "Google Maps e para a imagem Sentinel-2.</p>")

if COM_MAPA:
    saida_cab = '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
else:
    saida_cab = ""
import base64
arquivos = {}
for n in ("lst.png", "lst_valor.png", "lst_ti.png", "lst_ti_valor.png"):
    if (R / "data" / n).exists():
        arquivos[n] = "data:image/png;base64," + base64.b64encode((R / "data" / n).read_bytes()).decode()
for nome in ("ufam", "vsm"):
    b64 = base64.b64encode((R / "img" / f"{nome}.png").read_bytes()).decode()
    corpo = corpo.replace(f'src="img/{nome}.png"', f'src="data:image/png;base64,{b64}"')
saida = saida_cab + f"""<title>Focos de calor Andirá-Marau</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;750&family=Atkinson+Hyperlegible:wght@400;700&display=swap">
<style>
{lcss}
{css}
</style>
{corpo}
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const DADOS = {json.dumps(dados, ensure_ascii=False, separators=(',', ':'))};
window.ARQUIVOS = {json.dumps(arquivos)};
{js}
</script>
"""
Path(sys.argv[1]).write_text(saida)
print(len(saida))
