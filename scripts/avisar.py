"""Avisa no WhatsApp (e/ou Telegram) quando aparece foco ativo perto da comunidade.

WhatsApp — API oficial da Meta (WhatsApp Cloud API). Segredos no GitHub
(Settings → Secrets and variables → Actions):
  WHATSAPP_TOKEN     token permanente (usuário do sistema no Meta Business)
  WHATSAPP_PHONE_ID  "Phone number ID" do número do projeto
  WHATSAPP_PARA      números que recebem, com DDI e DDD, separados por vírgula
                     ex.: 5592991234567,5592998765432
Variáveis (opcionais, em Variables):
  WHATSAPP_MODELO    nome do modelo de mensagem aprovado (padrão: alerta_foco_calor)
  WHATSAPP_IDIOMA    idioma do modelo (padrão: pt_BR)
  SITE_URL           endereço do site (padrão: https://valdiek.github.io/monitor-marau/)

O modelo precisa ter 4 variáveis no corpo:
  {{1}} quantidade de focos · {{2}} comunidade · {{3}} detalhes · {{4}} link do mapa

Telegram (opcional): TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.

Cada foco é avisado uma vez só; os já avisados ficam em docs/data/avisados.json.
Teste do envio:  python scripts/avisar.py --teste
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

MANAUS = timezone(timedelta(hours=-4))
REG = C.DADOS / "avisados.json"
SITE = os.environ.get("SITE_URL", "").strip() or "https://valdiek.github.io/monitor-marau/"


def env(n, padrao=""):
    return (os.environ.get(n) or "").strip() or padrao


def hora(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(MANAUS).strftime("%d/%m %Hh%M")


def km(v):
    return str(v).replace(".", ",")


def chave(f):
    # o id muda entre atualizações; a chave usa a 1ª detecção e a posição arredondada
    return f"{f['inicio']}|{f['lat']:.2f}|{f['lon']:.2f}"


def detalhes(focos):
    """Uma linha só (o WhatsApp não aceita quebra de linha nas variáveis do modelo)."""
    partes = []
    for f in sorted(focos, key=lambda x: x["dist_com_km"])[:4]:
        partes.append(f"{km(f['dist_com_km'])} km a {f['rumo']}, desde {hora(f['inicio'])} "
                      f"({f['lat']:.4f}, {f['lon']:.4f})")
    if len(focos) > 4:
        partes.append(f"e mais {len(focos) - 4}")
    return "; ".join(partes)


# ---------------------------------------------------------------- WhatsApp
def whatsapp(focos, teste=False):
    token, phone_id, para = env("WHATSAPP_TOKEN"), env("WHATSAPP_PHONE_ID"), env("WHATSAPP_PARA")
    if not (token and phone_id and para):
        print("WhatsApp não configurado.")
        return None
    modelo, idioma = env("WHATSAPP_MODELO", "alerta_foco_calor"), env("WHATSAPP_IDIOMA", "pt_BR")
    versao = env("WHATSAPP_API_VERSAO", "v22.0")
    valores = [str(len(focos)), C.COMUNIDADE["nome"],
               "TESTE do sistema, não é foco real" if teste else detalhes(focos), SITE]
    ok = 0
    for numero in [n.strip().lstrip("+").replace(" ", "").replace("-", "") for n in para.split(",") if n.strip()]:
        corpo = {"messaging_product": "whatsapp", "to": numero, "type": "template",
                 "template": {"name": modelo, "language": {"code": idioma},
                              "components": [{"type": "body",
                                              "parameters": [{"type": "text", "text": v} for v in valores]}]}}
        req = urllib.request.Request(f"https://graph.facebook.com/{versao}/{phone_id}/messages",
                                     data=json.dumps(corpo).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            ok += 1
            print(f"WhatsApp: enviado para …{numero[-4:]}")
        except urllib.error.HTTPError as e:
            print(f"WhatsApp: falhou para …{numero[-4:]}: {e.code} {e.read().decode(errors='replace')[:300]}")
        except urllib.error.URLError as e:
            print(f"WhatsApp: sem conexão com a Meta: {e.reason}")
    return ok > 0


# ---------------------------------------------------------------- Telegram
def telegram(focos, teste=False):
    token, chat = env("TELEGRAM_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None
    com = C.COMUNIDADE["nome"]
    linhas = [("[TESTE] " if teste else "") + f"🔥 {len(focos)} foco(s) de calor a até {C.ALERTA_KM} km da {com}", ""]
    for f in sorted(focos, key=lambda x: x["dist_com_km"]):
        gm = f"https://www.google.com/maps/search/?api=1&query={f['lat']},{f['lon']}"
        linhas.append(f"• {km(f['dist_com_km'])} km a {f['rumo']} · desde {hora(f['inicio'])} · "
                      f"{f['n']} detecção(ões), {', '.join(f['satelites'])}\n  {gm}")
    linhas += ["", f"Mapa: {SITE}", "",
               "Confirme em campo antes de agir: o ponto pode estar a algumas centenas de metros do fogo real."]
    dados = urllib.parse.urlencode({"chat_id": chat, "text": "\n".join(linhas),
                                    "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=30).read()
        print("Telegram: enviado")
        return True
    except urllib.error.HTTPError as e:
        print(f"Telegram: falhou: {e.code}")
        return False
    except urllib.error.URLError as e:
        print(f"Telegram: sem conexão: {e.reason}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true", help="envia uma mensagem de teste, sem foco real")
    a = ap.parse_args()

    if a.teste:
        exemplo = [{"dist_com_km": 3.2, "rumo": "nordeste", "inicio": datetime.now(timezone.utc).isoformat(),
                    "lat": C.COMUNIDADE["lat"] + .02, "lon": C.COMUNIDADE["lon"] + .02, "n": 2, "satelites": ["NOAA-20"]}]
        r = [whatsapp(exemplo, teste=True), telegram(exemplo, teste=True)]
        if not any(r):
            sys.exit("Nenhum aviso de teste foi enviado. Confira os segredos e o log acima.")
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
    r = [whatsapp(novos), telegram(novos)]
    if any(r):  # marca como avisado se pelo menos um canal funcionou
        agora = datetime.now(timezone.utc).isoformat()
        for f in novos:
            avisados[chave(f)] = agora
        print(f"Aviso enviado: {len(novos)} foco(s).")
    elif all(x is None for x in r):
        print(f"{len(novos)} foco(s) perto da comunidade, mas nenhum canal de aviso está configurado.")
    REG.write_text(json.dumps(avisados))


if __name__ == "__main__":
    main()
