# Monitor de focos de calor · TI Andirá-Marau

Site estático que mostra os focos de calor das últimas 48 horas ao redor da comunidade Ilha Michiles (rio Marau), na Terra Indígena Andirá-Marau (Sateré-Mawé). Cada foco mostra a distância e a direção a partir da comunidade, e focos ativos a até 10 km geram aviso no WhatsApp. Atualiza sozinho a cada hora pelo GitHub Actions e fica hospedado de graça no GitHub Pages.

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

## Avisos no WhatsApp

Usa a API oficial da Meta (WhatsApp Cloud API). Precisa de um número de celular só do projeto (que não esteja em uso no app do WhatsApp).

1. Em business.facebook.com, crie a conta empresarial do projeto.
2. Em developers.facebook.com → *Meus apps* → *Criar app* (tipo *Empresa*) → adicione o produto **WhatsApp** e cadastre o número do projeto. Anote o **Phone number ID**.
3. No *WhatsApp Manager* → *Modelos de mensagem*, crie o modelo abaixo e espere a aprovação.
4. Em *Configurações do negócio* → *Usuários do sistema*, crie um usuário (Admin), dê acesso ao app e gere um **token permanente** com as permissões `whatsapp_business_messaging` e `whatsapp_business_management`.
5. No GitHub, em **Settings → Secrets and variables → Actions**, cadastre os segredos `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` e `WHATSAPP_PARA` (números com DDI e DDD, separados por vírgula: `5592991234567,5592998765432`).
6. Teste: **Actions → Focos de calor → Run workflow**, marque *Só enviar uma mensagem de TESTE* e rode.

**Modelo de mensagem** — nome `alerta_foco_calor`, categoria **Utilidade**, idioma **Português (BR)**:

> 🔥 Alerta de foco de calor: {{1}} foco(s) ativo(s) a até 10 km da comunidade {{2}}. Detalhes: {{3}}. Veja o mapa: {{4}} — Confirme em campo antes de agir.

Exemplos para a Meta: `1` · `Ilha Michiles` · `3,2 km a nordeste, desde 19/10 14h30 (-3.7345, -57.2176)` · `https://valdiek.github.io/monitor-marau/`

A Meta cobra por mensagem de modelo enviada (centavos por mensagem). Cada foco é avisado uma vez só.

## Avisos no Telegram (opcional)

Crie um bot com o **@BotFather**, adicione-o a um grupo e cadastre os segredos `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`. Pode funcionar junto com o WhatsApp.

## Comunidade e distâncias

Em `scripts/config.py`: `COMUNIDADE` (nome e coordenadas), `ALERTA_KM` (10) e `ANEIS_KM` (5, 10 e 20 km, desenhados no mapa).

## Zona do rio Marau

Em `scripts/config.py`, preencha `ZONA_MARAU["pontos"]` com pontos (lat, lon) ao longo do trecho do rio, por exemplo `[(-3.60, -57.20), (-3.80, -57.15)]`. Os focos a até `buffer_km` dessa linha ganham o selo "Marau" e um contador próprio.

## Temperatura da superfície e qualidade do ar

- **Temperatura (botão "Temperatura" no mapa).** Mosaico Landsat 8/9 (30 m, banda térmica, ~10h da manhã) dos últimos 48 dias, com o pixel sem nuvem mais recente de cada lugar (máscara QA_PIXEL). Fonte: Microsoft Planetary Computer. Roda todo dia pelo workflow *Temperatura da superfície*. Tocando no mapa aparece o valor, o satélite e a data da cena.
- **Qualidade do ar (quadro e botão "Fumaça").** PM2.5 do modelo CAMS (Copernicus, ~40 km) via Open-Meteo, sem chave. Série das últimas 48 h e previsão de 3 dias na comunidade, e grade de 60 km ao redor. Faixas do IQAr (CETESB). Roda junto com os focos, a cada hora.

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
