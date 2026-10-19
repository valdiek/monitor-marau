"""Configuração do Monitor de Focos de Calor da TI Andirá-Marau.

Tudo o que se ajusta sem mexer na lógica fica aqui.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "docs" / "data"

FUSO = "America/Manaus"  # UTC-4, sem horário de verão

# ---------------------------------------------------------------------------
# Área monitorada
# ---------------------------------------------------------------------------
TI_ARQUIVO = DADOS / "ti.geojson"          # limite oficial (FUNAI, 25/06/2025)
MUNICIPIOS_ARQUIVO = DADOS / "municipios.geojson"

# Faixa de entorno ao redor da TI que também é monitorada (km).
ENTORNO_KM = 10

# Comunidade de referência: o mapa abre aqui e cada foco mostra distância e direção.
COMUNIDADE = {"nome": "Ilha Michiles", "lat": -3.754505, "lon": -57.237643}
ALERTA_KM = 10            # focos ativos até esta distância geram alerta
ANEIS_KM = [5, 10, 20]    # círculos desenhados no mapa (o maior também entra na área monitorada)

# Semáforo de queima (regra prática; ajuste com os técnicos e o Prevfogo).
# Umidade mínima e vento máximo entre 10h e 18h do dia.
SEMAFORO = {
    "ur_proibido": 30,          # abaixo disso: NÃO QUEIME
    "vento_proibido_kmh": 20,   # acima disso: NÃO QUEIME
    "seca_proibido_dias": 20,   # dias sem chuva + ar seco: NÃO QUEIME
    "ur_ruim": 40,              # abaixo disso: dia ruim
    "vento_ruim_kmh": 12,       # acima disso: dia ruim
    "seca_ruim_dias": 10,       # dias sem chuva: dia ruim
    "chuva_minima_mm": 2,       # dia com menos que isso conta como "sem chuva"
}

# Temperatura da superfície (Landsat 8/9)
TEMPERATURA = {
    "raio_km": 22,               # quadrado ao redor da comunidade
    "janela_dias": 48,           # junta as cenas desse período (a região é muito nublada)
    "resolucao_graus": 0.0003,   # ~33 m
    "escala_c": [20, 46],        # faixa de cores
}

# Qualidade do ar (CAMS via Open-Meteo, sem chave)
AR = {
    "grade_raio_km": 60,         # camada de fumaça no mapa
    "grade_passo_graus": 0.1,
}

# Zona prioritária do rio Marau.
# Lista de pontos (lat, lon) ao longo do trecho do rio, de jusante para
# montante. Os focos a até BUFFER_KM dessa linha recebem o selo "Rio Marau".
# Deixe a lista vazia para desligar a zona.
ZONA_MARAU = {
    "nome": "Rio Marau",
    "pontos": [],          # ex.: [(-3.60, -57.20), (-3.80, -57.15), ...]
    "buffer_km": 3,
}

# ---------------------------------------------------------------------------
# Janela de tempo
# ---------------------------------------------------------------------------
JANELA_H = 48               # o site mostra as últimas 48 h
RECENTE_H = 6               # "detecções recentes" no painel

# ---------------------------------------------------------------------------
# Satélites
# 'inpe'  = nomes usados nos CSVs do INPE (BDQueimadas)
# 'firms' = código de 'satellite' no CSV do FIRMS
# 'pixel_km' = tamanho nominal do pixel no nadir
# ---------------------------------------------------------------------------
SATELITES = {
    "NOAA-20": {"inpe": ["NOAA-20"], "firms": ["N20", "N"], "sensor": "VIIRS",
                "pixel_km": 0.375, "tipo": "polar", "horario": "~01h30 e ~13h30"},
    "NOAA-21": {"inpe": ["NOAA-21"], "firms": ["N21"], "sensor": "VIIRS",
                "pixel_km": 0.375, "tipo": "polar", "horario": "~01h30 e ~13h30"},
    "GOES-19": {"inpe": ["GOES-19", "GOES-16"], "firms": [], "sensor": "ABI",
                "pixel_km": 2.2, "tipo": "geoestacionario", "horario": "a cada 10 min"},
    "TERRA":   {"inpe": ["TERRA_M-M", "TERRA_M-T", "TERRA"], "firms": ["Terra", "T"],
                "sensor": "MODIS", "pixel_km": 1.0, "tipo": "polar", "horario": "~9h e ~21h"},
    "AQUA":    {"inpe": ["AQUA_M-T", "AQUA_M-M", "AQUA"], "firms": ["Aqua", "A"],
                "sensor": "MODIS", "pixel_km": 1.0, "tipo": "polar", "horario": "~13h e ~01h"},
    "METOP-B": {"inpe": ["METOP-B"], "firms": [], "sensor": "AVHRR",
                "pixel_km": 1.1, "tipo": "polar", "horario": "~9h30 e ~21h30"},
    "METOP-C": {"inpe": ["METOP-C"], "firms": [], "sensor": "AVHRR",
                "pixel_km": 1.1, "tipo": "polar", "horario": "~9h30 e ~21h30"},
}

# Fontes consultadas na API do FIRMS (precisa da chave FIRMS_MAP_KEY).
FIRMS_FONTES = ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"]

# ---------------------------------------------------------------------------
# Regras de processamento
# ---------------------------------------------------------------------------
# Detecções do mesmo foco: distância até (maior pixel + folga) e até 12 h.
AGRUP_FOLGA_KM = 0.5
AGRUP_HORAS = 12

# Mesma detecção vinda do INPE e do FIRMS: mesmo satélite, até 20 min.
DUPLICATA_MIN = 20

# Horário das passagens: inferido pelas detecções numa faixa ao redor da TI.
FAIXA_PASSAGEM_GRAUS = 3
PASSAGEM_INTERVALO_MIN = 30   # detecções separadas por mais que isso = outra passagem

# Extinção estimada
EXTINCAO_PASSAGENS_POLARES = 2   # passagens polares seguidas sem registrar o foco
EXTINCAO_GOES_HORAS = 3          # GOES passa 3 h sem registrar um foco que ele via
