"""Semáforo de queima: previsão do tempo para a comunidade → bom / ruim / não queime.

Fonte: Open-Meteo (gratuito, sem chave). Os limites ficam em config.py (SEMAFORO).
São uma regra prática para apoiar a decisão da comunidade, não uma autorização.
"""
import json
import urllib.request
from datetime import date, datetime, timedelta

import config as C

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&hourly=relative_humidity_2m,wind_speed_10m,temperature_2m,precipitation"
       "&daily=precipitation_sum&past_days=45&forecast_days=4&timezone=America%2FManaus")
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def classificar(ur_min, vento_max, dias_sem_chuva, chuva_dia):
    L = C.SEMAFORO
    if chuva_dia >= 5:
        dias_sem_chuva = 0  # chuva no próprio dia molha o mato
    motivos = []
    if ur_min < L["ur_proibido"]:
        motivos.append(f"ar muito seco ({ur_min:.0f}% de umidade)")
    if vento_max > L["vento_proibido_kmh"]:
        motivos.append(f"vento forte ({vento_max:.0f} km/h)")
    if dias_sem_chuva >= L["seca_proibido_dias"] and ur_min < L["ur_ruim"]:
        motivos.append(f"{dias_sem_chuva} dias sem chuva")
    if motivos:
        return "nao", motivos
    if ur_min < L["ur_ruim"]:
        motivos.append(f"ar seco ({ur_min:.0f}% de umidade)")
    if vento_max > L["vento_ruim_kmh"]:
        motivos.append(f"vento moderado ({vento_max:.0f} km/h)")
    if dias_sem_chuva >= L["seca_ruim_dias"]:
        motivos.append(f"{dias_sem_chuva} dias sem chuva")
    if motivos:
        return "ruim", motivos
    if chuva_dia >= 5:
        return "bom", [f"chuva prevista ({chuva_dia:.0f} mm), mato úmido"]
    return "bom", ["umidade e vento dentro do limite"]


def montar(horas, chuva_diaria, hoje):
    """horas: lista de dicts {t: datetime local, ur, vento, temp}; chuva_diaria: {date: mm}."""
    dias = []
    for k in range(4):
        d = hoje + timedelta(days=k)
        h = [x for x in horas if x["t"].date() == d]
        if not h:
            continue
        tarde = [x for x in h if 10 <= x["t"].hour <= 18]
        ur_min = min(x["ur"] for x in tarde)
        vento_max = max(x["vento"] for x in tarde)
        temp_max = max(x["temp"] for x in h)
        # dias seguidos sem chuva relevante até a véspera
        seca, dd = 0, d - timedelta(days=1)
        while chuva_diaria.get(dd, 99) < C.SEMAFORO["chuva_minima_mm"]:
            seca += 1
            dd -= timedelta(days=1)
        nivel, motivos = classificar(ur_min, vento_max, seca, chuva_diaria.get(d, 0))
        janela = None
        if nivel != "nao":
            cand = [x for x in h if 15 <= x["t"].hour <= 17 and x["ur"] >= C.SEMAFORO["ur_proibido"]]
            if cand:
                m = min(cand, key=lambda x: (x["vento"], -x["ur"]))
                janela = {"inicio": f"{m['t'].hour:02d}h", "fim": f"{m['t'].hour + 2:02d}h",
                          "ur": round(m["ur"]), "vento": round(m["vento"])}
        dias.append({"data": d.isoformat(), "dia": "hoje" if k == 0 else ("amanhã" if k == 1 else DIAS[d.weekday()]),
                     "nivel": nivel, "motivos": motivos, "ur_min": round(ur_min), "vento_max": round(vento_max),
                     "temp_max": round(temp_max), "dias_sem_chuva": seca,
                     "chuva_mm": round(chuva_diaria.get(d, 0), 1), "janela": janela})
    return {"fonte": "Open-Meteo", "local": C.COMUNIDADE["nome"], "limites": C.SEMAFORO, "dias": dias}


def coletar():
    c = C.COMUNIDADE
    req = urllib.request.Request(URL.format(lat=c["lat"], lon=c["lon"]), headers={"User-Agent": "monitor-andira-marau/1.0"})
    j = json.loads(urllib.request.urlopen(req, timeout=40).read())
    H = j["hourly"]
    horas = [{"t": datetime.fromisoformat(t), "ur": u, "vento": v, "temp": tp}
             for t, u, v, tp in zip(H["time"], H["relative_humidity_2m"], H["wind_speed_10m"], H["temperature_2m"])
             if u is not None and v is not None]
    chuva = {date.fromisoformat(t): (p or 0) for t, p in zip(j["daily"]["time"], j["daily"]["precipitation_sum"])}
    hoje = datetime.now().astimezone().date()
    return montar(horas, chuva, hoje)


def teste(hoje):
    """Valores fictícios de época seca, para conferir o site."""
    import math
    perfil = [  # (UR mínima à tarde, vento máximo, chuva do dia)
        (27, 17, 0), (36, 11, 0), (41, 13, 0), (58, 8, 14),
    ]
    horas, chuva = [], {}
    for k, (urm, vm, mm) in enumerate(perfil):
        d = hoje + timedelta(days=k)
        chuva[d] = mm
        for hh in range(24):
            f = (math.cos((hh - 14) / 24 * 2 * math.pi) + 1) / 2   # 1 às 14h, 0 às 2h
            horas.append({"t": datetime(d.year, d.month, d.day, hh), "ur": 95 - (95 - urm) * f,
                          "vento": 3 + (vm - 3) * f * (0.8 if hh >= 16 else 1), "temp": 24 + 11 * f})
    for k in range(1, 46):
        chuva[hoje - timedelta(days=k)] = 0 if k <= 23 else 12
    r = montar(horas, chuva, hoje)
    r["fonte"] = "valores de teste"
    return r
