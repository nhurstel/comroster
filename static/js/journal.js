/* Page Journal : événements applicatifs (persistants) + logs techniques (mémoire).
   Deux volets, un filtre texte commun, un filtre par niveau côté Technique, export
   texte du volet affiché, actualisation automatique (suspendue onglet caché). */
(() => {
  "use strict";

  const EVENT_LABELS = {
    publish: "Publication envoyée",
    import: "Fichier importé",
    restore: "Publication restaurée",
    history_clear: "Publications passées effacées",
    network_save: "Réglages réseau enregistrés",
    network_apply: "Réglages réseau appliqués",
    reboot: "Redémarrage du boîtier",
    antenna_connect: "Antenne connectée",
    antenna_disconnect: "Antenne déconnectée",
    antenna_import: "Import depuis l'antenne",
    config_save: "Configuration sauvegardée",
    config_load: "Configuration chargée",
    config_delete: "Configuration supprimée",
  };
  const LEVEL_LABELS = { DEBUG: "debug", INFO: "info", WARNING: "avert.", ERROR: "erreur", CRITICAL: "critique" };

  const state = {
    tab: "events",
    q: "",
    levels: new Set(["INFO", "WARNING", "ERROR"]),
    events: [],
    logs: [],
  };

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (iso) => {
    try {
      return new Date(iso).toLocaleString("fr-FR",
        { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch { return "—"; }
  };
  // Les niveaux au-dessus d'ERROR suivent le chip « erreurs ».
  const levelKey = (lv) => (lv === "CRITICAL" ? "ERROR" : lv === "DEBUG" ? "INFO" : lv);

  function filteredEvents() {
    const q = state.q.toLowerCase();
    return state.events.filter((e) =>
      !q || (EVENT_LABELS[e.event] || e.event).toLowerCase().includes(q)
         || (e.detail || "").toLowerCase().includes(q));
  }
  function filteredLogs() {
    const q = state.q.toLowerCase();
    return state.logs.filter((l) =>
      state.levels.has(levelKey(l.level))
      && (!q || l.message.toLowerCase().includes(q) || l.logger.toLowerCase().includes(q)));
  }

  function render() {
    const isLogs = state.tab === "logs";
    document.getElementById("events-list").hidden = isLogs;
    document.getElementById("log-list").hidden = !isLogs;
    document.getElementById("level-chips").hidden = !isLogs;
    document.querySelectorAll("[data-jtab]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.jtab === state.tab)));

    if (!isLogs) {
      const rows = filteredEvents();
      document.getElementById("events-list").innerHTML = rows.length
        ? rows.map((e) =>
            `<li><span class="j-time">${esc(when(e.ts))}</span>`
            + `<span class="j-label">${esc(EVENT_LABELS[e.event] || e.event)}</span>`
            + (e.detail ? `<span class="j-detail">${esc(e.detail)}</span>` : "")
            + "</li>").join("")
        : "<li class='journal-empty'>Rien à signaler.</li>";
      document.getElementById("journal-count").textContent =
        `${rows.length} événement${rows.length > 1 ? "s" : ""}`;
    } else {
      const rows = filteredLogs();
      document.getElementById("log-list").innerHTML = rows.length
        ? rows.map((l) =>
            `<div class="log-row" data-level="${esc(l.level)}">`
            + `<span class="log-time">${esc(when(l.ts))}</span>`
            + `<span class="log-level">${esc(LEVEL_LABELS[l.level] || l.level)}</span>`
            + `<span class="log-logger" title="${esc(l.logger)}">${esc(l.logger)}</span>`
            + `<span class="log-msg">${esc(l.message)}</span></div>`).join("")
        : "<div class='journal-empty'>Aucun log ne correspond.</div>";
      document.getElementById("journal-count").textContent =
        `${rows.length} ligne${rows.length > 1 ? "s" : ""} · tampon des ${state.logs.length} dernières`;
    }
  }

  async function refresh() {
    try {
      const [ev, lg] = await Promise.all([
        fetch("/api/journal").then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
        fetch("/api/logs").then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
      ]);
      state.events = ev;
      state.logs = lg;
      document.getElementById("journal-updated").textContent =
        new Date().toLocaleTimeString("fr-FR");
      document.getElementById("status-info").textContent =
        `${state.events.length} événements · ${state.logs.length} logs en tampon`;
      render();
    } catch {
      document.getElementById("status-info").textContent =
        "serveur injoignable — nouvelle tentative dans 5 s";
    }
  }

  function download() {
    const lines = state.tab === "logs"
      ? filteredLogs().map((l) => `${l.ts}\t${l.level}\t${l.logger}\t${l.message}`)
      : filteredEvents().map((e) => `${e.ts}\t${EVENT_LABELS[e.event] || e.event}\t${e.detail || ""}`);
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `comroster-journal-${state.tab}-${new Date().toISOString().slice(0, 19).replaceAll(":", "")}.log`;
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
  }

  document.querySelectorAll("[data-jtab]").forEach((b) =>
    b.addEventListener("click", () => { state.tab = b.dataset.jtab; render(); }));
  document.querySelectorAll("#level-chips [data-level]").forEach((b) =>
    b.addEventListener("click", () => {
      const lv = b.dataset.level;
      if (state.levels.has(lv)) state.levels.delete(lv);
      else state.levels.add(lv);
      b.setAttribute("aria-pressed", String(state.levels.has(lv)));
      render();
    }));
  const filter = document.getElementById("journal-filter");
  filter.addEventListener("input", () => { state.q = filter.value.trim(); render(); });
  document.getElementById("refresh-btn").addEventListener("click", refresh);
  document.getElementById("download-btn").addEventListener("click", download);

  // Auto-actualisation, suspendue quand l'onglet n'est pas visible (rien à repeindre,
  // et pas de requêtes en tâche de fond depuis un poste de régie).
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  refresh();
})();
