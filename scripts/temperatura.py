"""Temperatura da superfície (Landsat 8/9, 30 m) ao redor da comunidade.

Monta um mosaico com o pixel sem nuvem mais recente de cada lugar, a partir das
cenas Landsat Collection 2 Nível 2 (banda ST_B10) do Microsoft Planetary Computer.

Gera em docs/data/:
  lst.png        imagem colorida para o mapa (transparente onde não há dado)
  lst_valor.png  mesma grade em tons de cinza: valor = (°C - MIN) * 4 (0 = sem dado)
  lst.json       limites, escala, cenas usadas, cobertura e estatísticas

Uso: python scripts/temperatura.py [--dias 32]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
T_MIN, T_MAX = C.TEMPERATURA["escala_c"]
# rampa de cores (°C → RGB): azul frio, verde floresta, amarelo, laranja, vermelho, vinho
RAMPA = [(20, (49, 54, 149)), (24, (69, 117, 180)), (27, (116, 173, 209)), (29, (171, 217, 233)),
         (31, (254, 224, 144)), (34, (253, 174, 97)), (37, (244, 109, 67)), (41, (215, 48, 39)),
         (46, (128, 0, 38))]


def colorir(t):
    xs = np.array([p[0] for p in RAMPA], float)
    cores = np.array([p[1] for p in RAMPA], float)
    rgb = np.stack([np.interp(t, xs, cores[:, k]) for k in range(3)], axis=-1)
    return rgb.astype(np.uint8)


def salvar_colorido(cod, destino):
    """PNG com paleta (bem menor que RGBA): índice 0 transparente, 1..255 = (°C - MIN) * 4 + 1."""
    temps = (np.arange(256) - 1) / 4 + T_MIN
    pal = colorir(np.clip(temps, T_MIN, T_MAX))
    pal[0] = (0, 0, 0)
    im = Image.fromarray(cod, "P")
    im.putpalette(pal.flatten().tolist())
    im.save(destino, optimize=True, transparency=0)


def caixa():
    c = C.COMUNIDADE
    r = C.TEMPERATURA["raio_km"]
    dlat = r / 110.57
    dlon = r / (111.32 * math.cos(math.radians(c["lat"])))
    return (c["lon"] - dlon, c["lat"] - dlat, c["lon"] + dlon, c["lat"] + dlat)


def caixa_ti():
    from shapely.geometry import shape
    from shapely.ops import unary_union
    g = unary_union([shape(f["geometry"]) for f in json.loads(C.TI_ARQUIVO.read_text())["features"]])
    lat0 = g.centroid.y
    d = C.ENTORNO_KM
    o, s_, l, n = g.bounds
    dlat, dlon = d / 110.57, d / (111.32 * math.cos(math.radians(lat0)))
    # área = TI + entorno (aprox. por buffer em graus, só para o recorte visual)
    area = g.buffer(max(dlat, dlon), quad_segs=8)
    return (o - dlon, s_ - dlat, l + dlon, n + dlat), area


def gerar(cat, bbox, res, prefixo, dias, recorte=None):
    from odc.stac import load
    fim = datetime.now(timezone.utc)
    inicio = fim - timedelta(days=dias)
    itens = list(cat.search(
        collections=["landsat-c2-l2"], bbox=bbox,
        datetime=f"{inicio:%Y-%m-%d}/{fim:%Y-%m-%d}",
        query={"platform": {"in": ["landsat-8", "landsat-9"]}, "eo:cloud_cover": {"lt": 90}},
    ).items())
    print(f"[{prefixo}] {len(itens)} cenas Landsat de {inicio:%d/%m} a {fim:%d/%m}")
    saida = C.DADOS
    meta = {"gerado_em": fim.strftime("%Y-%m-%dT%H:%M:%SZ"), "bounds": [[bbox[1], bbox[0]], [bbox[3], bbox[2]]],
            "escala_c": [T_MIN, T_MAX], "rampa": [[t, "#%02x%02x%02x" % c] for t, c in RAMPA],
            "janela_dias": dias, "resolucao_m": round(res * 111320), "cenas": [], "cobertura_pct": 0}
    if not itens:
        meta["erro"] = "nenhuma cena Landsat no período"
        (saida / f"{prefixo}.json").write_text(json.dumps(meta, ensure_ascii=False))
        return

    ds = load(itens, bands=["lwir11", "qa_pixel"], bbox=bbox, crs="EPSG:4326",
              resolution=res, groupby="solar_day", chunks={}, resampling={"lwir11": "bilinear", "*": "nearest"})
    ds = ds.compute()
    datas = [np.datetime_as_string(t, unit="D") for t in ds.time.values]

    ny, nx = ds.sizes["latitude"], ds.sizes["longitude"]
    temp = np.full((ny, nx), np.nan, np.float32)
    origem = np.full((ny, nx), -1, np.int16)
    # da cena mais recente para a mais antiga: preenche só onde ainda não há valor
    ordem = np.argsort(ds.time.values)[::-1]
    for k in ordem:
        st = ds["lwir11"].isel(time=k).values.astype(np.float32)
        qa = ds["qa_pixel"].isel(time=k).values.astype(np.uint16)
        ruim = qa & 0b11111  # preenchimento, nuvem dilatada, cirrus, nuvem, sombra
        ok = (st > 0) & (ruim == 0)
        t = st * 0.00341802 + 149.0 - 273.15
        ok &= (t > 5) & (t < 75)
        novo = ok & np.isnan(temp)
        temp[novo] = t[novo]
        origem[novo] = k
    lat = ds.latitude.values
    lon = ds.longitude.values
    if lat[0] < lat[-1]:  # garante norte em cima
        temp, origem, lat = temp[::-1], origem[::-1], lat[::-1]
    if recorte is not None:
        from shapely import contains_xy
        xx, yy = np.meshgrid(lon, lat)
        fora = ~contains_xy(recorte, xx, yy)
        temp[fora] = np.nan
        origem[fora] = -1
        dentro = ~fora
    else:
        dentro = np.ones_like(temp, bool)
    validos = ~np.isnan(temp)
    meta["cobertura_pct"] = round(100 * validos.sum() / max(1, dentro.sum()), 1)
    print(f"[{prefixo}] cobertura sem nuvem: {meta['cobertura_pct']}%  ({nx}x{ny} px)")

    plataformas, horas = {}, {}
    for it in itens:
        d = it.datetime.strftime("%Y-%m-%d")
        plataformas.setdefault(d, set()).add(it.properties.get("platform", "").replace("landsat-", "Landsat "))
        horas.setdefault(d, it.datetime.strftime("%H:%M"))
    for k in ordem:
        n = int((origem == k).sum())
        if n:
            meta["cenas"].append({"indice": int(k), "data": datas[k], "hora_utc": horas.get(datas[k]),
                                  "satelite": " / ".join(sorted(plataformas.get(datas[k], []))),
                                  "pct": round(100 * n / validos.sum(), 1)})
    if validos.any():
        v = temp[validos]
        meta["estat"] = {"min": round(float(v.min()), 1), "p50": round(float(np.median(v)), 1),
                         "p95": round(float(np.percentile(v, 95)), 1), "max": round(float(v.max()), 1)}
        c = C.COMUNIDADE
        iy, ix = int(np.abs(lat - c["lat"]).argmin()), int(np.abs(lon - c["lon"]).argmin())
        jan = temp[max(0, iy - 3):iy + 4, max(0, ix - 3):ix + 4]
        if np.isfinite(jan).any():
            meta["estat"]["comunidade"] = round(float(np.nanmedian(jan)), 1)
    # limites reais da grade (bordas dos pixels)
    meta["bounds"] = [[float(lat[-1] - res / 2), float(lon[0] - res / 2)], [float(lat[0] + res / 2), float(lon[-1] + res / 2)]]

    # valores (canal R) e cena (canal G) para leitura ao tocar no mapa
    cod = np.where(validos, np.clip(np.round((np.nan_to_num(temp, nan=T_MIN) - T_MIN) * 4) + 1, 1, 255), 0).astype(np.uint8)
    cena = np.where(validos, np.clip(origem + 1, 0, 255), 0).astype(np.uint8)
    Image.fromarray(np.stack([cod, cena, np.zeros_like(cod)], -1), "RGB").save(saida / f"{prefixo}_valor.png", optimize=True)
    salvar_colorido(cod, saida / f"{prefixo}.png")
    meta["tamanho_px"] = [nx, ny]
    meta["codigo"] = {"canal_r": f"(°C - {T_MIN}) * 4 + 1; 0 = sem dado", "canal_g": "índice da cena + 1"}
    (saida / f"{prefixo}.json").write_text(json.dumps(meta, ensure_ascii=False))
    print(json.dumps({k: meta[k] for k in ("cobertura_pct", "estat", "cenas") if k in meta}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=C.TEMPERATURA["janela_dias"])
    a = ap.parse_args()

    import planetary_computer
    import pystac_client
    cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)

    # 1) comunidade, 30 m
    gerar(cat, caixa(), C.TEMPERATURA["resolucao_graus"], "lst", a.dias)
    # 2) TI inteira + entorno, ~90 m (arquivo leve para o tablet)
    bbox, area = caixa_ti()
    gerar(cat, bbox, C.TEMPERATURA["resolucao_ti_graus"], "lst_ti", a.dias, recorte=area)


if __name__ == "__main__":
    main()
