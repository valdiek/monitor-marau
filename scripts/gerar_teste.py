"""Gera CSVs fictícios (formato INPE 10 min e FIRMS) para testar o site offline.

    python scripts/gerar_teste.py teste/
    python scripts/coletar.py --inpe-local teste/inpe --firms-local teste/firms --agora 2026-10-17T22:00:00Z
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

random.seed(7)
UTC = timezone.utc
AGORA = datetime(2026, 10, 17, 22, 0, tzinfo=UTC)
saida = Path(sys.argv[1] if len(sys.argv) > 1 else "teste")
(saida / "inpe").mkdir(parents=True, exist_ok=True)
(saida / "firms").mkdir(parents=True, exist_ok=True)

ti = shape(json.loads(C.TI_ARQUIVO.read_text())["features"][0]["geometry"])
c = ti.representative_point()

inpe, firms = [], []
INPE_NOME = {"NOAA-20": "NOAA-20", "NOAA-21": "NOAA-21", "GOES-19": "GOES-19", "TERRA": "TERRA_M-T",
             "AQUA": "AQUA_M-T", "METOP-B": "METOP-B", "METOP-C": "METOP-C"}
FIRMS_NOME = {"NOAA-20": "N20", "NOAA-21": "N21", "TERRA": "Terra", "AQUA": "Aqua"}


def det(sat, lat, lon, t, frp=None):
    inpe.append((lat, lon, INPE_NOME[sat], t))
    if sat in FIRMS_NOME:
        px = C.SATELITES[sat]["pixel_km"]
        firms.append((lat + random.uniform(-.001, .001), lon + random.uniform(-.001, .001),
                      round(px * random.uniform(1, 1.4), 2), round(px * random.uniform(1, 1.2), 2),
                      t, FIRMS_NOME[sat], random.choice("nnh"), frp or round(random.uniform(2, 30), 1)))


# Passagens: dias 15, 16 e 17; detecções de fundo longe da TI, mas dentro da faixa de 3°
def passagens():
    for dia in (15, 16, 17):
        base = datetime(2026, 10, dia, tzinfo=UTC)
        yield "NOAA-20", base + timedelta(hours=5, minutes=30)
        yield "NOAA-21", base + timedelta(hours=6, minutes=20)
        yield "NOAA-20", base + timedelta(hours=17, minutes=30)
        yield "NOAA-21", base + timedelta(hours=18, minutes=15)
        yield "TERRA", base + timedelta(hours=13, minutes=5)
        yield "METOP-B", base + timedelta(hours=13, minutes=35)
        yield "AQUA", base + timedelta(hours=17, minutes=50)


PASS = [(s, t) for s, t in passagens() if t <= AGORA]
for s, t in PASS:
    for _ in range(random.randint(4, 12)):
        det(s, c.y + random.uniform(-2.5, -1.8), c.x + random.uniform(1.6, 2.6), t + timedelta(minutes=random.randint(0, 3)))
t = AGORA - timedelta(hours=60)
while t <= AGORA:
    if random.random() < .5:
        det("GOES-19", c.y + random.uniform(-2.5, -1.8), c.x + random.uniform(1.6, 2.6), t)
    t += timedelta(minutes=10)


def ponto_na_ti(dlat, dlon):
    p = Point(c.x + dlon, c.y + dlat)
    assert ti.contains(p), (dlat, dlon)
    return p.y, p.x


def queimar(lat, lon, sats_tempos, goes=None):
    for s, t in sats_tempos:
        for _ in range(random.randint(1, 3)):
            det(s, lat + random.uniform(-.003, .003), lon + random.uniform(-.003, .003), t)
    if goes:
        ini, fim = goes
        t = ini
        while t <= fim:
            det("GOES-19", lat + .01, lon - .01, t)
            t += timedelta(minutes=random.choice([10, 20, 30]))


P = {s + t.strftime("%d%H"): (s, t) for s, t in PASS}
# 1. Foco ativo dentro da TI, visto em várias passagens e pelo GOES até agora
la, lo = ponto_na_ti(0.05, -0.08)
queimar(la, lo, [P["NOAA-2016" + "17"], P["NOAA-2117" + "06"], P["NOAA-2017" + "17"], P["NOAA-2117" + "18"]],
        goes=(AGORA - timedelta(hours=20), AGORA - timedelta(minutes=30)))
# 2. Foco extinto dentro da TI (visto só na manhã do dia 16)
la, lo = ponto_na_ti(-0.25, 0.10)
queimar(la, lo, [P["NOAA-2016" + "05"], P["NOAA-2116" + "06"]])
# 3. Foco no entorno (fora da TI, a poucos km), ativo
lo2 = ti.bounds[0] - 0.02
la2 = c.y
queimar(la2, lo2, [P["NOAA-2017" + "17"], P["AQUA17" + "17"]])
# 4. Foco extinto pelo GOES dentro da TI
la, lo = ponto_na_ti(0.20, 0.05)
queimar(la, lo, [P["NOAA-2117" + "06"]], goes=(AGORA - timedelta(hours=16), AGORA - timedelta(hours=9)))

# 5. Foco ativo a ~3 km a nordeste da comunidade (VIIRS da tarde + GOES)
from math import cos, radians
cl, cn = C.COMUNIDADE["lat"], C.COMUNIDADE["lon"]
queimar(cl + 0.019, cn + 0.019 / cos(radians(cl)), [P["NOAA-2017" + "17"], P["NOAA-2117" + "18"]],
        goes=(AGORA - timedelta(hours=5), AGORA - timedelta(minutes=20)))
# 6. Foco extinto a ~8 km a sudoeste (roça de ontem)
queimar(cl - 0.05, cn - 0.05 / cos(radians(cl)), [P["NOAA-2016" + "17"], P["NOAA-2116" + "18"]])

for t0 in sorted({r[3].replace(minute=r[3].minute // 10 * 10, second=0) for r in inpe}):
    linhas = [r for r in inpe if r[3].replace(minute=r[3].minute // 10 * 10, second=0) == t0]
    with open(saida / "inpe" / f"focos_10min_{t0:%Y%m%d_%H%M}.csv", "w") as f:
        f.write("lat,lon,satelite,data\n")
        for la, lo, s, t in linhas:
            f.write(f"{la:.5f},{lo:.5f},{s},{t:%Y-%m-%d %H:%M:%S}\n")
with open(saida / "firms" / "firms.csv", "w") as f:
    f.write("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n")
    for la, lo, sc, tr, t, s, cf, frp in firms:
        f.write(f"{la:.5f},{lo:.5f},330.1,{sc},{tr},{t:%Y-%m-%d},{t:%H%M},{s},VIIRS,{cf},2.0NRT,295.0,{frp},D\n")
print(f"{len(inpe)} linhas INPE, {len(firms)} linhas FIRMS em {saida}")
