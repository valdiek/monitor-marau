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
  ]).then(([estado, ti, mun, zonas]) => {
    E = estado;
    resumo();
    semaforo();
    avisos();
    iniciarMapa(ti, mun, zonas);
    focosNoMapa();
    linhaDoTempo();
    passagens();
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
        fillColor: c, fillOpacity: ext ? .15 : .9,
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
})();
