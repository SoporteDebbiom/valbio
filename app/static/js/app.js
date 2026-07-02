/* =========================================================================
   Cliente de captura y resultados.
   El servidor calcula con precisión completa y devuelve números crudos;
   el cliente sólo arma la captura, pide el cálculo y FORMATEA con los
   decimales elegidos (sin redondeo en el cálculo). Un módulo por "kind".
   ========================================================================= */
(() => {
  "use strict";
  const root = document.getElementById("app-root");
  if (!root) return;

  const KIND = root.dataset.kind;
  const MODULE_ID = root.dataset.module;
  const UNIT = root.dataset.unit;
  const COMPUTE_URL = root.dataset.computeUrl;
  const SAVE_URL = root.dataset.saveUrl;
  const IMPORT_URL = root.dataset.importUrl;
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const cfg = JSON.parse(document.getElementById("project-cfg").textContent || "{}");
  let DEC = Number.isInteger(cfg.decimals) ? cfg.decimals : 4;
  let saved = JSON.parse(document.getElementById("saved-data").textContent || "{}");
  let lastResults = null;
  let version = parseInt(root.dataset.version || "0", 10);

  // ---- utilidades ----------------------------------------------------------
  const el = (tag, attrs = {}, html = "") => {
    const n = document.createElement(tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (html) n.innerHTML = html;
    return n;
  };
  const fmt = (x) => (x === null || x === undefined || x === "")
    ? "—"
    : Number(x).toLocaleString("en-US", { minimumFractionDigits: DEC, maximumFractionDigits: DEC });
  const cls = (ok) => ok === true ? "is-ok" : ok === false ? "is-bad" : "";
  const verdictTag = (v) => {
    const c = v === "CUMPLE" ? "ok" : v === "NO CUMPLE" ? "bad" : "neu";
    return `<span class="tag ${c}">${v}</span>`;
  };
  const fx = (items) =>
    `<div class="fx"><b>Fórmulas (idénticas al Excel):</b>${items.map(t => `<code>${t}</code>`).join("")}</div>`;

  async function post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  let timer = null;
  function scheduleCompute() {
    clearTimeout(timer);
    timer = setTimeout(runCompute, 180);
  }
  async function runCompute() {
    const payload = MOD.collect();
    try {
      lastResults = await post(COMPUTE_URL, payload);
      MOD.render(lastResults);
    } catch (e) { /* sin conexión: se mantiene la última vista */ }
  }
  function rerender() { if (lastResults) MOD.render(lastResults); }

  // Reconstruye la tabla del módulo conservando lo capturado (para +/- filas y columnas).
  function rebuild() {
    try { saved = MOD.collect(); } catch (e) { /* ignora datos a medio capturar */ }
    root.innerHTML = "";
    MOD.build();
    runCompute();
  }

  // Barra de controles "− etiqueta +" para agregar o quitar filas/columnas.
  function controls(defs) {
    const bar = el("div", { class: "sizer" });
    defs.forEach((d) => {
      const g = el("span", { class: "sz-group" });
      g.innerHTML = `<button type="button" class="szbtn" data-a="rm" title="Quitar ${d.label}">−</button>` +
        `<span class="sz-lab">${d.label}: <b>${d.get()}</b></span>` +
        `<button type="button" class="szbtn" data-a="add" title="Agregar ${d.label}">+</button>`;
      g.querySelector('[data-a="add"]').addEventListener("click", () => { d.set(d.get() + 1); rebuild(); });
      g.querySelector('[data-a="rm"]').addEventListener("click", () => {
        if (d.get() > (d.min || 1)) { d.set(d.get() - 1); rebuild(); }
      });
      bar.appendChild(g);
    });
    return bar;
  }

  // Escapa texto del usuario antes de meterlo en atributos value="...".
  function escAttr(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/"/g, "&quot;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Operación estructural de la tabla libre: lee, modifica y reconstruye.
  function freeApply(fn) {
    const data = KINDS.free.collect();
    fn(data);
    saved = data;
    root.innerHTML = "";
    KINDS.free.build();
    runCompute();
  }
  function setFree(key, t, c, text) {
    const n = root.querySelector(`[data-res=${key}][data-t='${t}'][data-c='${c}']`);
    if (n) n.textContent = text;
  }

  // ---- importación desde Excel (mapeo por posición) ------------------------
  function isNum(v) {
    return v !== "" && v != null && !isNaN(parseFloat(String(v).replace(",", ".")));
  }
  // Reemplaza los datos del módulo con un payload y lo vuelve a dibujar.
  function loadInto(payload) {
    saved = payload;
    root.innerHTML = "";
    MOD.build();
    runCompute();
  }
  const col = (grid, c) => grid.map(r => (r[c] != null ? r[c] : ""));
  const width = (grid) => grid.reduce((m, r) => Math.max(m, r.length), 0);

  // Cuadro de diálogo: elegir hoja, marcar encabezados y mapear columnas a campos.
  function openImportWizard(sheets) {
    let sIdx = 0, levels = null;
    const CFG_KEY = "valbio.import." + KIND;
    const loadCfg = () => { try { return JSON.parse(localStorage.getItem(CFG_KEY) || "null"); } catch (e) { return null; } };
    const saveCfg = (c) => { try { localStorage.setItem(CFG_KEY, JSON.stringify(c)); } catch (e) { /* almacenamiento no disponible */ } };
    const cfg = loadCfg() || {};
    if (cfg.sheet != null && cfg.sheet < sheets.length) sIdx = cfg.sheet;
    if (Array.isArray(cfg.levels)) levels = cfg.levels.map(a => a.slice());
    const ov = el("div", { class: "modal-ov" });
    const box = el("div", { class: "modal" });
    ov.appendChild(box); document.body.appendChild(ov);
    const close = () => ov.remove();

    const grid = () => sheets[sIdx].grid || [];
    const cols = () => width(grid());
    const autoHeader = () => {
      const g = grid();
      return g.length > 1 && g[0].every(c => !isNum(c)) && g.slice(1).some(r => r.some(isNum));
    };
    let header = (typeof cfg.header === "boolean") ? cfg.header : autoHeader();
    const dataRows = () => header ? grid().slice(1) : grid();
    const colLabel = (c) => header ? (String((grid()[0] || [])[c] || "").trim() || "Columna " + (c + 1)) : "Columna " + (c + 1);
    const colOptions = (sel) => {
      let o = ""; for (let c = 0; c < cols(); c++) o += `<option value="${c}"${c === sel ? " selected" : ""}>${escAttr(colLabel(c))}</option>`;
      return o;
    };
    const mkLevel = (li) => {
      const cc = Math.max(1, cols());
      return MOD.wiz.axis === "stats" ? ["", Math.min(li, cc - 1)]
        : [Math.min(2 * li, cc - 1), Math.min(2 * li + 1, cc - 1)];
    };
    function readLevels() {
      box.querySelectorAll(".imp-level").forEach((elm, li) => {
        MOD.wiz.perLevel.forEach((pf, pi) => {
          const node = elm.querySelector(`[data-pf="${pi}"]`);
          levels[li][pi] = pf.type === "text" ? node.value : parseInt(node.value, 10);
        });
      });
    }
    function previewHtml() {
      const g = grid(), w = Math.min(cols(), 10);
      let h = '<table class="grid imp-grid"><tbody>';
      g.slice(0, 7).forEach((r, ri) => {
        h += "<tr>";
        for (let c = 0; c < w; c++) h += `<td class="${header && ri === 0 ? "imp-hd" : ""}">${escAttr(r[c] != null ? r[c] : "")}</td>`;
        h += "</tr>";
      });
      h += "</tbody></table>";
      if (cols() > 10) h += '<div class="muted small">Se muestran las primeras columnas.</div>';
      return h;
    }
    function mapHtml() {
      const w = MOD.wiz;
      if (!w || w.mode === "sheet") {
        return '<div class="muted small" style="margin-bottom:8px">Elige las hojas que quieres agregar como tablas:</div>' +
          '<div class="imp-sheets">' +
          sheets.map((s, i) => `<label class="chk"><input type="checkbox" data-sh="${i}" checked> ${escAttr(s.title)}</label>`).join("") +
          '</div>';
      }
      if (w.mode === "cols") {
        let h = (w.note ? `<div class="muted small" style="margin-bottom:8px">${w.note}</div>` : "") + '<div class="imp-fields">';
        w.fields.forEach((f, i) => {
          const def = (cfg.cols && cfg.cols[i] != null) ? Math.min(cfg.cols[i], cols() - 1) : Math.min(i, cols() - 1);
          h += `<div class="field"><label>${f}</label><select data-fld="${i}">${colOptions(def)}</select></div>`;
        });
        return h + "</div>";
      }
      if (!levels) levels = [mkLevel(0)];
      let h = '<div class="imp-levels">';
      levels.forEach((lv, li) => {
        h += `<div class="imp-level"><div class="imp-level-h">Nivel ${li + 1}${levels.length > 1 ? ` <button class="ft-x" type="button" data-rmlv="${li}">×</button>` : ""}</div>`;
        w.perLevel.forEach((pf, pi) => {
          h += pf.type === "text"
            ? `<div class="field"><label>${pf.label}</label><input data-pf="${pi}" value="${escAttr(lv[pi] || "")}" inputmode="decimal"></div>`
            : `<div class="field"><label>${pf.label}</label><select data-pf="${pi}">${colOptions(lv[pi] || 0)}</select></div>`;
        });
        h += "</div>";
      });
      return h + '</div><button class="btn sm" type="button" id="impAddLv">+ Agregar nivel</button>';
    }
    function render() {
      box.innerHTML =
        '<div class="modal-h"><h3>Importar de Excel</h3><button class="modal-x" type="button" id="impX">×</button></div>' +
        '<div class="modal-b">' +
          `<div class="field"><label>Hoja del libro</label><select id="impSheet">${sheets.map((s, i) => `<option value="${i}"${i === sIdx ? " selected" : ""}>${escAttr(s.title)}</option>`).join("")}</select></div>` +
          `<label class="chk"><input type="checkbox" id="impHdr"${header ? " checked" : ""}> La primera fila son encabezados</label>` +
          `<div class="imp-prev">${previewHtml()}</div>` +
          `<div class="imp-map">${mapHtml()}</div>` +
        '</div>' +
        '<div class="modal-f"><button class="btn ghost" type="button" id="impCancel">Cancelar</button><button class="btn solid" type="button" id="impDo">Importar</button></div>';
      box.querySelector("#impX").onclick = close;
      box.querySelector("#impCancel").onclick = close;
      box.querySelector("#impSheet").onchange = (e) => { sIdx = +e.target.value; header = autoHeader(); levels = null; render(); };
      box.querySelector("#impHdr").onchange = (e) => { if (MOD.wiz && MOD.wiz.mode === "levels") readLevels(); header = e.target.checked; render(); };
      const add = box.querySelector("#impAddLv");
      if (add) add.onclick = () => { readLevels(); levels.push(mkLevel(levels.length)); render(); };
      box.querySelectorAll("[data-rmlv]").forEach(b => b.onclick = () => { readLevels(); levels.splice(+b.dataset.rmlv, 1); render(); });
      box.querySelector("#impDo").onclick = doImport;
    }
    function buildTable(si) {
      const g = sheets[si].grid || [];
      const hdr = (g[0] || []).map((h, i) => header ? (String(h || "").trim() || "Columna " + (i + 1)) : "Columna " + (i + 1));
      const body = (header ? g.slice(1) : g).map(r => hdr.map((_, c) => r[c] != null ? String(r[c]) : ""));
      return { title: sheets[si].title, headers: hdr, rows: body };
    }
    function doImport() {
      const w = MOD.wiz, rows = dataRows();
      if (!w || w.mode === "sheet") {
        const picked = [];
        box.querySelectorAll("[data-sh]").forEach(ch => { if (ch.checked) picked.push(+ch.dataset.sh); });
        if (!picked.length) { alert("Elige al menos una hoja."); return; }
        MOD.importGrid(picked.map(buildTable));
        saveCfg({ header, sheet: sIdx });
      } else if (w.mode === "cols") {
        const sel = [];
        box.querySelectorAll("[data-fld]").forEach(s => sel[+s.dataset.fld] = parseInt(s.value, 10));
        MOD.importGrid(rows.map(r => sel.map(c => (r[c] != null ? r[c] : ""))));
        saveCfg({ header, sheet: sIdx, cols: sel });
      } else {
        readLevels();
        let g2;
        if (w.axis === "stats") {
          g2 = [levels.map(L => L[0] || "")];
          rows.forEach(r => g2.push(levels.map(L => (r[L[1]] != null ? r[L[1]] : ""))));
        } else {
          g2 = rows.map(r => { const out = []; levels.forEach(L => { out.push(r[L[0]] != null ? r[L[0]] : ""); out.push(r[L[1]] != null ? r[L[1]] : ""); }); return out; });
        }
        MOD.importGrid(g2);
        saveCfg({ header, sheet: sIdx, levels: levels.map(a => a.slice()) });
      }
      close();
    }
    render();
  }

  async function save(force = false) {
    const btn = document.getElementById("btnSave");
    try {
      const r = await fetch(SAVE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ payload: MOD.collect(), base_version: version, force }),
      });

      if (r.status === 409) {
        const info = await r.json();
        const overwrite = confirm(
          `${info.updated_by || "Otra persona"} guardó cambios en este módulo después de que lo abriste.\n\n` +
          "Aceptar: sobrescribir con lo que tienes ahora.\nCancelar: recargar para ver su versión.");
        if (overwrite) return save(true);
        location.reload();
        return;
      }
      if (!r.ok) throw new Error("HTTP " + r.status);

      const data = await r.json();
      version = data.version || version;
      const ei = document.getElementById("editInfo");
      if (ei) ei.innerHTML = "Última edición: <b>" + (data.updated_by || "tú") + "</b> (ahora)";
      btn.textContent = "Guardado ✓";
      setTimeout(() => (btn.textContent = "Guardar"), 1400);
    } catch (e) {
      alert("No se pudo guardar. Revisa tu conexión.");
    }
  }

  // ---- helper para tablas niveles × réplicas -------------------------------
  // Configuración por módulo para que cada tabla coincida con su hoja de Excel.
  const STATS_CFG = {
    preexa:    { top: "Concentración nominal",   named: false, sub: false, nlev: 3, nrep: 5,
                 footer: [["n", "n"], ["Promedio", "mean"], ["Desv. Est.", "sd"], ["CV (%)", "cv"], ["%desv", "dev"], ["Dictamen", "verdict"]] },
    estmues:   { top: "Concentración adicionada", named: true, names: ["MCB", "MCA"], sub: true, nlev: 2, nrep: 3,
                 footer: [["n", "n"], ["Promedio", "mean"], ["CV (%)", "cv"], ["%desv", "dev"], ["Dictamen", "verdict"]] },
    estmuepro: { top: "Concentración adicionada", named: true, names: ["MCB", "MCA"], sub: true, nlev: 2, nrep: 3,
                 footer: [["n", "n"], ["Promedio", "mean"], ["CV (%)", "cv"], ["%desv", "dev"], ["Dictamen", "verdict"]] },
    estaut:    { top: "Concentración adicionada", named: true, names: ["MCB", "MCA"], sub: true, nlev: 2, nrep: 3,
                 footer: [["n", "n"], ["Promedio", "mean"], ["CV (%)", "cv"], ["%desv", "dev"], ["Dictamen", "verdict"]] },
    ccd:       { top: "Concentración adicionada", named: true, names: ["MCB", "MCA"], sub: true, nlev: 2, nrep: 3,
                 footer: [["n", "n"], ["Promedio", "mean"], ["CV (%)", "cv"], ["%desv", "dev"], ["Desv. Est.", "sd"], ["Dictamen", "verdict"]] },
  };
  const STATS_DEFAULT = { top: "Concentración nominal", named: false, sub: false,
    footer: [["n", "n"], ["Promedio", "mean"], ["CV (%)", "cv"], ["%desv", "dev"], ["Desv. Est.", "sd"], ["Dictamen", "verdict"]] };
  const scfg = () => STATS_CFG[MODULE_ID] || STATS_DEFAULT;

  function statsTable(levels, reps, names) {
    const c = scfg();
    const nm = (l) => (names && names[l]) || (c.names && c.names[l]) || ("Nivel " + (l + 1));
    const wrap = el("div", { class: "tbl-wrap" });
    let h = '<table class="grid"><thead>';
    h += '<tr><th class="rowlab" rowspan="2">Réplica</th>';
    h += `<th colspan="${levels}">${c.top} (${UNIT})</th></tr>`;
    if (c.named) {
      h += "<tr>";
      for (let l = 0; l < levels; l++)
        h += `<th><input class="lvlname" data-role="lname" data-l="${l}" value="${escAttr(nm(l))}"></th>`;
      h += "</tr>";
    } else {
      // los valores nominales identifican cada nivel (van bajo el encabezado)
      h += "<tr>";
      for (let l = 0; l < levels; l++) h += `<th><input class="nomhd" data-role="nom" data-l="${l}" inputmode="decimal"></th>`;
      h += "</tr>";
    }
    h += "</thead><tbody>";
    if (c.named) {
      h += `<tr><td class="rowlab">${c.top} (${UNIT})</td>`;
      for (let l = 0; l < levels; l++) h += `<td><input data-role="nom" data-l="${l}" inputmode="decimal"></td>`;
      h += "</tr>";
    }
    h += '<tr><td class="band" colspan="' + (levels + 1) + `">Concentración cuantificada (${UNIT})</td></tr>`;
    for (let r = 0; r < reps; r++) {
      h += `<tr><td class="rowlab">${r + 1}</td>`;
      for (let l = 0; l < levels; l++) h += `<td><input data-role="rep" data-l="${l}" data-r="${r}" inputmode="decimal"></td>`;
      h += "</tr>";
    }
    h += "</tbody><tfoot>";
    for (const [lab, key] of c.footer) {
      h += `<tr><td class="rowlab">${lab}</td>`;
      for (let l = 0; l < levels; l++) h += `<td class="out" data-res="${key}" data-l="${l}"></td>`;
      h += "</tr>";
    }
    h += "</tfoot></table>";
    wrap.innerHTML = h;
    return wrap;
  }

  // =========================================================================
  // Módulos por tipo
  // =========================================================================
  const KINDS = {};

  // --- estadística (precisión, estabilidades, interferencias, seguimiento) --
  KINDS.stats = {
    levels: 3, reps: 5,
    hint: "Excel: 1ª fila = concentración nominal por nivel (columnas); filas siguientes = réplicas.",
    wiz: { mode: "levels", axis: "stats", perLevel: [{ label: "Concentración nominal", type: "text" }, { label: "Columna de réplicas", type: "col" }] },
    importGrid(g) {
      if (!g.length) return;
      const nom = g[0], reps = g.slice(1), w = width(g);
      const levels = [];
      for (let c = 0; c < w; c++) levels.push({ nominal: nom[c] || "", replicates: col(reps, c) });
      loadInto({ limits: { cv: 15, dev: 15, cv_lic: 20, dev_lic: 20 }, levels });
    },
    build() {
      const c = scfg();
      if (saved.levels && saved.levels.length) {
        this.levels = Math.max(1, saved.levels.length);
        const mr = Math.max.apply(null, saved.levels.map(l => (l.replicates || []).length));
        if (mr > 0) this.reps = mr;
      }
      if (c.sub) {
        const s = el("div", { class: "st-sub" });
        s.innerHTML = `<label>Condición</label><input id="stSubtitle" placeholder="p. ej. A CORTO PLAZO 3 HORAS" value="${escAttr(saved.subtitle || "")}">`;
        root.appendChild(s);
      }
      root.appendChild(el("div", {}, fx([
        "Promedio = PROMEDIO(x)", "DE = DESVEST(x) · n−1",
        "CV% = DE / Promedio × 100", "%desv = 100 × (nominal − Promedio) / nominal"])));
      root.appendChild(controls([
        { label: "niveles", get: () => this.levels, set: (n) => this.levels = n, min: 1 },
        { label: "réplicas", get: () => this.reps, set: (n) => this.reps = n, min: 1 },
      ]));
      root.appendChild(statsTable(this.levels, this.reps, (saved.levels || []).map(l => l.label)));
      hydrate(saved);
    },
    collect() {
      const c = scfg();
      const levels = [];
      for (let l = 0; l < this.levels; l++) {
        const nom = val(`[data-role=nom][data-l='${l}']`);
        const reps = [];
        for (let r = 0; r < this.reps; r++) reps.push(val(`[data-role=rep][data-l='${l}'][data-r='${r}']`));
        const lvl = { nominal: nom, replicates: reps };
        if (c.named) lvl.label = val(`[data-role=lname][data-l='${l}']`);
        levels.push(lvl);
      }
      const out = { limits: { cv: 15, dev: 15, cv_lic: 20, dev_lic: 20 }, levels };
      if (c.sub) { const s = q("#stSubtitle"); if (s) out.subtitle = s.value; }
      return out;
    },
    render(res) {
      (res.levels || []).forEach((s, l) => {
        setRes("n", l, s.n || 0);
        ["mean", "sd", "cv", "dev"].forEach(k => setRes(k, l, fmt(s[k])));
        const cell = q(`[data-res=verdict][data-l='${l}']`);
        if (cell) { cell.innerHTML = verdictTag(s.verdict); cell.className = "out " + cls(s.verdict === "CUMPLE" ? true : s.verdict === "NO CUMPLE" ? false : null); }
        ["cv", "dev"].forEach(k => {
          const c = q(`[data-res=${k}][data-l='${l}']`);
          if (c) c.className = "out " + (s["ok_" + (k === "cv" ? "cv" : "dev")] === null ? "" : cls(s["ok_" + (k === "cv" ? "cv" : "dev")]));
        });
      });
    },
  };

  // --- aptitud del sistema --------------------------------------------------
  KINDS.suitability = {
    inj: 6,
    hint: "Excel: 2 columnas — área del analito y área del EI; una fila por inyección.",
    wiz: { mode: "cols", fields: ["Área del analito", "Área del EI"] },
    importGrid(g) {
      loadInto({ cv_limit: 2, runs: [{ injections: g.map(r => ({ analyte: r[0] || "", is: r[1] || "" })) }] });
    },
    build() {
      if (saved.runs && saved.runs[0] && saved.runs[0].injections)
        this.inj = Math.max(1, saved.runs[0].injections.length);
      root.appendChild(el("div", {}, fx([
        "Relación = Área analito ÷ Área EI", "CV% = DESVEST(relaciones) / Promedio × 100"])));
      root.appendChild(controls([
        { label: "inyecciones", get: () => this.inj, set: (n) => this.inj = n, min: 1 },
      ]));
      const wrap = el("div", { class: "tbl-wrap" });
      let h = '<table class="grid"><thead><tr><th class="rowlab">Inyección</th><th>Área del analito</th><th>Área del EI</th><th>Relación de Áreas</th></tr></thead><tbody>';
      for (let i = 0; i < this.inj; i++) {
        h += `<tr><td class="rowlab">Inyección ${i + 1}</td>
          <td><input data-role="a" data-i="${i}" inputmode="decimal"></td>
          <td><input data-role="ei" data-i="${i}" inputmode="decimal"></td>
          <td class="out" data-res="rel" data-i="${i}"></td></tr>`;
      }
      h += '</tbody><tfoot><tr><td class="rowlab">Promedio</td><td class="out" data-res="mean" colspan="3"></td></tr>';
      h += '<tr><td class="rowlab">CV (%)</td><td class="out" data-res="cv" colspan="2"></td><td class="out" data-res="verdict"></td></tr></tfoot></table>';
      wrap.innerHTML = h; root.appendChild(wrap);
      hydrate(saved);
    },
    collect() {
      const inj = [];
      for (let i = 0; i < this.inj; i++)
        inj.push({ analyte: val(`[data-role=a][data-i='${i}']`), is: val(`[data-role=ei][data-i='${i}']`) });
      return { cv_limit: 2, runs: [{ injections: inj }] };
    },
    render(res) {
      const run = (res.runs || [])[0]; if (!run) return;
      (run.ratios || []).forEach((r, i) => setRes("rel", i, fmt(r)));
      setRes("mean", null, fmt(run.mean));
      const cv = q("[data-res=cv]"); if (cv) cv.textContent = fmt(run.cv);
      const v = q("[data-res=verdict]"); if (v) v.innerHTML = verdictTag(run.verdict);
    },
  };

  // --- curva de calibración -------------------------------------------------
  KINDS.curve = {
    levels: 7,
    hint: "Excel: 2 columnas — concentración nominal y respuesta; una fila por nivel.",
    wiz: { mode: "cols", fields: ["Concentración nominal", "Respuesta"] },
    importGrid(g) {
      loadInto({ weight: (saved.weight || "1"), limits: { r: 0.99, error: 15 },
                 levels: g.map(r => ({ nominal: r[0] || "", response: r[1] || "" })) });
    },
    build() {
      if (saved.levels && saved.levels.length) this.levels = Math.max(2, saved.levels.length);
      root.appendChild(el("div", {}, fx([
        "Respuesta = a + b × Conc", "Conc. calc = (Respuesta − a) / b",
        "% cuantificado = Conc. calc / nominal × 100", "% error = |100 − % cuantificado|"])));
      root.appendChild(controls([
        { label: "niveles", get: () => this.levels, set: (n) => this.levels = n, min: 2 },
      ]));
      const sel = el("div", { class: "inline-form", style: "margin-bottom:14px" });
      sel.innerHTML = `<div class="field" style="margin:0"><label>Ponderación</label>
        <select id="weight">
          <option value="1">1 (sin ponderar)</option><option value="1/x">1/x</option>
          <option value="1/x2">1/x²</option><option value="1/y">1/y</option><option value="1/y2">1/y²</option>
        </select></div>`;
      root.appendChild(sel);
      const wrap = el("div", { class: "tbl-wrap" });
      let h = `<table class="grid"><thead><tr><th class="rowlab">Nivel</th><th>Conc. nominal (${UNIT})</th><th>Respuesta (rel. áreas)</th><th>Conc. calculada</th><th>% cuantificado</th><th>% error</th></tr></thead><tbody>`;
      for (let l = 0; l < this.levels; l++) {
        h += `<tr><td class="rowlab">Nivel ${l + 1}</td>
          <td><input data-role="nom" data-l="${l}" inputmode="decimal"></td>
          <td><input data-role="resp" data-l="${l}" inputmode="decimal"></td>
          <td class="out" data-res="calc" data-l="${l}"></td>
          <td class="out" data-res="pq" data-l="${l}"></td>
          <td class="out" data-res="err" data-l="${l}"></td></tr>`;
      }
      h += "</tbody></table>";
      wrap.innerHTML = h; root.appendChild(wrap);
      root.appendChild(el("div", { class: "result-line", id: "regline" }, '<span class="muted small">Captura datos para ver la regresión.</span>'));
      document.getElementById("weight").addEventListener("change", () => { saved.weight = document.getElementById("weight").value; scheduleCompute(); });
      hydrate(saved);
    },
    collect() {
      const levels = [];
      for (let l = 0; l < this.levels; l++)
        levels.push({ nominal: val(`[data-role=nom][data-l='${l}']`), response: val(`[data-role=resp][data-l='${l}']`) });
      return { weight: document.getElementById("weight").value, limits: { r: 0.99, error: 15 }, levels };
    },
    render(res) {
      (res.points || []).forEach((p, l) => {
        setRes("calc", l, fmt(p.calc)); setRes("pq", l, fmt(p.pct_quant));
        const e = q(`[data-res=err][data-l='${l}']`);
        if (e) { e.textContent = fmt(p.error); e.className = "out " + (p.ok === null ? "" : cls(p.ok)); }
      });
      const reg = res.regression, line = document.getElementById("regline");
      if (reg && line) {
        line.innerHTML =
          `<span class="kv"><span class="k">Pendiente (b)</span><span class="v">${fmt(reg.slope)}</span></span>` +
          `<span class="kv"><span class="k">Ordenada (a)</span><span class="v">${fmt(reg.intercept)}</span></span>` +
          `<span class="kv"><span class="k">r</span><span class="v">${fmt(reg.r)}</span></span>` +
          `<span class="kv"><span class="k">n</span><span class="v">${reg.n}</span></span>` +
          verdictTag(res.r_ok === null ? "—" : res.r_ok ? "CUMPLE" : "NO CUMPLE");
      } else if (line) {
        line.innerHTML = '<span class="muted small">Captura datos para ver la regresión.</span>';
      }
    },
  };

  // --- recobro --------------------------------------------------------------
  KINDS.recovery = {
    levels: [["mcb", "MCB (baja)"], ["mcm", "MCM (media)"], ["mca", "MCA (alta)"]], reps: 3,
    hint: "Excel: columnas por pares (solución, matriz) por nivel; filas = réplicas.",
    wiz: { mode: "levels", axis: "rec", perLevel: [{ label: "Columna solución", type: "col" }, { label: "Columna matriz", type: "col" }] },
    importGrid(g) {
      const w = width(g), nlev = Math.max(1, Math.floor(w / 2)), levels = [];
      for (let k = 0; k < nlev; k++)
        levels.push({ id: "lvl" + k, label: "Nivel " + (k + 1), solution: col(g, 2 * k), matrix: col(g, 2 * k + 1) });
      loadInto({ limits: { cv: 15 }, levels });
    },
    build() {
      if (saved.levels && saved.levels.length) {
        this.levels = saved.levels.map((lv, i) => [lv.id || ("lvl" + i), lv.label || ("Nivel " + (i + 1))]);
        const mr = Math.max.apply(null, saved.levels.map(l => Math.max((l.solution || []).length, (l.matrix || []).length)));
        if (mr > 0) this.reps = mr;
      }
      root.appendChild(el("div", {}, fx([
        "Prom. solución / Prom. matriz = PROMEDIO(réplicas)",
        "%Recobro = Prom. matriz × 100 / Prom. solución", "CV% = DESVEST(niveles) / Promedio × 100"])));
      root.appendChild(controls([
        { label: "niveles", get: () => this.levels.length, set: (n) => {
            while (this.levels.length < n) this.levels.push(["lvl" + this.levels.length, "Nivel " + (this.levels.length + 1)]);
            while (this.levels.length > n) this.levels.pop();
          }, min: 1 },
        { label: "réplicas", get: () => this.reps, set: (n) => this.reps = n, min: 1 },
      ]));
      const wrap = el("div", { class: "tbl-wrap" });
      let h = '<table class="grid"><thead><tr><th class="rowlab">Réplica</th>';
      this.levels.forEach(([id, lab]) => h += `<th>${lab} · solución</th><th>${lab} · matriz</th>`);
      h += "</tr></thead><tbody>";
      for (let r = 0; r < this.reps; r++) {
        h += `<tr><td class="rowlab">Réplica ${r + 1}</td>`;
        this.levels.forEach(([id]) => h += `<td><input data-role="sol" data-l="${id}" data-r="${r}" inputmode="decimal"></td><td><input data-role="mat" data-l="${id}" data-r="${r}" inputmode="decimal"></td>`);
        h += "</tr>";
      }
      h += '</tbody><tfoot><tr><td class="rowlab">% Recobro</td>';
      this.levels.forEach(([id]) => h += `<td class="out" data-res="rec" data-l="${id}" colspan="2"></td>`);
      h += "</tr></tfoot></table>";
      wrap.innerHTML = h; root.appendChild(wrap);
      root.appendChild(el("div", { class: "result-line", id: "recline" }));
      hydrate(saved);
    },
    collect() {
      const levels = this.levels.map(([id, label]) => {
        const sol = [], mat = [];
        for (let r = 0; r < this.reps; r++) { sol.push(val(`[data-role=sol][data-l='${id}'][data-r='${r}']`)); mat.push(val(`[data-role=mat][data-l='${id}'][data-r='${r}']`)); }
        return { id, label, solution: sol, matrix: mat };
      });
      return { limits: { cv: 15 }, levels };
    },
    render(res) {
      (res.levels || []).forEach((lv, i) => {
        const id = this.levels[i][0];
        const c = q(`[data-res=rec][data-l='${id}']`); if (c) c.textContent = fmt(lv.recovery) + " %";
      });
      const o = res.overall, line = document.getElementById("recline");
      if (line) line.innerHTML =
        `<span class="kv"><span class="k">Recobro promedio</span><span class="v">${fmt(o.mean)} %</span></span>` +
        `<span class="kv"><span class="k">CV del recobro</span><span class="v">${fmt(o.cv)} %</span></span>` +
        verdictTag(o.verdict);
    },
  };

  // --- efecto matriz (FMN) --------------------------------------------------
  KINDS.matrix = {
    lots: 3,
    hint: "Excel: 1ª fila = referencia en solución (área analito, área EI); filas siguientes = lotes.",
    wiz: { mode: "cols", note: "La primera fila mapeada es la referencia en solución; las siguientes son los lotes.", fields: ["Área del analito", "Área del EI"] },
    importGrid(g) {
      const ref = g[0] || [], lots = g.slice(1);
      loadInto({ reference: { analyte: ref[0] || "", is: ref[1] || "" }, limits: { cv: 15 },
                 lots: lots.map(r => ({ analyte: r[0] || "", is: r[1] || "" })) });
    },
    build() {
      if (saved.lots && saved.lots.length) this.lots = Math.max(1, saved.lots.length);
      root.appendChild(el("div", {}, fx([
        "Relación = Área analito ÷ Área EI", "FMN = Relación(matriz) ÷ Relación(solución)",
        "CV% = DESVEST(FMN) / Promedio × 100"])));
      root.appendChild(controls([
        { label: "lotes", get: () => this.lots, set: (n) => this.lots = n, min: 1 },
      ]));
      const ref = el("div", { class: "card", style: "margin-bottom:14px" });
      ref.innerHTML = `<div class="card-h"><h3>Referencia en solución</h3></div><div class="card-b grid-fields">
        <div class="field"><label>Área analito (solución)</label><input data-role="ref-a" inputmode="decimal"></div>
        <div class="field"><label>Área EI (solución)</label><input data-role="ref-ei" inputmode="decimal"></div></div>`;
      root.appendChild(ref);
      const wrap = el("div", { class: "tbl-wrap" });
      let h = '<table class="grid"><thead><tr><th class="rowlab">Lote</th><th>Área analito (matriz)</th><th>Área EI (matriz)</th><th>FMN</th></tr></thead><tbody>';
      for (let l = 0; l < this.lots; l++)
        h += `<tr><td class="rowlab">Lote ${l + 1}</td>
          <td><input data-role="a" data-l="${l}" inputmode="decimal"></td>
          <td><input data-role="ei" data-l="${l}" inputmode="decimal"></td>
          <td class="out" data-res="fmn" data-l="${l}"></td></tr>`;
      h += "</tbody></table>";
      wrap.innerHTML = h; root.appendChild(wrap);
      root.appendChild(el("div", { class: "result-line", id: "mxline" }));
      hydrate(saved);
    },
    collect() {
      const lots = [];
      for (let l = 0; l < this.lots; l++) lots.push({ analyte: val(`[data-role=a][data-l='${l}']`), is: val(`[data-role=ei][data-l='${l}']`) });
      return { reference: { analyte: val("[data-role=ref-a]"), is: val("[data-role=ref-ei]") }, limits: { cv: 15 }, lots };
    },
    render(res) {
      (res.lots || []).forEach((lt, l) => setRes("fmn", l, fmt(lt.fmn)));
      const o = res.overall, line = document.getElementById("mxline");
      if (line) line.innerHTML =
        `<span class="kv"><span class="k">FMN promedio</span><span class="v">${fmt(o.mean)}</span></span>` +
        `<span class="kv"><span class="k">CV del FMN</span><span class="v">${fmt(o.cv)} %</span></span>` +
        verdictTag(o.verdict);
    },
  };

  // --- acarreo / selectividad ----------------------------------------------
  KINDS.ratio = {
    rows: 3,
    hint: "Excel: 4 columnas — blanco analito, ref. analito, blanco EI, ref. EI; una fila por lote.",
    wiz: { mode: "cols", fields: ["Blanco analito", "Ref. analito", "Blanco EI", "Ref. EI"] },
    importGrid(g) {
      loadInto({ limits: { analyte: 20, is: 5 },
                 rows: g.map(r => ({ blank_analyte: r[0] || "", ref_analyte: r[1] || "",
                                     blank_is: r[2] || "", ref_is: r[3] || "" })) });
    },
    build() {
      if (saved.rows && saved.rows.length) this.rows = Math.max(1, saved.rows.length);
      root.appendChild(el("div", {}, fx(["% respuesta = Área del blanco × 100 ÷ Área de referencia"])));
      root.appendChild(controls([
        { label: "filas", get: () => this.rows, set: (n) => this.rows = n, min: 1 },
      ]));
      const wrap = el("div", { class: "tbl-wrap" });
      let h = '<table class="grid"><thead><tr><th class="rowlab">Lote</th><th>Blanco analito</th><th>Ref. analito</th><th>% analito</th><th>Blanco EI</th><th>Ref. EI</th><th>% EI</th></tr></thead><tbody>';
      for (let r = 0; r < this.rows; r++)
        h += `<tr><td class="rowlab">Lote ${r + 1}</td>
          <td><input data-role="ba" data-r="${r}" inputmode="decimal"></td>
          <td><input data-role="ra" data-r="${r}" inputmode="decimal"></td>
          <td class="out" data-res="pa" data-r="${r}"></td>
          <td><input data-role="be" data-r="${r}" inputmode="decimal"></td>
          <td><input data-role="re" data-r="${r}" inputmode="decimal"></td>
          <td class="out" data-res="pe" data-r="${r}"></td></tr>`;
      h += "</tbody></table>";
      wrap.innerHTML = h; root.appendChild(wrap);
      hydrate(saved);
    },
    collect() {
      const rows = [];
      for (let r = 0; r < this.rows; r++) rows.push({
        blank_analyte: val(`[data-role=ba][data-r='${r}']`), ref_analyte: val(`[data-role=ra][data-r='${r}']`),
        blank_is: val(`[data-role=be][data-r='${r}']`), ref_is: val(`[data-role=re][data-r='${r}']`),
      });
      return { limits: { analyte: 20, is: 5 }, rows };
    },
    render(res) {
      (res.rows || []).forEach((row, r) => {
        const a = q(`[data-res=pa][data-r='${r}']`); if (a) { a.textContent = fmt(row.analyte_pct); a.className = "out " + (row.ok_analyte === null ? "" : cls(row.ok_analyte)); }
        const e = q(`[data-res=pe][data-r='${r}']`); if (e) { e.textContent = fmt(row.is_pct); e.className = "out " + (row.ok_is === null ? "" : cls(row.ok_is)); }
      });
    },
  };

  // --- tabla personalizada (libre) -----------------------------------------
  KINDS.free = {
    tables: null,
    hint: "Excel: cada hoja del libro se agrega como una tabla (1ª fila = encabezados).",
    wiz: { mode: "sheet" },
    importGrid(tables) {
      freeApply(data => (tables || []).forEach(t =>
        data.tables.push({ title: t.title, headers: t.headers, rows: t.rows })));
    },
    build() {
      this.tables = (saved.tables && saved.tables.length) ? saved.tables : [
        { title: "Tabla 1", headers: ["Columna 1", "Columna 2", "Columna 3"],
          rows: [["", "", ""], ["", "", ""], ["", "", ""]] },
      ];
      root.appendChild(el("div", {}, '<div class="fx"><b>Tabla libre:</b>' +
        '<code>Agrega tablas, filas y columnas; escribe en cualquier celda.</code>' +
        '<code>Bajo cada columna numérica se calculan n, promedio, DE y CV%.</code></div>'));

      this.tables.forEach((t, ti) => {
        const card = el("div", { class: "free-table" });
        let h = '<div class="ft-head">' +
          `<input class="ft-title" data-role="title" data-t="${ti}" value="${escAttr(t.title || ("Tabla " + (ti + 1)))}">` +
          `<button type="button" class="btn danger sm" data-act="del-table" data-t="${ti}">Eliminar tabla</button></div>`;
        h += '<div class="tbl-wrap"><table class="grid free-grid"><thead><tr><th class="rowlab"></th>';
        t.headers.forEach((hd, c) => {
          h += `<th><input class="ft-h" data-role="header" data-t="${ti}" data-c="${c}" value="${escAttr(hd)}">` +
            `<button type="button" class="ft-x" data-act="del-col" data-t="${ti}" data-c="${c}" title="Quitar columna">×</button></th>`;
        });
        h += `<th class="ft-add"><button type="button" class="szbtn" data-act="add-col" data-t="${ti}" title="Agregar columna">+</button></th></tr></thead><tbody>`;
        t.rows.forEach((row, r) => {
          h += `<tr><td class="rowlab"><button type="button" class="ft-x" data-act="del-row" data-t="${ti}" data-r="${r}" title="Quitar fila">×</button> ${r + 1}</td>`;
          t.headers.forEach((hd, c) => {
            h += `<td><input data-role="cell" data-t="${ti}" data-r="${r}" data-c="${c}" value="${escAttr(row[c])}"></td>`;
          });
          h += "<td></td></tr>";
        });
        h += "</tbody><tfoot>";
        [["n", "n"], ["Promedio", "mean"], ["Desv. Est.", "sd"], ["CV (%)", "cv"]].forEach(([lab, key]) => {
          h += `<tr><td class="rowlab">${lab}</td>`;
          t.headers.forEach((hd, c) => h += `<td class="out" data-res="${key}" data-t="${ti}" data-c="${c}"></td>`);
          h += "<td></td></tr>";
        });
        h += "</tfoot></table></div>";
        h += `<button type="button" class="btn sm" data-act="add-row" data-t="${ti}">+ Fila</button>`;
        card.innerHTML = h;
        root.appendChild(card);
      });

      root.appendChild(el("button",
        { type: "button", class: "btn solid sm", "data-act": "add-table", style: "margin-top:10px" },
        "+ Agregar tabla"));

      root.querySelectorAll("[data-act]").forEach((b) => {
        const t = b.dataset.t === undefined ? -1 : +b.dataset.t;
        const c = b.dataset.c === undefined ? -1 : +b.dataset.c;
        const r = b.dataset.r === undefined ? -1 : +b.dataset.r;
        const act = b.dataset.act;
        b.addEventListener("click", () => {
          if (act === "add-table") return freeApply(d => d.tables.push({ title: "Tabla " + (d.tables.length + 1), headers: ["Columna 1", "Columna 2"], rows: [["", ""], ["", ""]] }));
          if (act === "del-table") return freeApply(d => { if (d.tables.length > 1) d.tables.splice(t, 1); });
          if (act === "add-col") return freeApply(d => { d.tables[t].headers.push("Columna " + (d.tables[t].headers.length + 1)); d.tables[t].rows.forEach(row => row.push("")); });
          if (act === "del-col") return freeApply(d => { if (d.tables[t].headers.length > 1) { d.tables[t].headers.splice(c, 1); d.tables[t].rows.forEach(row => row.splice(c, 1)); } });
          if (act === "add-row") return freeApply(d => d.tables[t].rows.push(d.tables[t].headers.map(() => "")));
          if (act === "del-row") return freeApply(d => { if (d.tables[t].rows.length > 1) d.tables[t].rows.splice(r, 1); });
        });
      });
    },
    collect() {
      const tables = [];
      root.querySelectorAll(".free-grid").forEach((tbl) => {
        const card = tbl.closest(".free-table");
        const titleEl = card ? card.querySelector('[data-role="title"]') : null;
        const headers = [];
        tbl.querySelectorAll('[data-role="header"]').forEach(hh => headers.push(hh.value));
        const rowsMap = {};
        tbl.querySelectorAll('[data-role="cell"]').forEach((inp) => {
          const r = +inp.dataset.r, c = +inp.dataset.c;
          (rowsMap[r] = rowsMap[r] || [])[c] = inp.value;
        });
        const rows = Object.keys(rowsMap).map(Number).sort((a, b) => a - b).map((r) => {
          const arr = rowsMap[r];
          for (let i = 0; i < headers.length; i++) if (arr[i] == null) arr[i] = "";
          return arr.slice(0, headers.length);
        });
        tables.push({ title: titleEl ? titleEl.value : "Tabla", headers, rows });
      });
      return { tables };
    },
    render(res) {
      (res.tables || []).forEach((t, ti) => {
        (t.stats || []).forEach((s, c) => {
          setFree("n", ti, c, s.n || 0);
          ["mean", "sd", "cv"].forEach(k => setFree(k, ti, c, fmt(s[k])));
        });
      });
    },
  };

  // ---- helpers de DOM ------------------------------------------------------
  function q(sel) { return root.querySelector(sel); }
  function val(sel) { const n = q(sel); return n ? n.value : ""; }
  function setRes(key, l, text) { const sel = l === null ? `[data-res=${key}]` : `[data-res=${key}][data-l='${l}']`; const n = q(sel); if (n) n.textContent = text; }

  // rehidratar inputs desde lo guardado (estructura espejo de collect)
  function hydrate(data) {
    if (!data) return;
    if (data.weight) { const w = document.getElementById("weight"); if (w) w.value = data.weight; }
    // las claves guardadas son exactamente el payload de collect(); reasignamos por rol
    const apply = (sel, v) => { const n = q(sel); if (n != null && v != null && v !== "") n.value = v; };
    try {
      if (KIND === "stats" && data.levels) data.levels.forEach((lv, l) => {
        apply(`[data-role=nom][data-l='${l}']`, lv.nominal);
        (lv.replicates || []).forEach((rv, r) => apply(`[data-role=rep][data-l='${l}'][data-r='${r}']`, rv));
      });
      if (KIND === "suitability" && data.runs) (data.runs[0].injections || []).forEach((inj, i) => {
        apply(`[data-role=a][data-i='${i}']`, inj.analyte); apply(`[data-role=ei][data-i='${i}']`, inj.is);
      });
      if (KIND === "curve" && data.levels) data.levels.forEach((lv, l) => {
        apply(`[data-role=nom][data-l='${l}']`, lv.nominal); apply(`[data-role=resp][data-l='${l}']`, lv.response);
      });
      if (KIND === "recovery" && data.levels) data.levels.forEach((lv) => {
        (lv.solution || []).forEach((s, r) => apply(`[data-role=sol][data-l='${lv.id}'][data-r='${r}']`, s));
        (lv.matrix || []).forEach((s, r) => apply(`[data-role=mat][data-l='${lv.id}'][data-r='${r}']`, s));
      });
      if (KIND === "matrix") {
        apply("[data-role=ref-a]", (data.reference || {}).analyte); apply("[data-role=ref-ei]", (data.reference || {}).is);
        (data.lots || []).forEach((lt, l) => { apply(`[data-role=a][data-l='${l}']`, lt.analyte); apply(`[data-role=ei][data-l='${l}']`, lt.is); });
      }
      if (KIND === "ratio" && data.rows) data.rows.forEach((row, r) => {
        apply(`[data-role=ba][data-r='${r}']`, row.blank_analyte); apply(`[data-role=ra][data-r='${r}']`, row.ref_analyte);
        apply(`[data-role=be][data-r='${r}']`, row.blank_is); apply(`[data-role=re][data-r='${r}']`, row.ref_is);
      });
    } catch (e) { /* datos antiguos incompatibles: se ignoran */ }
  }

  // ---- arranque ------------------------------------------------------------
  const MOD = KINDS[KIND];
  if (!MOD) { root.innerHTML = '<div class="notice">Módulo no disponible.</div>'; return; }
  if (KIND === "stats" && !(saved.levels && saved.levels.length)) {
    const c = scfg();
    if (c.nlev) MOD.levels = c.nlev;
    if (c.nrep) MOD.reps = c.nrep;
  }
  MOD.build();
  root.addEventListener("input", scheduleCompute);
  document.getElementById("btnSave").addEventListener("click", () => save());

  // Ayuda de formato e importación desde Excel (disponible en todos los módulos).
  const hintEl = document.getElementById("importHint");
  if (hintEl && MOD.hint) hintEl.textContent = MOD.hint;
  const importInput = document.getElementById("xlsxFile");
  const importBtn = document.getElementById("btnImport");
  if (importBtn && importInput) {
    importBtn.addEventListener("click", () => importInput.click());
    importInput.addEventListener("change", async () => {
      if (!importInput.files.length) return;
      const orig = importBtn.textContent;
      importBtn.disabled = true; importBtn.textContent = "Importando…";
      try {
        const fd = new FormData();
        fd.append("file", importInput.files[0]);
        const r = await fetch(IMPORT_URL, { method: "POST", headers: { "X-CSRFToken": CSRF }, body: fd });
        const d = await r.json();
        if (!r.ok) {
          alert(d.error || "No se pudo importar el archivo.");
        } else if ((d.tables || []).length) {
          openImportWizard(d.tables);
        } else {
          alert("El archivo no contenía datos legibles.");
        }
      } catch (e) {
        alert("No se pudo importar el archivo.");
      }
      importInput.value = ""; importBtn.disabled = false; importBtn.textContent = orig;
    });
  }

  // decimales (sólo presentación; el cálculo ya es de precisión completa)
  const decVal = document.getElementById("decVal");
  const setDec = (d) => { DEC = Math.max(0, Math.min(10, d)); decVal.textContent = DEC; document.getElementById("decMinus").disabled = DEC <= 0; document.getElementById("decPlus").disabled = DEC >= 10; rerender(); };
  document.getElementById("decMinus").addEventListener("click", () => setDec(DEC - 1));
  document.getElementById("decPlus").addEventListener("click", () => setDec(DEC + 1));
  setDec(DEC);

  runCompute();   // primer cálculo con lo guardado
})();
