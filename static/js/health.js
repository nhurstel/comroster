/* Page Santé : monitoring de l'appliance. Rend un instantané /api/health en cartes,
   actualisation automatique (suspendue onglet caché). Tout est tolérant à l'absence
   (champ null hors Pi → « indisponible »). */
(() => {
  "use strict";

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // — formatage —
  const bytes = (n) => {
    if (n == null) return "—";
    const u = ["o", "Ko", "Mo", "Go", "To"];
    let i = 0, v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(i >= 2 ? 1 : 0)} ${u[i]}`;
  };
  const duration = (s) => {
    if (s == null) return "—";
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d) return `${d} j ${h} h`;
    if (h) return `${h} h ${m} min`;
    return `${m} min`;
  };
  const when = (iso) => {
    try { return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
    catch { return "—"; }
  };
  const pct = (used, total) => (total ? Math.round(used / total * 100) : 0);

  // — briques d'affichage —
  const row = (k, v, tone) => `<div class="h-row"><span class="h-key">${esc(k)}</span>`
    + `<span class="h-val${tone ? " " + tone : ""}">${v}</span></div>`;
  const gauge = (p, tone) => `<div class="h-gauge"><div class="h-gauge-fill ${tone || ""}" data-pct="${p}"></div></div>`;
  const dot = (label, on, warn) => `<span class="h-flag ${on ? (warn ? "bad" : "ok") : "muted"}">${esc(label)}</span>`;

  function card(title, body) { return `<section class="h-card"><h2>${esc(title)}</h2>${body}</section>`; }

  function render(d) {
    const cards = [];

    // Processeur
    const cpu = d.cpu || {};
    const temp = cpu.temp_c;
    const tempTone = temp == null ? "" : temp >= 80 ? "bad" : temp >= 70 ? "warn" : "ok";
    const th = cpu.throttled;
    let cpuBody = row("Température", temp == null ? "indisponible" : `${temp} °C`, tempTone)
      + row("Charge (1 / 5 / 15 min)", cpu.load ? cpu.load.join("  ·  ") : "—")
      + row("Cœurs", cpu.cores ?? "—");
    if (th) {
      cpuBody += `<div class="h-flags">`
        + dot("Sous-tension", th.undervoltage_now, true)
        + dot("Throttling", th.throttled_now, true)
        + dot("Limite thermique", th.temp_limit_now, true)
        + `</div>`;
      const past = th.undervoltage_past || th.throttled_past || th.temp_limit_past;
      if (past) cpuBody += `<p class="h-note">Depuis le démarrage : `
        + [th.undervoltage_past && "sous-tension", th.throttled_past && "throttling", th.temp_limit_past && "limite thermique"]
          .filter(Boolean).join(", ") + ".</p>";
    } else {
      cpuBody += `<p class="h-note">Throttling : indisponible (hors Raspberry Pi).</p>`;
    }
    cards.push(card("Processeur", cpuBody));

    // Mémoire
    const m = d.memory;
    cards.push(card("Mémoire vive", m
      ? row("Utilisée", `${bytes(m.used)} / ${bytes(m.total)}`, pct(m.used, m.total) >= 90 ? "bad" : "")
        + gauge(pct(m.used, m.total), pct(m.used, m.total) >= 90 ? "bad" : pct(m.used, m.total) >= 75 ? "warn" : "ok")
        + row("Disponible", bytes(m.available))
      : `<p class="h-note">Indisponible (hors Linux).</p>`));

    // Disque (carte SD)
    const dk = d.disk;
    cards.push(card("Stockage (carte SD)", dk
      ? row("Occupé", `${bytes(dk.used)} / ${bytes(dk.total)}`, pct(dk.used, dk.total) >= 90 ? "bad" : "")
        + gauge(pct(dk.used, dk.total), pct(dk.used, dk.total) >= 90 ? "bad" : pct(dk.used, dk.total) >= 80 ? "warn" : "ok")
        + row("Libre", bytes(dk.free))
      : `<p class="h-note">Indisponible.</p>`));

    // Fonctionnement
    const up = d.uptime || {};
    cards.push(card("Fonctionnement", row("Boîtier allumé depuis", duration(up.system_s))
      + row("Application démarrée depuis", duration(up.app_s))));

    // Diffusion
    const p = d.published;
    cards.push(card("Diffusion", row("Écrans connectés", d.displays ?? "—", d.displays > 0 ? "ok" : "muted")
      + (p ? row("Dernière publication", when(p.updated_at)) + row("Contenu publié", `${p.groups} groupes · ${p.people} beltpacks`)
           : row("Publication", "jamais publié", "muted"))));

    // Réseau intercom
    const a = d.antenna;
    cards.push(card("Réseau intercom", a
      ? row("État", a.connected ? "Connecté" : "Hors ligne", a.connected ? "ok" : "warn") + row("Adresse", a.ip || "—")
      : row("État", "Aucun réseau intercom configuré", "muted")));

    const host = document.getElementById("health-cards");
    host.innerHTML = cards.join("");
    // Largeur des jauges en CSSOM (la CSP interdit style="" en attribut).
    host.querySelectorAll(".h-gauge-fill[data-pct]").forEach((f) => { f.style.width = f.dataset.pct + "%"; });
  }

  async function refresh() {
    try {
      const d = await fetch("/api/health").then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
      render(d);
      document.getElementById("health-updated").textContent = new Date().toLocaleTimeString("fr-FR");
      document.getElementById("status-info").textContent = "boîtier surveillé en direct";
    } catch {
      document.getElementById("status-info").textContent = "serveur injoignable — nouvelle tentative dans 4 s";
    }
  }

  setInterval(() => { if (!document.hidden) refresh(); }, 4000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  refresh();
})();
