/* Monitor de focos de calor · TI Andirá-Marau */
(function () {
  "use strict";

  const FUSO = "America/Manaus";
  const H = 3600e3;
  const $ = (s) => document.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const fmtHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
  const fmtDiaHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const fmtDia = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, weekday: "short", day: "2-digit", month: "2-digit" });
  const fmtCompleto = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  const d = (s) => (s ? new Date(s) : null);
  const dh = (s) => (s ? fmtDiaHora.format(d(s)).replace(",", "") : "–");

  let E, mapa, camadaFocos, fundos = {}, filtro = "todos";
  let AR = null, LST = null, camadaExtra = null, camadaAtual = "nenhuma", lstPixels = null, arQuando = "agora";
  const arquivo = (n) => (window.ARQUIVOS && window.ARQUIVOS[n]) || `data/${n}`;
  const marcadores = {};

  function corIdade(horas) {
    if (horas <= 6) return css("--f0");
    if (horas <= 12) return css("--f1");
    if (horas <= 24) return css("--f2");
    return css("--f3");
  }
  function corFoco(f) {
    if (f.status === "extinto") return css("--ext");
    return corIdade((d(E.gerado_em) - d(f.ultima)) / H);
  }
  function duracao(ms) {
    const h = Math.round(ms / H);
    if (h < 1) return "menos de 1 h";
    return h < 48 ? `${h} h` : `${Math.round(h / 24)} dias`;
  }
  const km1 = (v) => v.toString().replace(".", ",");
  function distTxt(f) { return `${km1(f.dist_com_km)} km a ${f.rumo}`; }
  function seloOnde(f) {
    let s = f.onde === "ti" ? '<span class="selo ti">TI</span>' : `<span class="selo ent">entorno ${f.dist_ti_km} km</span>`;
    if (f.marau) s += '<span class="selo marau">Marau</span>';
    if (f.alerta && f.status === "ativo") s += `<span class="selo alerta">≤ ${E.area.alerta_km} km</span>`;
    return s;
  }

  // ---------------------------------------------------------------- carregar
  Promise.all([
    fetch("data/estado.json", { cache: "no-store" }).then((r) => r.json()),
    fetch("data/ti.geojson").then((r) => r.json()),
    fetch("data/municipios.geojson").then((r) => r.json()).catch(() => null),
    fetch("data/zonas.geojson", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
    fetch("data/ar.json", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
    fetch("data/lst.json", { cache: "no-store" }).then((r) => r.json()).catch(() => null),
  ]).then(([estado, ti, mun, zonas, ar, lst]) => {
    E = estado;
    AR = ar && !ar.erro && ar.serie ? ar : null;
    LST = lst && !lst.erro && lst.estat ? lst : null;
    resumo();
    semaforo();
    avisos();
    iniciarMapa(ti, mun, zonas);
    focosNoMapa();
    linhaDoTempo();
    passagens();
    quadroAr();
    iniciarCamadas();
  }).catch((e) => {
    $("#atual").textContent = "Não foi possível carregar os dados.";
    console.error(e);
  });

  // ---------------------------------------------------------------- resumo
  function resumo() {
    const r = E.resumo;
    const g = d(E.gerado_em);
    const idade = (Date.now() - g) / H;
    $("#atual").textContent = `Atualizado ${fmtCompleto.format(g)}` + (idade > 3 && !E.teste ? ` · há ${duracao(Date.now() - g)}` : "");
    $("#n-alerta").textContent = r.ativos_alerta;
    $("#c-alerta").classList.toggle("zero", r.ativos_alerta === 0);
    $("#l-alerta").textContent = r.ativos_alerta === 1
      ? `foco ativo a até ${E.area.alerta_km} km da comunidade`
      : `focos ativos a até ${E.area.alerta_km} km da comunidade`;
    $("#n-ti").textContent = r.ativos_ti;
    $("#n-ent").textContent = r.ativos_entorno;
    $("#l-ent").textContent = `ativos no entorno (${E.area.entorno_km} km)`;
    $("#ent-km").textContent = `(${E.area.entorno_km} km)`;
    $("#n-ext").textContent = r.extintos;
    $("#n-det").textContent = r.deteccoes;
    $("#l-det").textContent = `detecções em 48 h · ${r.deteccoes_recentes} nas últimas ${E.recente_h} h`;
    if (E.area.marau.pontos.length) {
      $("#c-marau").hidden = false;
      $("#leg-marau").hidden = false;
      $("#n-marau").textContent = r.ativos_marau;
    }
  }

  // ---------------------------------------------------------------- semáforo de queima
  const NIVEL = { bom: "PODE QUEIMAR", ruim: "DIA RUIM PARA QUEIMAR", nao: "NÃO QUEIME HOJE" };
  const NIVEL_CURTO = { bom: "Pode queimar", ruim: "Dia ruim", nao: "Não queime" };
  function semaforo() {
    const S = E.semaforo;
    if (!S || !S.dias || !S.dias.length) return;
    $("#semaforo").hidden = false;
    $("#sem-fonte").textContent = S.fonte === "valores de teste" ? "valores de teste" : `previsão ${S.fonte}`;
    const h = S.dias[0];
    const titulo = h.nivel === "nao" ? NIVEL.nao : h.nivel === "ruim" ? NIVEL.ruim : NIVEL.bom;
    const jan = h.janela
      ? `<p class="sem-janela">Se for queimar: melhor horário <b>${h.janela.inicio}–${h.janela.fim}</b> (umidade ~${h.janela.ur}%, vento ~${h.janela.vento} km/h).</p>`
      : "";
    const el = $("#sem-hoje");
    el.dataset.nivel = h.nivel;
    el.innerHTML = `
      <div class="sem-titulo"><i class="sem-luz" aria-hidden="true"></i><b>${titulo}<small>${S.local} · ${fmtDia.format(new Date(h.data + "T12:00:00-04:00"))}</small></b></div>
      <p class="sem-motivos">${h.motivos.join(" · ")}</p>
      <div class="sem-num">
        <div><b>${h.ur_min}%</b><span>umidade mínima</span></div>
        <div><b>${h.vento_max}</b><span>vento máx. km/h</span></div>
        <div><b>${h.dias_sem_chuva}</b><span>dias sem chuva</span></div>
        <div><b>${h.temp_max}°</b><span>temperatura máx.</span></div>
      </div>${jan}`;
    $("#sem-dias").innerHTML = S.dias.slice(1, 4).map((d) => `
      <div class="sem-dia" data-nivel="${d.nivel}">
        <b>${d.dia}</b><strong>${NIVEL_CURTO[d.nivel]}</strong>
        <span>${d.ur_min}% · ${d.vento_max} km/h${d.chuva_mm >= 2 ? ` · chuva ${km1(d.chuva_mm)} mm` : ""}</span>
      </div>`).join("");
  }

  function avisos() {
    const el = $("#avisos");
    const msgs = [];
    if (E.teste) msgs.push(['teste', "DADOS DE TESTE — focos e previsão fictícios, só para mostrar como o sistema vai funcionar."]);
    const idade = (Date.now() - d(E.gerado_em)) / H;
    if (!E.teste && idade > 3) msgs.push(["", `A última atualização foi há ${duracao(idade * H)}. Os dados podem estar desatualizados.`]);
    for (const f of E.fontes) {
      if (!f.ok) msgs.push(["", `${f.fonte} indisponível nesta atualização${f.erro ? ` (${f.erro})` : ""}.`]);
      else if (f.erro) msgs.push(["", `${f.fonte}: ${f.erro}.`]);
    }
    if (!msgs.length) return;
    el.hidden = false;
    el.innerHTML = msgs.map(([c, m]) => `<div class="aviso ${c}">${m}</div>`).join("");
  }

  // ---------------------------------------------------------------- mapa
  function iniciarMapa(ti, mun, zonas) {
    mapa = L.map("mapa", { zoomControl: true, attributionControl: true, preferCanvas: false })
      .setView([E.area.comunidade.lat, E.area.comunidade.lon], 11);
    fundos.mapa = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "© OpenStreetMap",
    });
    fundos.sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 18, attribution: "Imagem © Esri, Maxar, Earthstar",
    });
    fundos.mapa.addTo(mapa);
    document.querySelectorAll("[data-fundo]").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("[data-fundo]").forEach((x) => x.classList.toggle("on", x === b));
      Object.values(fundos).forEach((f) => mapa.removeLayer(f));
      fundos[b.dataset.fundo].addTo(mapa);
    }));

    const verde = css("--ti");
    if (mun) {
      L.geoJSON(mun, {
        style: { color: "#7a6f62", weight: 1, opacity: .6, fill: false, dashArray: "2 4" },
        interactive: false,
      }).addTo(mapa);
    }
    const camTi = L.geoJSON(ti, { style: { color: verde, weight: 3, fillColor: verde, fillOpacity: .06 }, interactive: false }).addTo(mapa);

    if (zonas) {
      const cor = css("--marau");
      L.geoJSON(zonas, {
        style: (ft) => ft.properties.tipo === "marau"
          ? { color: cor, weight: 1.5, fillColor: cor, fillOpacity: .18 }
          : { color: verde, weight: 1.5, dashArray: "6 6", fill: false, opacity: .8 },
        interactive: false,
      }).addTo(mapa);
    }
    if (E.area.marau.pontos.length > 1) {
      L.polyline(E.area.marau.pontos, { color: css("--marau"), weight: 2, opacity: .9, dashArray: "4 4" })
        .bindTooltip(E.area.marau.nome).addTo(mapa);
    }

    // comunidade e anéis de distância
    const C0 = E.area.comunidade, azul = "#1f6f8b";
    const aneis = E.area.aneis_km.map((r) => {
      const circ = L.circle([C0.lat, C0.lon], { radius: r * 1000, color: azul, weight: r === E.area.alerta_km ? 2 : 1.2,
        dashArray: "6 6", fill: r === E.area.alerta_km, fillColor: azul, fillOpacity: .05, interactive: false }).addTo(mapa);
      L.tooltip({ permanent: true, direction: "center", className: "rotulo-anel" })
        .setLatLng([C0.lat + r / 110.57, C0.lon]).setContent(`${r} km`).addTo(mapa);
      return circ;
    });
    L.marker([C0.lat, C0.lon], { icon: L.divIcon({ className: "", html: '<div class="marca-com"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), zIndexOffset: 1000 })
      .bindTooltip(C0.nome, { permanent: true, direction: "bottom", offset: [0, 10], className: "rotulo-com" }).addTo(mapa);
    const enquadrar = (modo) => {
      const raio = E.area.alerta_km * 1000;
      mapa.fitBounds(modo === "ti" ? camTi.getBounds() : L.latLng(C0.lat, C0.lon).toBounds(raio * 2), { padding: [12, 12] });
    };
    document.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("[data-zoom]").forEach((x) => x.classList.toggle("on", x === b));
      enquadrar(b.dataset.zoom);
    }));
    enquadrar("com");
    camadaFocos = L.layerGroup().addTo(mapa);
    mapa.on("zoomend", focosNoMapa);
    const rotulos = () => mapa.getContainer().classList.toggle("zoom-baixo", mapa.getZoom() < 10);
    mapa.on("zoomend", rotulos); rotulos();
  }

  function popup(f) {
    const c = corFoco(f);
    const ext = f.status === "extinto"
      ? `<dt>Apagou</dt><dd>entre ${dh(f.extinto_apos)} e ${dh(f.extinto_ate)}</dd>`
      : `<dt>Ativo há</dt><dd>${duracao(d(E.gerado_em) - d(f.inicio))}</dd>`;
    const gm = `https://www.google.com/maps/search/?api=1&query=${f.lat},${f.lon}`;
    return `<div class="pop">
      <h3>${f.id} ${seloOnde(f)}</h3>
      <span class="st" style="background:${c}">${f.status === "ativo" ? "ATIVO" : "EXTINTO (estimado)"}</span>
      <dl>
        <dt>Distância</dt><dd><b>${distTxt(f)}</b> da comunidade</dd>
        <dt>Município</dt><dd>${f.municipio || "–"}</dd>
        <dt>1ª detecção</dt><dd>${dh(f.inicio)}</dd>
        <dt>Última</dt><dd>${dh(f.ultima)}</dd>
        ${ext}
        <dt>Detecções</dt><dd>${f.n} · ${f.satelites.join(", ")}</dd>
        ${f.frp_max != null ? `<dt>Potência</dt><dd>${f.frp_max} MW (FRP máx.)</dd>` : ""}
        ${f.confianca ? `<dt>Confiança</dt><dd>${f.confianca}</dd>` : ""}
        <dt>Fontes</dt><dd>${f.fontes.join(" + ")}</dd>
        <dt>Local</dt><dd>${f.lat.toFixed(4)}, ${f.lon.toFixed(4)}</dd>
      </dl>
      <div class="botoes">
        <a href="${gm}" target="_blank" rel="noopener">Google Maps ↗</a>
        <a href="https://browser.dataspace.copernicus.eu/?zoom=14&lat=${f.lat}&lng=${f.lon}&datasetId=S2_L2A_CDAS" target="_blank" rel="noopener">Sentinel-2 ↗</a>
      </div>
    </div>`;
  }

  function focosNoMapa() {
    if (!camadaFocos) return;
    camadaFocos.clearLayers();
    const zoom = mapa.getZoom();
    const lista = E.focos.filter((f) => filtro === "todos" || f.status === filtro).slice().reverse();
    for (const f of lista) {
      const c = corFoco(f);
      const ext = f.status === "extinto";
      // pixels das detecções (só com zoom de perto)
      if (zoom >= 11) {
        for (const p of f.deteccoes.filter((x) => x.sensor !== "ABI")) {
          const dlat = p.px[1] / 110.57 / 2;
          const dlon = p.px[0] / (111.32 * Math.cos(p.lat * Math.PI / 180)) / 2;
          L.rectangle([[p.lat - dlat, p.lon - dlon], [p.lat + dlat, p.lon + dlon]], {
            color: c, weight: 1, fillColor: c, fillOpacity: ext ? .08 : .18, dashArray: ext ? "3 3" : null, interactive: false,
          }).addTo(camadaFocos);
        }
      }
      const raio = Math.min(16, 7 + Math.sqrt(f.n) * 1.4);
      const m = L.circleMarker([f.lat, f.lon], {
        radius: raio, color: ext ? c : "#2a0d05", weight: ext ? 2 : 1.5, dashArray: ext ? "3 3" : null,
        fillColor: c, fillOpacity: ext ? .15 : .9, bubblingMouseEvents: false,
      }).bindPopup(popup(f), { maxWidth: 280 })
        .bindTooltip(f.id, { permanent: zoom >= 10, direction: "right", offset: [raio, 0], className: "rotulo-foco" })
        .addTo(camadaFocos);
      marcadores[f.id] = m;
    }
  }

  function irPara(id) {
    const f = E.focos.find((x) => x.id === id);
    if (!f) return;
    $("#mapa").scrollIntoView({ behavior: "smooth", block: "center" });
    mapa.setView([f.lat, f.lon], Math.max(mapa.getZoom(), 12));
    setTimeout(() => marcadores[id] && marcadores[id].openPopup(), 350);
  }

  // ---------------------------------------------------------------- linha do tempo
  function linhaDoTempo() {
    const el = $("#linha");
    const t0 = d(E.janela_inicio), t1 = d(E.gerado_em), tot = t1 - t0;
    const x = (t) => Math.max(0, Math.min(100, ((d(t) - t0) / tot) * 100));
    const lista = E.focos.filter((f) => filtro === "todos" || f.status === filtro);
    el.style.setProperty("--rot", window.innerWidth < 520 ? "98px" : "150px");

    if (!lista.length) {
      el.innerHTML = `<div class="vazio">${E.focos.length ? "Nenhum foco neste filtro." : "Nenhum foco de calor na TI nem no entorno nas últimas 48 horas."}</div>`;
      return;
    }

    // eixo a cada 12 h (horário de Manaus)
    let eixo = "";
    const passo = 12 * H;
    const off = 4 * H; // UTC−4
    let t = Math.ceil((t0.getTime() - off) / passo) * passo + off;
    for (; t <= t1.getTime(); t += passo) {
      const dt = new Date(t);
      const rot = fmtHora.format(dt) === "00:00" ? fmtDia.format(dt).replace(".", "") : fmtHora.format(dt).replace(":00", "h");
      eixo += `<span style="left:${x(dt)}%">${rot}</span>`;
    }

    const linhas = lista.map((f) => {
      const c = corFoco(f);
      const a = x(f.inicio), b = x(f.ultima);
      let barras = "";
      if (f.status === "ativo") {
        barras += `<div class="lt-barra vivo" style="left:${a}%;width:${Math.max(b - a, .8)}%;--c:${c}"></div>`;
        barras += `<div class="lt-esvai" style="left:${b}%;width:${100 - b}%;--c:${c}"></div>`;
      } else {
        const e = x(f.extinto_ate);
        barras += `<div class="lt-barra" style="left:${a}%;width:${Math.max(b - a, .8)}%;--c:${corIdade((t1 - d(f.ultima)) / H)}"></div>`;
        barras += `<div class="lt-hach" style="left:${b}%;width:${Math.max(e - b, .8)}%"></div>`;
      }
      const marcas = [...new Set(f.deteccoes.filter((p) => p.sensor !== "ABI").map((p) => p.t))].map((tt) => `<i class="lt-marca" style="left:${x(tt)}%"></i>`).join("");
      return `<div class="lt-lin" tabindex="0" role="button" data-id="${f.id}" aria-label="Foco ${f.id}, ${f.status}">
        <div class="lt-rot"><b>${f.id}</b> ${seloOnde(f)}<small>${distTxt(f)} · ${f.n} det.</small></div>
        <div class="lt-pista">${barras}${marcas}<i class="agora"></i></div>
      </div>`;
    }).join("");

    el.innerHTML = `<div class="lt-eixo">${eixo}</div>${linhas}`;
    el.querySelectorAll(".lt-lin").forEach((r) => {
      r.addEventListener("click", () => irPara(r.dataset.id));
      r.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); irPara(r.dataset.id); } });
    });
  }

  document.querySelectorAll("[data-filtro]").forEach((b) => b.addEventListener("click", () => {
    filtro = b.dataset.filtro;
    document.querySelectorAll("[data-filtro]").forEach((x) => x.classList.toggle("on", x === b));
    linhaDoTempo();
    focosNoMapa();
  }));
  window.addEventListener("resize", () => E && linhaDoTempo());

  // ---------------------------------------------------------------- passagens
  function passagens() {
    const tb = $("#passagens");
    if (!E.passagens.length) {
      tb.innerHTML = '<tr><td colspan="4">Nenhuma passagem identificada nas últimas 48 h.</td></tr>';
      return;
    }
    let dia = "", html = "";
    for (const p of E.passagens) {
      const dd = fmtDia.format(d(p.hora));
      if (dd !== dia) {
        dia = dd;
        html += `<tr><td colspan="4" class="dia">${dd}</td></tr>`;
      }
      const px = p.pixel_km < 1 ? `${Math.round(p.pixel_km * 1000)} m` : `${p.pixel_km.toString().replace(".", ",")} km`;
      html += `<tr><td>${fmtHora.format(d(p.hora))}</td><td>${p.sat} <small>${p.sensor}</small></td><td>${px}</td>
        <td class="n ${p.n_area ? "pos" : ""}">${p.n_area}</td></tr>`;
    }
    tb.innerHTML = html;
  }

  // ================================================================ qualidade do ar
  const AR_PARADAS = [[0, "#43a047"], [15, "#c0ca33"], [32, "#fdd835"], [50, "#fb8c00"], [75, "#e53935"], [125, "#7b1fa2"], [200, "#4a0072"]];
  const AR_FAIXA_COR = { boa: "#43a047", moderada: "#f9a825", ruim: "#ef6c00", muito_ruim: "#d32f2f", pessima: "#6a1b9a" };
  function hex(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  function rampa(v, paradas) {
    if (v <= paradas[0][0]) return hex(paradas[0][1]);
    for (let i = 1; i < paradas.length; i++) {
      const [a, ca] = paradas[i - 1], [b, cb] = paradas[i];
      if (v <= b) { const t = (v - a) / (b - a), x = hex(ca), y = hex(cb); return x.map((k, j) => Math.round(k + (y[j] - k) * t)); }
    }
    return hex(paradas[paradas.length - 1][1]);
  }
  function faixaAr(v) {
    if (v == null) return null;
    return v <= 15 ? "boa" : v <= 50 ? "moderada" : v <= 75 ? "ruim" : v <= 125 ? "muito_ruim" : "pessima";
  }
  const NOME_FAIXA = { boa: "Boa", moderada: "Moderada", ruim: "Ruim", muito_ruim: "Muito ruim", pessima: "Péssima" };
  const horaDe = (t) => new Date(t + ":00-04:00");

  function quadroAr() {
    if (!AR) return;
    $("#ar").hidden = false;
    $("#ar-fonte").textContent = AR.fonte === "valores de teste" ? "valores de teste" : `modelo ${AR.modelo}`;
    const a = AR.atual || {}, cod = AR.nivel || faixaAr(a.pm25);
    const pico = AR.pico24;
    $("#ar-topo").innerHTML = `
      <div class="ar-nivel${cod === "moderada" || cod === "boa" ? " claro" : ""}" style="--c:${AR_FAIXA_COR[cod] || "var(--suave)"}">
        <span>Ar hoje</span><b>${NOME_FAIXA[cod] || "–"}</b><small>média das últimas 24 h</small>
      </div>
      <div class="ar-num"><b>${a.pm25 != null ? Math.round(a.pm25) : "–"}</b><span>PM2.5 agora<br>µg/m³</span></div>
      <div class="ar-num"><b>${AR.media24 != null ? Math.round(AR.media24) : "–"}</b><span>média 24 h<br>µg/m³</span></div>
      <div class="ar-num"><b>${pico ? Math.round(pico.pm25) : "–"}</b><span>pior nas próximas 24 h${pico ? `<br>${fmtHora.format(horaDe(pico.t)).replace(":00", "h")} · ${NOME_FAIXA[faixaAr(pico.pm25)]}` : ""}</span></div>`;
    graficoAr();
  }

  function graficoAr() {
    const el = $("#ar-grafico");
    const S = AR.serie.filter((p) => p.pm25 != null);
    if (!S.length) return;
    const W = Math.max(300, el.clientWidth || 600), H = 150, m = { l: 28, r: 6, t: 8, b: 22 };
    const max = Math.max(80, ...S.map((p) => p.pm25)) * 1.08;
    const bw = (W - m.l - m.r) / S.length;
    const y = (v) => m.t + (H - m.t - m.b) * (1 - v / max);
    const agora = horaDe(AR.hora_local).getTime();
    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" aria-hidden="true">`;
    for (const [v, rot] of [[15, "15 boa"], [50, "50 moderada"], [75, "75 ruim"]]) {
      if (v > max) continue;
      svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" class="g-ref"/><text x="${m.l - 4}" y="${y(v) + 3}" class="g-rot" text-anchor="end">${v}</text>`;
    }
    S.forEach((p, i) => {
      const t = horaDe(p.t).getTime();
      const futuro = t > agora;
      svg += `<rect x="${(m.l + i * bw).toFixed(1)}" y="${y(p.pm25).toFixed(1)}" width="${Math.max(1, bw - .6).toFixed(1)}" height="${(H - m.b - y(p.pm25)).toFixed(1)}" fill="${AR_FAIXA_COR[faixaAr(p.pm25)]}" opacity="${futuro ? .45 : .95}"><title>${dh(new Date(t).toISOString())}: ${Math.round(p.pm25)} µg/m³</title></rect>`;
      if (p.t.endsWith("T00:00")) {
        svg += `<line x1="${m.l + i * bw}" x2="${m.l + i * bw}" y1="${m.t}" y2="${H - m.b}" class="g-dia"/><text x="${m.l + i * bw + 3}" y="${H - 7}" class="g-rot">${p.t.slice(8, 10)}/${p.t.slice(5, 7)}</text>`;
      }
      if (t === agora) {
        svg += `<line x1="${m.l + i * bw}" x2="${m.l + i * bw}" y1="${m.t - 4}" y2="${H - m.b}" class="g-agora"/><text x="${m.l + i * bw + 3}" y="${m.t + 6}" class="g-rot forte">agora</text>`;
      }
    });
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" class="g-base"/></svg>`;
    el.innerHTML = svg + '<p class="nota g-leg">Barras cheias: estimativa das últimas horas. Barras claras: previsão.</p>';
  }
  window.addEventListener("resize", () => AR && graficoAr());

  // ================================================================ camadas do mapa
  function iniciarCamadas() {
    const bt = document.querySelectorAll("[data-camada]");
    bt.forEach((b) => {
      const tem = b.dataset.camada === "nenhuma" || (b.dataset.camada === "lst" ? LST : AR);
      if (!tem) { b.disabled = true; b.title = "ainda sem dados"; }
      b.addEventListener("click", () => {
        if (b.disabled) return;
        bt.forEach((x) => x.classList.toggle("on", x === b));
        mostrarCamada(b.dataset.camada);
      });
    });
    $("#opacidade").addEventListener("input", (e) => camadaExtra && camadaExtra.setOpacity(e.target.value / 100));
    document.querySelectorAll("[data-quando]").forEach((b) => b.addEventListener("click", () => {
      arQuando = b.dataset.quando;
      document.querySelectorAll("[data-quando]").forEach((x) => x.classList.toggle("on", x === b));
      mostrarCamada("ar");
    }));
    mapa.on("click", lerPonto);
  }

  function mostrarCamada(qual) {
    camadaAtual = qual;
    if (camadaExtra) { mapa.removeLayer(camadaExtra); camadaExtra = null; }
    const painel = $("#painel-camada");
    painel.hidden = qual === "nenhuma";
    $("#ar-quando").hidden = qual !== "ar";
    const op = $("#opacidade").value / 100;
    if (qual === "lst") {
      camadaExtra = L.imageOverlay(arquivo("lst.png") + (window.ARQUIVOS ? "" : `?v=${LST.gerado_em}`), LST.bounds, { opacity: op, className: "img-lst", interactive: false }).addTo(mapa);
      camadaExtra.bringToBack();
      escala(LST.rampa, LST.escala_c[0], LST.escala_c[1], "", [20, 25, 30, 35, 40, 46], "°C");
      const cenas = LST.cenas.slice(0, 3).map((c) => `${c.satelite} ${c.data.slice(8, 10)}/${c.data.slice(5, 7)} (${Math.round(c.pct)}%)`).join(", ");
      const com = LST.estat.comunidade != null ? ` Na comunidade: <b>${km1(LST.estat.comunidade)} °C</b>.` : "";
      $("#camada-info").innerHTML = `Temperatura da superfície às ~10h, Landsat 30 m. ${Math.round(LST.cobertura_pct)}% da área sem nuvem nos últimos ${LST.janela_dias} dias; partes sem cor estavam cobertas. Cenas: ${cenas}.${com} Toque no mapa para ver o valor.`;
      if (!lstPixels) carregarPixels();
    } else if (qual === "ar") {
      const g = AR.grade, M = g[arQuando];
      const cv = document.createElement("canvas");
      cv.width = g.lons.length; cv.height = g.lats.length;
      const cx = cv.getContext("2d"), img = cx.createImageData(cv.width, cv.height);
      for (let i = 0; i < g.lats.length; i++) for (let j = 0; j < g.lons.length; j++) {
        const v = M[i][j], k = ((g.lats.length - 1 - i) * cv.width + j) * 4;
        if (v == null) continue;
        const [r, gg, b] = rampa(v, AR_PARADAS);
        img.data.set([r, gg, b, 255], k);
      }
      cx.putImageData(img, 0, 0);
      const p = g.passo / 2;
      camadaExtra = L.imageOverlay(cv.toDataURL(), [[g.lats[0] - p, g.lons[0] - p], [g.lats[g.lats.length - 1] + p, g.lons[g.lons.length - 1] + p]],
        { opacity: op, className: "img-ar", interactive: false }).addTo(mapa);
      camadaExtra.bringToBack();
      escala(AR_PARADAS.slice(0, 6), 0, 125, "", [0, 15, 50, 75, 125]);
      $("#camada-info").innerHTML = `Fumaça fina (PM2.5, em µg/m³), modelo CAMS (~40 km), ${arQuando === "agora" ? "hora atual" : "pior valor das próximas 24 h"}. Mostra para onde a fumaça da região está indo. Toque no mapa para ver o valor.`;
    }
    if (qual === "ar") mapa.fitBounds(camadaExtra.getBounds(), { padding: [4, 4] });
    else if (qual === "lst") mapa.fitBounds(LST.bounds, { padding: [4, 4] });
  }

  function escala(paradas, min, max, unidade, marcas, sufixo = "") {
    const pos = (v) => ((v - min) / (max - min)) * 100;
    const grad = paradas.map(([v, c]) => `${c} ${Math.max(0, Math.min(100, pos(v))).toFixed(1)}%`).join(", ");
    $("#escala").innerHTML = `<div class="escala-barra" style="background:linear-gradient(90deg, ${grad})"></div>
      <div class="escala-marcas">${marcas.map((v, i) => `<span style="left:${pos(v)}%">${v}${i === marcas.length - 1 ? (sufixo ? " " + sufixo : "+") : ""}</span>`).join("")}<em>${unidade}</em></div>`;
  }

  function carregarPixels() {
    const im = new Image();
    im.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = im.width; cv.height = im.height;
      const cx = cv.getContext("2d", { willReadFrequently: true });
      cx.drawImage(im, 0, 0);
      lstPixels = { w: im.width, h: im.height, d: cx.getImageData(0, 0, im.width, im.height).data };
    };
    im.src = arquivo("lst_valor.png") + (window.ARQUIVOS ? "" : `?v=${LST.gerado_em}`);
  }

  function lerPonto(ev) {
    const { lat, lng } = ev.latlng;
    let html = null;
    if (camadaAtual === "lst" && LST && lstPixels) {
      const [[s, w], [n, e]] = LST.bounds;
      if (lat < s || lat > n || lng < w || lng > e) return;
      const x = Math.floor(((lng - w) / (e - w)) * lstPixels.w), y = Math.floor(((n - lat) / (n - s)) * lstPixels.h);
      const k = (y * lstPixels.w + x) * 4, r = lstPixels.d[k], g = lstPixels.d[k + 1];
      if (!r) html = "<b>Sem dado</b><br>Nuvem ou sombra em todas as imagens do período.";
      else {
        const t = (r - 1) / 4 + LST.escala_c[0];
        const c = LST.cenas.find((x) => x.indice === g - 1);
        html = `<b>${km1(t.toFixed(1))} °C</b> na superfície<br>${c ? `${c.satelite} · ${c.data.slice(8, 10)}/${c.data.slice(5, 7)}${c.hora_utc ? ` · ~${String((+c.hora_utc.slice(0, 2) + 20) % 24).padStart(2, "0")}h${c.hora_utc.slice(3)}` : ""}` : ""}`;
      }
    } else if (camadaAtual === "ar" && AR) {
      const g = AR.grade, p = g.passo;
      const i = Math.round((lat - g.lats[0]) / p), j = Math.round((lng - g.lons[0]) / p);
      if (i < 0 || j < 0 || i >= g.lats.length || j >= g.lons.length) return;
      const v = g[arQuando][i][j];
      if (v == null) return;
      html = `<b>${Math.round(v)} µg/m³</b> de PM2.5<br>Ar ${NOME_FAIXA[faixaAr(v)].toLowerCase()} · ${arQuando === "agora" ? "agora" : "pior em 24 h"}`;
    }
    if (html) L.popup({ maxWidth: 240 }).setLatLng(ev.latlng).setContent(`<div class="pop">${html}</div>`).openOn(mapa);
  }
})();
