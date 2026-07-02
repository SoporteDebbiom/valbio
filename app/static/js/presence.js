(() => {
  "use strict";
  const countEl = document.getElementById("onlineCount");
  const listEl = document.getElementById("onlineList");
  const btn = document.getElementById("presenceBtn");
  const pop = document.getElementById("presencePop");
  const feed = document.getElementById("activityFeed");
  if (!countEl) return;

  const ICONS = { login: "→", sheet: "▤", data: "✎", user: "◍", backup: "⛁", general: "•" };

  btn.addEventListener("click", () => { pop.hidden = !pop.hidden; });
  document.addEventListener("click", (e) => {
    if (!pop.hidden && !e.target.closest("#presence")) pop.hidden = true;
  });

  function ago(iso) {
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (d < 60) return "hace un momento";
    if (d < 3600) return `hace ${Math.floor(d / 60)} min`;
    if (d < 86400) return `hace ${Math.floor(d / 3600)} h`;
    return new Date(iso).toLocaleDateString("es-MX");
  }

  function renderOnline(you, online) {
    countEl.textContent = online.length;
    listEl.innerHTML = online.map(u => `
      <li><span class="dot"></span>${u.username}${u.username === you ? " <em>(tú)</em>" : ""}
      <span class="role">${u.role}</span></li>`).join("")
      || '<li class="muted small">Nadie más por ahora.</li>';
  }

  function renderFeed(recent) {
    if (!feed) return;
    feed.innerHTML = recent.map(a => `
      <li class="act act-${a.category}">
        <span class="act-ic">${ICONS[a.category] || ICONS.general}</span>
        <span class="act-main"><b>${a.user || "—"}</b> ${a.action}</span>
        <span class="act-time">${ago(a.time)}</span>
      </li>`).join("");
  }

  async function tick() {
    try {
      const r = await fetch("/api/presence", { headers: { "Accept": "application/json" } });
      if (!r.ok) return;
      const d = await r.json();
      renderOnline(d.you, d.online || []);
      renderFeed(d.recent || []);
    } catch (e) { /* sin conexión momentánea */ }
  }

  tick();
  setInterval(tick, 25000);
})();
