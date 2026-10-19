"""Qualidade do ar (fumaça): PM2.5 do modelo CAMS, via Open-Meteo (sem chave).

O CAMS é um modelo (~40 km), não um medidor: mostra a fumaça da região, não a de
uma roça específica. Gera docs/data/ar.json com:
  - série horária na comunidade (últimas 48 h + próximos 3 dias)
  - grade de PM2.5 ao redor, para a camada "Fumaça" do mapa (hora atual e máximo das próximas 24 h)

Uso: python scripts/ar.py   |   python scripts/ar.py --teste
"""
import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

API = "https://air-quality-api.open-meteo.com/v1/air-quality"
MANAUS = timezone(timedelta(hours=-4))
# Faixas do IQAr (CETESB) para PM2.5, µg/m³
FAIXAS = [(15, "boa", "Boa"), (50, "moderada", "Moderada"), (75, "ruim", "Ruim"),
          (125, "muito_ruim", "Muito ruim"), (1e9, "pessima", "Péssima")]


def faixa(v):
    for lim, cod, nome in FAIXAS:
        if v is not None and v <= lim:
            return cod, nome
    return None, "sem dado"


def baixar(params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "monitor-andira-marau/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def grade_pontos():
    c = C.COMUNIDADE
    r, p = C.AR["grade_raio_km"], C.AR["grade_passo_graus"]
    nlat = math.ceil(r / 110.57 / p)
    nlon = math.ceil(r / (111.32 * math.cos(math.radians(c["lat"]))) / p)
    lats = [round(c["lat"] + i * p, 4) for i in range(-nlat, nlat + 1)]
    lons = [round(c["lon"] + j * p, 4) for j in range(-nlon, nlon + 1)]
    return lats, lons


def montar(serie_t, serie_pm, serie_pm10, serie_co, lats, lons, grade_agora, grade_max, agora, fonte):
    pontos = [{"t": t, "pm25": pm, "pm10": p10, "co": co}
              for t, pm, p10, co in zip(serie_t, serie_pm, serie_pm10, serie_co)]
    hora = agora.astimezone(MANAUS).strftime("%Y-%m-%dT%H:00")
    atual = next((p for p in pontos if p["t"] == hora), None) or next((p for p in reversed(pontos) if p["t"] <= hora and p["pm25"] is not None), None)
    futuro = [p for p in pontos if p["t"] > hora][:24]
    pico = max(futuro, key=lambda p: p["pm25"] or 0) if futuro else None
    ult24 = [p["pm25"] for p in pontos if p["t"] <= hora and p["pm25"] is not None][-24:]
    media24 = round(sum(ult24) / len(ult24), 1) if ult24 else None
    cod, nome = faixa(media24 if media24 is not None else (atual or {}).get("pm25"))
    return {
        "gerado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"), "fonte": fonte, "modelo": "CAMS (Copernicus)",
        "local": C.COMUNIDADE["nome"], "hora_local": hora,
        "atual": atual, "media24": media24, "nivel": cod, "nivel_nome": nome,
        "pico24": pico, "pico_nivel": faixa(pico["pm25"])[1] if pico else None,
        "faixas": [{"ate": f[0] if f[0] < 1e9 else None, "cod": f[1], "nome": f[2]} for f in FAIXAS],
        "serie": pontos,
        "grade": {"lats": lats, "lons": lons, "passo": C.AR["grade_passo_graus"],
                  "agora": grade_agora, "max24": grade_max},
    }


def real():
    c = C.COMUNIDADE
    j = baixar({"latitude": c["lat"], "longitude": c["lon"], "hourly": "pm2_5,pm10,carbon_monoxide",
                "past_days": 2, "forecast_days": 4, "timezone": "America%2FManaus"})
    h = j["hourly"]
    lats, lons = grade_pontos()
    la = ",".join(str(x) for x in lats for _ in lons)
    lo = ",".join(str(y) for _ in lats for y in lons)
    g = baixar({"latitude": la, "longitude": lo, "hourly": "pm2_5", "forecast_days": 2,
                "timezone": "America%2FManaus"})
    if isinstance(g, dict):
        g = [g]
    agora = datetime.now(timezone.utc)
    hora = agora.astimezone(MANAUS).strftime("%Y-%m-%dT%H:00")
    g_agora, g_max = [], []
    for item in g:
        ts, vs = item["hourly"]["time"], item["hourly"]["pm2_5"]
        idx = ts.index(hora) if hora in ts else 0
        g_agora.append(vs[idx])
        prox = [v for v in vs[idx:idx + 24] if v is not None]
        g_max.append(round(max(prox), 1) if prox else None)
    n = len(lons)
    g_agora = [g_agora[i * n:(i + 1) * n] for i in range(len(lats))]
    g_max = [g_max[i * n:(i + 1) * n] for i in range(len(lats))]
    return montar(h["time"], h["pm2_5"], h["pm10"], h["carbon_monoxide"], lats, lons, g_agora, g_max, agora, "Open-Meteo")


def teste(agora):
    loc = agora.astimezone(MANAUS).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    ts, pm, p10, co = [], [], [], []
    for k in range(-48, 72):
        t = loc + timedelta(hours=k)
        base = 38 + 25 * math.exp(-((k - 10) / 14) ** 2) - 12 * (k > 40)
        v = max(4, base + 10 * math.sin((t.hour - 16) / 24 * 2 * math.pi))
        ts.append(t.strftime("%Y-%m-%dT%H:00")); pm.append(round(v, 1)); p10.append(round(v * 1.4, 1)); co.append(round(180 + v * 6))
    lats, lons = grade_pontos()
    c = C.COMUNIDADE
    ga = [[round(max(3, 30 + 35 * math.exp(-(((la - c["lat"] + .25) / .3) ** 2 + ((lo - c["lon"] - .3) / .35) ** 2))), 1)
           for lo in lons] for la in lats]
    gm = [[round(v * 1.3, 1) for v in row] for row in ga]
    r = montar(ts, pm, p10, co, lats, lons, ga, gm, agora, "valores de teste")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true")
    ap.add_argument("--agora")
    a = ap.parse_args()
    agora = datetime.fromisoformat(a.agora.replace("Z", "+00:00")) if a.agora else datetime.now(timezone.utc)
    try:
        r = teste(agora) if a.teste else real()
    except Exception as e:
        r = {"erro": f"{type(e).__name__}: {e}", "gerado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ")}
    (C.DADOS / "ar.json").write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print({k: r.get(k) for k in ("erro", "media24", "nivel_nome", "atual", "pico_nivel")})


if __name__ == "__main__":
    main()
