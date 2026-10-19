# Monitor de focos de calor · TI Andirá-Marau

Site estático que mostra os focos de calor das últimas 48 horas ao redor da comunidade Ilha Michiles (rio Marau), na Terra Indígena Andirá-Marau (Sateré-Mawé). Cada foco mostra a distância e a direção a partir da comunidade, e focos ativos a até 10 km geram aviso no Telegram. Atualiza sozinho a cada hora pelo GitHub Actions e fica hospedado de graça no GitHub Pages.

## O que o site mostra

- Focos ativos dentro da TI, no entorno e na zona do rio Marau.
- Mapa com o limite oficial da TI (FUNAI, 25/06/2025), o entorno, os municípios e cada foco colorido pela idade da última detecção. Com zoom de perto, aparecem os pixels reais do satélite.
- Linha do tempo de 48 h por foco, com o período estimado de extinção.
- Tabela das passagens dos satélites e quantas detecções cada uma fez na área.

## Publicar (uma vez)

1. Crie um repositório no GitHub e envie esta pasta (branch `main`).
2. Peça uma chave gratuita do FIRMS em https://firms.modaps.eosdis.nasa.gov/api/map_key/ e cadastre em **Settings → Secrets and variables → Actions → New repository secret**, nome `FIRMS_MAP_KEY`. Sem a chave o site funciona só com o INPE (sem tamanho real do pixel, potência e confiança).
3. Em **Settings → Pages**: *Deploy from a branch*, branch `main`, pasta `/docs`.
4. Em **Actions → Focos de calor → Run workflow**, rode uma vez para gerar os primeiros dados reais. Depois roda sozinho a cada hora.

## Avisos no Telegram (opcional)

1. No Telegram, fale com o **@BotFather**, mande `/newbot` e guarde o token que ele devolve.
2. Crie um grupo com os técnicos e as lideranças e adicione o bot. Mande uma mensagem no grupo e abra `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver o `chat.id` (número negativo).
3. Cadastre os segredos `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` no repositório. Em **Variables**, crie `SITE_URL` com o endereço do site.

Cada foco ativo a até `ALERTA_KM` (10 km) da comunidade é avisado uma vez só.

## Comunidade e distâncias

Em `scripts/config.py`: `COMUNIDADE` (nome e coordenadas), `ALERTA_KM` (10) e `ANEIS_KM` (5, 10 e 20 km, desenhados no mapa).

## Zona do rio Marau

Em `scripts/config.py`, preencha `ZONA_MARAU["pontos"]` com pontos (lat, lon) ao longo do trecho do rio, por exemplo `[(-3.60, -57.20), (-3.80, -57.15)]`. Os focos a até `buffer_km` dessa linha ganham o selo "Marau" e um contador próprio.

## Como os dados são tratados

- **Fontes.** INPE BDQueimadas (arquivos de 10 min) e NASA FIRMS (VIIRS NOAA-20/21 e MODIS). Detecções iguais nas duas fontes são unidas.
- **Agrupamento.** Detecções a até (maior pixel + 0,5 km) e até 12 h uma da outra formam um só foco.
- **Extinção estimada.** O foco vira "extinto" quando duas passagens polares seguidas não o registram, ou quando o GOES-19, que o via, passa 3 h sem registrá-lo. Nuvem e fumaça podem gerar extinções falsas.
- **Passagens.** Inferidas pelas detecções de cada satélite numa faixa de 3° ao redor da TI.

Todos os limites ficam em `scripts/config.py`.

## Rodar e testar localmente

```bash
pip install -r requirements.txt
python scripts/coletar.py                       # dados reais (usa FIRMS_MAP_KEY se existir)
python scripts/gerar_teste.py teste/            # ou: dados fictícios
python scripts/coletar.py --inpe-local teste/inpe --firms-local teste/firms --agora 2026-10-17T22:00:00Z
cd docs && python -m http.server 8000           # abrir http://localhost:8000
```

Com dados de teste, o site mostra um aviso vermelho de "DADOS DE TESTE".

## Créditos dos dados

Focos: INPE e NASA FIRMS. Limite da TI: FUNAI, via geobr/IPEA. Municípios: IBGE, via tbrugz/geodata-br. Mapa: OpenStreetMap e Esri World Imagery.
