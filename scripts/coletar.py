"""Coleta e processa focos de calor para a TI Andirá-Marau.

Uso normal (GitHub Actions):
    python scripts/coletar.py

Teste offline com CSVs próprios:
    python scripts/coletar.py --inpe-local pasta --firms-local pasta --agora 2026-10-17T22:00:00Z

Gera docs/data/estado.json, lido pelo site.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shapely.geometry import LineString, Point, shape
import numpy as np
import shapely
from shapely.ops import unary_union
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

INPE_10MIN = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/"
FIRMS_AREA = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
UTC = timezone.utc

INPE_PARA_SAT = {n.upper(): k for k, v in C.SATELITES.items() for n in v["inpe"]}
FIRMS_PARA_SAT = {n.upper(): k for k, v in C.SATELITES.items() for n in v["firms"]}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def baixar(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-andira-marau/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def iso(t: datetime | None) -> str | None:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def ler_data(texto: str) -> datetime | None:
    texto = (texto or "").strip().replace("T", " ").rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    return None


def km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def para_km(geom, lat0):
    """Projeção equiretangular local (km) — suficiente para uma área deste tamanho."""
    kx = 111.32 * math.cos(math.radians(lat0))
    return shapely.transform(geom, lambda xy: xy * np.array([kx, 110.57]))


def de_km(geom, lat0):
    kx = 111.32 * math.cos(math.radians(lat0))
    return shapely.transform(geom, lambda xy: xy / np.array([kx, 110.57]))


# ---------------------------------------------------------------------------
# Área
# ---------------------------------------------------------------------------
RUMOS = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]


def distancia_rumo(lat, lon):
    """Distância (km) e direção a partir da comunidade."""
    c = C.COMUNIDADE
    dist = km(c["lat"], c["lon"], lat, lon)
    dx = (lon - c["lon"]) * math.cos(math.radians(c["lat"]))
    dy = lat - c["lat"]
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return round(dist, 1), RUMOS[int((ang + 22.5) // 45) % 8]


def carregar_area():
    ti = unary_union([shape(f["geometry"]) for f in json.loads(C.TI_ARQUIVO.read_text())["features"]])
    lat0 = ti.centroid.y
    ti_km = para_km(ti, lat0)
    com = Point(C.COMUNIDADE["lon"], C.COMUNIDADE["lat"])
    circulo = para_km(com, lat0).buffer(max(C.ANEIS_KM + [C.ALERTA_KM]), quad_segs=32)
    area = de_km(unary_union([ti_km.buffer(C.ENTORNO_KM), circulo]), lat0)

    marau = None
    pts = C.ZONA_MARAU.get("pontos") or []
    if len(pts) >= 1:
        linha = Point(pts[0][1], pts[0][0]) if len(pts) == 1 else LineString([(lon, lat) for lat, lon in pts])
        marau = de_km(para_km(linha, lat0).buffer(C.ZONA_MARAU["buffer_km"]), lat0)

    municipios = []
    if C.MUNICIPIOS_ARQUIVO.exists():
        for f in json.loads(C.MUNICIPIOS_ARQUIVO.read_text())["features"]:
            municipios.append((f["properties"].get("nome"), prep(shape(f["geometry"]))))

    oeste, sul, leste, norte = area.bounds
    g = C.FAIXA_PASSAGEM_GRAUS
    faixa = (oeste - g, sul - g, leste + g, norte + g)
    return {"ti": ti, "ti_p": prep(ti), "area": area, "area_p": prep(area), "marau": marau,
            "marau_p": prep(marau) if marau is not None else None,
            "municipios": municipios, "faixa": faixa, "lat0": lat0}


def na_faixa(r, faixa):
    o, s, l, n = faixa
    return o <= r["lon"] <= l and s <= r["lat"] <= n


# ---------------------------------------------------------------------------
# Leitura das fontes
# ---------------------------------------------------------------------------
def ler_inpe(texto: str):
    regs = []
    for r in csv.DictReader(io.StringIO(texto)):
        r = {(k or "").strip().lower(): v for k, v in r.items()}
        sat = INPE_PARA_SAT.get((r.get("satelite") or r.get("satellite") or "").strip().upper())
        if not sat:
            continue
        lat, lon = num(r.get("lat") or r.get("latitude")), num(r.get("lon") or r.get("longitude"))
        t = ler_data(r.get("data") or r.get("data_hora_gmt") or r.get("datahora") or "")
        if lat is None or lon is None or t is None:
            continue
        regs.append({"sat": sat, "lat": lat, "lon": lon, "t": t, "fontes": ["INPE"],
                     "scan": None, "track": None, "conf": None, "frp": None})
    return regs


def ler_firms(texto: str):
    regs = []
    for r in csv.DictReader(io.StringIO(texto)):
        lat, lon = num(r.get("latitude")), num(r.get("longitude"))
        d, h = (r.get("acq_date") or "").strip(), (r.get("acq_time") or "").strip().zfill(4)
        sat = FIRMS_PARA_SAT.get((r.get("satellite") or "").strip().upper())
        if lat is None or lon is None or not d or not sat:
            continue
        t = ler_data(f"{d} {h[:2]}:{h[2:]}")
        if t is None:
            continue
        conf = (r.get("confidence") or "").strip()
        conf = {"l": "baixa", "n": "nominal", "h": "alta"}.get(conf.lower(), conf)
        regs.append({"sat": sat, "lat": lat, "lon": lon, "t": t, "fontes": ["FIRMS"],
                     "scan": num(r.get("scan")), "track": num(r.get("track")),
                     "conf": conf or None, "frp": num(r.get("frp"))})
    return regs


def coletar_inpe(agora, faixa, local=None):
    status = {"fonte": "INPE BDQueimadas", "ok": False, "arquivos": 0, "deteccoes": 0, "erro": None}
    textos = []
    try:
        if local:
            textos = [p.read_text(encoding="utf-8", errors="replace") for p in sorted(Path(local).glob("*.csv"))]
        else:
            indice = baixar(INPE_10MIN)
            inicio = agora - timedelta(hours=C.JANELA_H + 6)
            nomes = []
            for nome, d, h in sorted(set(re.findall(r'(focos_10min_(\d{8})_(\d{4})\.csv)', indice))):
                t = datetime.strptime(d + h, "%Y%m%d%H%M").replace(tzinfo=UTC)
                if inicio <= t <= agora + timedelta(minutes=20):
                    nomes.append(nome)

            def um(nome):
                try:
                    return baixar(INPE_10MIN + nome, timeout=45)
                except Exception:
                    return None

            with ThreadPoolExecutor(12) as ex:
                textos = [t for t in ex.map(um, nomes) if t]
            if nomes and len(textos) < len(nomes):
                status["erro"] = f"{len(nomes) - len(textos)} de {len(nomes)} arquivos falharam"
        regs = [r for tx in textos for r in ler_inpe(tx) if na_faixa(r, faixa)]
        status.update(ok=bool(textos), arquivos=len(textos), deteccoes=len(regs))
        return regs, status
    except Exception as e:  # o site continua com a outra fonte
        status["erro"] = f"{type(e).__name__}: {e}"
        return [], status


def coletar_firms(faixa, local=None):
    status = {"fonte": "NASA FIRMS", "ok": False, "deteccoes": 0, "erro": None}
    regs = []
    try:
        if local:
            for p in sorted(Path(local).glob("*.csv")):
                regs += ler_firms(p.read_text(encoding="utf-8", errors="replace"))
        else:
            chave = os.environ.get("FIRMS_MAP_KEY", "").strip()
            if not chave:
                status["erro"] = "sem chave FIRMS_MAP_KEY (site usa só o INPE)"
                return [], status
            area = ",".join(f"{v:.3f}" for v in faixa)
            for fonte in C.FIRMS_FONTES:
                try:
                    regs += ler_firms(baixar(f"{FIRMS_AREA}/{chave}/{fonte}/{area}/3", timeout=90))
                except Exception as e:
                    status["erro"] = f"{fonte}: {type(e).__name__}"
        regs = [r for r in regs if na_faixa(r, faixa)]
        status.update(ok=True, deteccoes=len(regs))
        return regs, status
    except Exception as e:
        status["erro"] = f"{type(e).__name__}: {e}"
        return [], status


def juntar_fontes(inpe, firms):
    """Une a mesma detecção vista pelo INPE e pelo FIRMS (FIRMS tem pixel real e confiança)."""
    saida = list(firms)
    for i in inpe:
        tol = max(0.5, C.SATELITES[i["sat"]]["pixel_km"] * 1.2)
        par = next((f for f in firms if f["sat"] == i["sat"]
                    and abs((f["t"] - i["t"]).total_seconds()) <= C.DUPLICATA_MIN * 60
                    and km(i["lat"], i["lon"], f["lat"], f["lon"]) <= tol), None)
        if par:
            if "INPE" not in par["fontes"]:
                par["fontes"].append("INPE")
        else:
            saida.append(i)
    # remove repetições exatas (o INPE às vezes repete linhas entre arquivos)
    vistos, unicos = set(), []
    for r in saida:
        k = (r["sat"], round(r["lat"], 4), round(r["lon"], 4), r["t"].strftime("%Y%m%d%H%M"))
        if k not in vistos:
            vistos.add(k)
            unicos.append(r)
    return unicos


# ---------------------------------------------------------------------------
# Passagens e agrupamento
# ---------------------------------------------------------------------------
def inferir_passagens(regs):
    """Para cada satélite polar, agrupa detecções da faixa em passagens."""
    por_sat = {}
    for r in regs:
        if C.SATELITES[r["sat"]]["tipo"] == "polar":
            por_sat.setdefault(r["sat"], []).append(r["t"])
    passagens = []
    for sat, ts in por_sat.items():
        ts.sort()
        grupo = [ts[0]]
        for t in ts[1:] + [None]:
            if t is not None and (t - grupo[-1]).total_seconds() <= C.PASSAGEM_INTERVALO_MIN * 60:
                grupo.append(t)
                continue
            meio = grupo[len(grupo) // 2]
            passagens.append({"sat": sat, "t": meio, "ini": grupo[0], "fim": grupo[-1], "n_faixa": len(grupo)})
            if t is not None:
                grupo = [t]
    return sorted(passagens, key=lambda p: p["t"])


def agrupar(dets):
    """União de detecções próximas no espaço e no tempo (union-find com grade)."""
    pai = list(range(len(dets)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    cel = 0.05  # ~5,5 km
    grade = {}
    for i, d in enumerate(dets):
        grade.setdefault((int(d["lat"] // cel), int(d["lon"] // cel)), []).append(i)
    for i, d in enumerate(dets):
        ci, cj = int(d["lat"] // cel), int(d["lon"] // cel)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for j in grade.get((ci + di, cj + dj), []):
                    if j <= i:
                        continue
                    e = dets[j]
                    if abs((d["t"] - e["t"]).total_seconds()) > C.AGRUP_HORAS * 3600:
                        continue
                    lim = max(C.SATELITES[d["sat"]]["pixel_km"], C.SATELITES[e["sat"]]["pixel_km"]) + C.AGRUP_FOLGA_KM
                    if km(d["lat"], d["lon"], e["lat"], e["lon"]) <= lim:
                        pai[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(len(dets)):
        grupos.setdefault(raiz(i), []).append(dets[i])
    return list(grupos.values())


def estimar_extincao(ev, passagens, ultimo_goes_faixa, agora):
    """Devolve (status, extinto_apos, extinto_ate)."""
    ultima = max(d["t"] for d in ev)
    sats_ev = {d["sat"] for d in ev}

    # 1) passagens polares depois da última detecção que não registraram o foco
    margem = timedelta(minutes=15)
    sem_registro = [p for p in passagens if p["t"] > ultima + margem
                    and (C.SATELITES[p["sat"]]["sensor"] == "VIIRS" or p["sat"] in sats_ev)]
    if len(sem_registro) >= C.EXTINCAO_PASSAGENS_POLARES:
        return "extinto", ultima, sem_registro[0]["t"], "passagens polares sem registro"

    # 2) GOES: via o foco e passou 3 h sem registrá-lo (mas continuou vendo outros)
    goes_ev = [d["t"] for d in ev if C.SATELITES[d["sat"]]["tipo"] == "geoestacionario"]
    if goes_ev and ultimo_goes_faixa:
        lim = max(goes_ev) + timedelta(hours=C.EXTINCAO_GOES_HORAS)
        if ultimo_goes_faixa >= lim and ultima + timedelta(hours=C.EXTINCAO_GOES_HORAS) <= agora:
            return "extinto", ultima, lim, "GOES sem registro por 3 h"
    return "ativo", None, None, None


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inpe-local")
    ap.add_argument("--firms-local")
    ap.add_argument("--agora", help="horário de referência UTC (teste), ex. 2026-10-17T22:00:00Z")
    ap.add_argument("--saida", default=str(C.DADOS / "estado.json"))
    a = ap.parse_args()

    agora = ler_data(a.agora) if a.agora else datetime.now(UTC).replace(microsecond=0)
    teste = bool(a.inpe_local or a.firms_local or a.agora)
    A = carregar_area()

    inpe, st_inpe = coletar_inpe(agora, A["faixa"], a.inpe_local)
    firms, st_firms = coletar_firms(A["faixa"], a.firms_local)
    regs = [r for r in juntar_fontes(inpe, firms) if r["t"] <= agora]

    inicio = agora - timedelta(hours=C.JANELA_H)
    passagens = inferir_passagens([r for r in regs if r["t"] >= inicio - timedelta(hours=12)])
    goes_faixa = [r["t"] for r in regs if C.SATELITES[r["sat"]]["tipo"] == "geoestacionario"]
    ultimo_goes = max(goes_faixa) if goes_faixa else None

    # detecções dentro da TI + entorno; 12 h extras de histórico para o agrupamento
    dets = [r for r in regs if r["t"] >= inicio - timedelta(hours=C.AGRUP_HORAS)
            and A["area_p"].contains(Point(r["lon"], r["lat"]))]
    focos = []
    for ev in agrupar(dets):
        ev.sort(key=lambda d: d["t"])
        if ev[-1]["t"] < inicio:
            continue  # terminou antes da janela
        status, apos, ate, motivo = estimar_extincao(ev, passagens, ultimo_goes, agora)
        menor = min(C.SATELITES[d["sat"]]["pixel_km"] for d in ev)
        finas = [d for d in ev if C.SATELITES[d["sat"]]["pixel_km"] <= menor * 1.5]
        lat = sum(d["lat"] for d in finas) / len(finas)
        lon = sum(d["lon"] for d in finas) / len(finas)
        p = Point(lon, lat)
        dentro = any(A["ti_p"].contains(Point(d["lon"], d["lat"])) for d in ev)
        marau = bool(A["marau_p"] and any(A["marau_p"].contains(Point(d["lon"], d["lat"])) for d in ev))
        dist_ti = 0.0 if dentro else round(para_km(p, A["lat0"]).distance(para_km(A["ti"], A["lat0"])), 1)
        mun = next((n for n, g in A["municipios"] if g.contains(p)), None)
        frps = [d["frp"] for d in ev if d["frp"] is not None]
        confs = [d["conf"] for d in ev if d["conf"]]
        focos.append({
            "lat": round(lat, 5), "lon": round(lon, 5),
            "status": status,
            "inicio": iso(ev[0]["t"]), "ultima": iso(ev[-1]["t"]),
            "extinto_apos": iso(apos), "extinto_ate": iso(ate), "motivo_extincao": motivo,
            "onde": "ti" if dentro else "entorno", "dist_ti_km": dist_ti, "marau": marau,
            "municipio": mun, "n": len(ev),
            "dist_com_km": distancia_rumo(lat, lon)[0], "rumo": distancia_rumo(lat, lon)[1],
            "alerta": distancia_rumo(lat, lon)[0] <= C.ALERTA_KM,
            "satelites": sorted({d["sat"] for d in ev}),
            "fontes": sorted({f for d in ev for f in d["fontes"]}),
            "frp_max": round(max(frps), 1) if frps else None,
            "confianca": "alta" if "alta" in confs else (confs[0] if confs else None),
            "deteccoes": [{"lat": round(d["lat"], 5), "lon": round(d["lon"], 5), "t": iso(d["t"]),
                           "sat": d["sat"], "sensor": C.SATELITES[d["sat"]]["sensor"],
                           "px": [d["scan"] or C.SATELITES[d["sat"]]["pixel_km"],
                                  d["track"] or C.SATELITES[d["sat"]]["pixel_km"]],
                           "fontes": d["fontes"], "conf": d["conf"], "frp": d["frp"]} for d in ev],
        })
    focos.sort(key=lambda f: (f["status"] != "ativo", f["dist_com_km"]))
    for i, f in enumerate(focos, 1):
        f["id"] = f"F{i:02d}"

    na_janela = [d for f in focos for d in f["deteccoes"] if d["t"] >= iso(inicio)]
    recentes = [d for d in na_janela if d["t"] >= iso(agora - timedelta(hours=C.RECENTE_H))]
    ativos = [f for f in focos if f["status"] == "ativo"]

    pass_saida = []
    for p in passagens:
        if p["t"] < inicio:
            continue
        n_area = sum(1 for d in dets if d["sat"] == p["sat"] and p["ini"] - timedelta(minutes=5) <= d["t"] <= p["fim"] + timedelta(minutes=5))
        pass_saida.append({"sat": p["sat"], "sensor": C.SATELITES[p["sat"]]["sensor"],
                           "pixel_km": C.SATELITES[p["sat"]]["pixel_km"], "hora": iso(p["t"]),
                           "n_area": n_area, "n_faixa": p["n_faixa"]})
    pass_saida.sort(key=lambda p: p["hora"], reverse=True)

    estado = {
        "gerado_em": iso(agora),
        "janela_inicio": iso(inicio),
        "janela_h": C.JANELA_H,
        "recente_h": C.RECENTE_H,
        "teste": teste,
        "area": {"nome": "TI Andirá-Marau", "entorno_km": C.ENTORNO_KM,
                 "comunidade": C.COMUNIDADE, "alerta_km": C.ALERTA_KM, "aneis_km": C.ANEIS_KM,
                 "marau": {"nome": C.ZONA_MARAU["nome"], "buffer_km": C.ZONA_MARAU["buffer_km"],
                           "pontos": C.ZONA_MARAU.get("pontos") or []}},
        "fontes": [st_inpe, st_firms],
        "resumo": {
            "ativos": len(ativos),
            "ativos_ti": sum(1 for f in ativos if f["onde"] == "ti"),
            "ativos_entorno": sum(1 for f in ativos if f["onde"] == "entorno"),
            "ativos_marau": sum(1 for f in ativos if f["marau"]),
            "ativos_alerta": sum(1 for f in ativos if f["alerta"]),
            "extintos_alerta": sum(1 for f in focos if f["status"] == "extinto" and f["alerta"]),
            "extintos": sum(1 for f in focos if f["status"] == "extinto"),
            "deteccoes": len(na_janela),
            "deteccoes_recentes": len(recentes),
        },
        "satelites": {k: {"sensor": v["sensor"], "pixel_km": v["pixel_km"], "tipo": v["tipo"],
                          "horario": v["horario"]} for k, v in C.SATELITES.items()},
        "focos": focos,
        "passagens": pass_saida,
    }
    import semaforo
    try:
        local = agora.astimezone(timezone(timedelta(hours=-4))).date()
        estado["semaforo"] = semaforo.teste(local) if teste else semaforo.coletar()
    except Exception as e:
        estado["semaforo"] = {"erro": f"{type(e).__name__}: {e}", "dias": []}
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    # contorno do entorno e da zona do Marau, desenhados pelo site
    extras = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"tipo": "entorno"},
         "geometry": json.loads(shapely.to_geojson(shapely.set_precision(A["area"].simplify(0.0005), 1e-5)))}]}
    if A["marau"] is not None:
        extras["features"].append({"type": "Feature", "properties": {"tipo": "marau"},
                                   "geometry": json.loads(shapely.to_geojson(shapely.set_precision(A["marau"].simplify(0.0003), 1e-5)))})
    (Path(a.saida).parent / "zonas.geojson").write_text(json.dumps(extras, separators=(",", ":")), encoding="utf-8")
    Path(a.saida).write_text(json.dumps(estado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    r = estado["resumo"]
    print(f"{iso(agora)}  ativos até {C.ALERTA_KM} km da comunidade: {r['ativos_alerta']}  focos ativos: {r['ativos']} (TI {r['ativos_ti']}, entorno {r['ativos_entorno']}, "
          f"Marau {r['ativos_marau']})  extintos: {r['extintos']}  detecções 48 h: {r['deteccoes']}  "
          f"passagens: {len(pass_saida)}")
    for s in estado["fontes"]:
        print(f"  {s['fonte']}: ok={s['ok']} detecções={s['deteccoes']} {s['erro'] or ''}")


if __name__ == "__main__":
    main()
