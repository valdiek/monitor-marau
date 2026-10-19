"""Envia alerta no Telegram quando aparece foco ativo perto da comunidade.

Precisa de dois segredos no GitHub (Settings → Secrets and variables → Actions):
  TELEGRAM_TOKEN    token do bot (criado com o @BotFather)
  TELEGRAM_CHAT_ID  id do grupo ou da pessoa que recebe os avisos
  SITE_URL          (opcional) endereço do site, para o link na mensagem

Cada foco é avisado uma vez só; os já avisados ficam em docs/data/avisados.json.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

MANAUS = timezone(timedelta(hours=-4))
REG = C.DADOS / "avisados.json"


def hora(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(MANAUS).strftime("%d/%m %Hh%M")


def chave(f):
    # o id muda entre atualizações; a chave usa a 1ª detecção e a posição arredondada
    return f"{f['inicio']}|{f['lat']:.2f}|{f['lon']:.2f}"


def main():
    token, chat = os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("Telegram não configurado; nenhum aviso enviado.")
        return
    estado = json.loads((C.DADOS / "estado.json").read_text(encoding="utf-8"))
    if estado.get("teste"):
        print("Dados de teste; nenhum aviso enviado.")
        return
    avisados = json.loads(REG.read_text()) if REG.exists() else {}
    limite = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    avisados = {k: v for k, v in avisados.items() if v >= limite}

    novos = [f for f in estado["focos"] if f["status"] == "ativo" and f["alerta"] and chave(f) not in avisados]
    if not novos:
        print("Nenhum foco novo perto da comunidade.")
        REG.write_text(json.dumps(avisados))
        return

    com = C.COMUNIDADE["nome"]
    linhas = [f"🔥 {len(novos)} foco(s) de calor a até {C.ALERTA_KM} km da {com}", ""]
    for f in sorted(novos, key=lambda x: x["dist_com_km"]):
        gm = f"https://www.google.com/maps/search/?api=1&query={f['lat']},{f['lon']}"
        linhas.append(f"• {str(f['dist_com_km']).replace('.', ',')} km a {f['rumo']} · desde {hora(f['inicio'])} · "
                      f"{f['n']} detecção(ões), {', '.join(f['satelites'])}\n  {gm}")
    if os.environ.get("SITE_URL"):
        linhas += ["", f"Mapa: {os.environ['SITE_URL']}"]
    linhas += ["", "Confirme em campo antes de agir: o ponto pode estar a algumas centenas de metros do fogo real."]

    dados = urllib.parse.urlencode({"chat_id": chat, "text": "\n".join(linhas),
                                    "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=30).read()
    agora = datetime.now(timezone.utc).isoformat()
    for f in novos:
        avisados[chave(f)] = agora
    REG.write_text(json.dumps(avisados))
    print(f"Aviso enviado: {len(novos)} foco(s).")


if __name__ == "__main__":
    main()
