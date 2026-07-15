/* ComRoster — Affichage TV temps réel (branché sur le SSE /events) */
(() => {
  const AUTO_SCROLL_INITIAL_DELAY = 3500;
  const AUTO_SCROLL_EDGE_PAUSE = 2500;
  const AUTO_SCROLL_SPEED = 40; // px/s
  const AUTO_SCROLL_MIN_DURATION = 8000;

  const grid = document.getElementById("display-grid");
  const bodyEl = document.body;
  const titleEl = document.getElementById("board-title");
  const subtitleEl = document.getElementById("board-subtitle");
  const liveIndicator = document.getElementById("live-indicator");
  const liveLabel = liveIndicator?.querySelector(".status-text");
  const clockEl = document.getElementById("board-clock");
  const syncHint = document.getElementById("sync-hint");
  const scrollContainer = document.getElementById("display-scroll");
  const updatedAtTime = document.getElementById("updated-at-time");
  const totalGroupsEl = document.getElementById("total-groups");
  const totalPeopleEl = document.getElementById("total-people");

  // Données initiales injectées via un bloc <script type="application/json">
  // (non exécuté → compatible CSP stricte sans script inline).
  let INITIAL = null;
  try { INITIAL = JSON.parse(document.getElementById("initial-data")?.textContent || "null"); } catch { /* bloc absent ou invalide */ }

  const state = { data: INITIAL || { groups: [], people: [] } };
  let liveStatusReset = null;
  const scroll = { frameId: null, pauseId: null, direction: 1, active: false, offset: 0 };
  const REDUCED_MOTION = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let eventSource = null;
  let reconnectTimer = null;

  const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
  const resolveTheme = (v) => (v === "day" ? "day" : "night");

  function setLive(mode) {
    if (!liveIndicator || !liveLabel) return;
    if (liveStatusReset) { clearTimeout(liveStatusReset); liveStatusReset = null; }
    const labels = { idle: "En direct", updated: "Mise à jour", error: "Reconnexion…", syncing: "Synchronisation…" };
    liveIndicator.dataset.state = mode;
    liveLabel.textContent = labels[mode] || labels.idle;
    if (mode === "updated") {
      liveStatusReset = setTimeout(() => setLive("idle"), 2500);
    }
  }

  function beltpackNumber(value) {
    if (value == null) return "";
    const m = String(value).match(/\d+/);
    return m ? m[0] : String(value);
  }

  function createPersonCard(person) {
    const el = document.createElement("article");
    el.className = "person";

    const badge = document.createElement("div");
    badge.className = "bp-badge";
    badge.innerHTML = `<span class="bp-l">BP</span><span class="bp-n">${esc(beltpackNumber(person.beltpack))}</span>`;
    const num = beltpackNumber(person.beltpack);
    const dot = document.createElement("span");
    dot.className = "bp-dot";
    dot.dataset.bp = num;
    badge.append(dot);

    const body = document.createElement("div");
    body.className = "person-body";
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = person.role || "—";
    body.append(role);

    const live = document.createElement("div");
    live.className = "card-live";
    const batt = document.createElement("span"); batt.className = "bp-batt"; batt.dataset.bp = num; batt.hidden = true;
    live.append(batt);

    el.append(badge, body, live);
    return el;
  }

  function render(data) {
    stopAutoScroll();
    bodyEl.dataset.theme = resolveTheme(data.theme);
    // Mode performance : désactive le flou GPU (voir display.css [data-perf="on"])
    bodyEl.dataset.perf = data.perf ? "on" : "off";
    // Nombre de colonnes de groupes (0 = automatique selon la largeur d'écran)
    if (grid) grid.style.gridTemplateColumns = data.columns > 0 ? `repeat(${data.columns}, minmax(0, 1fr))` : "";

    if (titleEl) titleEl.textContent = data.title || "Affectation Intercom";
    if (subtitleEl) {
      if (data.subtitle) { subtitleEl.textContent = data.subtitle; subtitleEl.hidden = false; }
      else subtitleEl.hidden = true;
    }
    if (updatedAtTime && data.updated_at) {
      try { updatedAtTime.textContent = new Date(data.updated_at).toLocaleString("fr-FR"); }
      catch { updatedAtTime.textContent = data.updated_at; }
    }

    const groups = [...(data.groups || [])].sort((a, b) => (a.order || 0) - (b.order || 0));
    const people = data.people || [];
    if (totalGroupsEl) totalGroupsEl.textContent = groups.length;
    if (totalPeopleEl) totalPeopleEl.textContent = people.length;

    grid.innerHTML = "";
    groups.forEach((group) => {
      const members = people.filter((p) => p.group_id === group.id);
      const blockEl = document.createElement("section");
      blockEl.className = "block";
      blockEl.style.setProperty("--block-accent", group.color || "var(--primary)");

      const header = document.createElement("div");
      header.className = "block-header";
      const heading = document.createElement("h3");
      heading.textContent = group.name;
      const badge = document.createElement("span");
      badge.className = "badge";
      // Libellé complet par défaut ; fitDisplayText() ne garde que le nombre QUE si le
      // libellé mange trop l'en-tête (colonnes étroites). Les deux formes sont mémorisées.
      const fullLabel = `${members.length} ${members.length > 1 ? "affectations" : "affectation"}`;
      badge.dataset.full = fullLabel;
      badge.dataset.count = members.length;
      badge.textContent = fullLabel;
      badge.title = fullLabel;
      header.append(heading, badge);

      const list = document.createElement("div");
      list.className = "block-items";
      if (members.length) members.forEach((p) => list.append(createPersonCard(p)));
      else {
        const hint = document.createElement("div");
        hint.className = "empty-hint";
        hint.textContent = "Aucune affectation";
        list.append(hint);
      }
      blockEl.append(header, list);
      grid.append(blockEl);
    });

    applyLiveIndicators();
    fitDisplayText();
    startAutoScroll();
  }

  /* ---------- Ajustement homogène du texte (une taille commune, une seule ligne) ----------
     On cherche la PLUS GRANDE taille de police (bornée) où le plus long titre — puis le plus
     long nom — tient encore sur une seule ligne, et on l'applique à TOUS les blocs. Résultat :
     texte homogène, en-têtes alignés, jamais tronqué, et qui grandit quand les cases s'agrandissent
     (moins de groupes / colonnes plus larges → titres plus gros). */
  function fitUniformFontSize(els, minPx, maxPx) {
    if (!els.length) return { size: maxPx, fits: true };
    let lo = minPx, hi = maxPx, best = minPx, bestFits = false;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      els.forEach((e) => { e.style.fontSize = mid + "px"; });
      // « tient sur une ligne » = le texte ne déborde pas de la largeur allouée
      const fits = els.every((e) => e.scrollWidth <= e.clientWidth);
      if (fits) { best = mid; bestFits = true; lo = mid + 1; } else { hi = mid - 1; }
    }
    els.forEach((e) => { e.style.fontSize = ""; });   // la valeur finale vient de la CSS var
    return { size: best, fits: bestFits };            // fits=false → même le plancher déborde
  }

  // Badge d'affectations : libellé complet, ou nombre seul si l'un d'eux prend plus de 40 %
  // de son en-tête (colonne trop étroite → on rend la place au titre).
  function setBadgeLabels(badges) {
    badges.forEach((b) => { b.textContent = b.dataset.full; });
    const cramped = badges.some((b) => b.offsetWidth > b.parentElement.clientWidth * 0.4);
    if (cramped) badges.forEach((b) => { b.textContent = b.dataset.count; });
  }

  function fitDisplayText() {
    if (!grid) return;
    // On mesure toujours en mode « une ligne » : on retire un éventuel repli wrap précédent.
    grid.classList.remove("wrap-titles", "wrap-roles");
    setBadgeLabels([...grid.querySelectorAll(".block-header .badge")]);
    const titles = [...grid.querySelectorAll(".block-header h3")];
    const roles = [...grid.querySelectorAll(".person .role")];
    const t = fitUniformFontSize(titles, 13, 24);
    const r = fitUniformFontSize(roles, 12, 19);
    grid.style.setProperty("--title-fs", t.size + "px");
    grid.style.setProperty("--role-fs", r.size + "px");
    grid.style.setProperty("--bpn-fs", Math.round(Math.min(Math.max(r.size * 1.3, 16), 22)) + "px");
    // Repli anti-troncature : si même au plancher lisible un texte ne tient pas sur une ligne
    // (nom très long en colonne étroite), on autorise le retour à la ligne — jamais coupé.
    grid.classList.toggle("wrap-titles", !t.fits);
    grid.classList.toggle("wrap-roles", !r.fits);
  }

  /* ---------- État temps réel des beltpacks (statut connecté / batterie) ---------- */
  const DEFAULT_IND = { online: true, battery: true };
  let liveBeltpacks = null;   // null = antenne déconnectée → aucun indicateur
  function applyLiveIndicators() {
    const ind = (state.data && state.data.indicators) || DEFAULT_IND;
    grid.querySelectorAll(".bp-dot[data-bp]").forEach((d) => {
      const on = liveBeltpacks?.[d.dataset.bp]?.online;
      if (!ind.online || on === undefined) { d.className = "bp-dot"; d.title = ""; }
      else { d.className = "bp-dot " + (on ? "on" : "down"); d.title = on ? "En ligne" : "Hors ligne"; }
    });
    grid.querySelectorAll(".bp-batt[data-bp]").forEach((b) => {
      const info = liveBeltpacks?.[b.dataset.bp];
      const pct = info?.online ? info.battery : null;
      if (!ind.battery || pct == null) { b.hidden = true; b.textContent = ""; }
      else { b.hidden = false; b.textContent = (info.charging ? "⚡" : "") + pct + "%"; b.className = "bp-batt" + (pct <= 20 ? " low" : ""); }
    });
  }
  function applyLive(res) {
    const hadBattery = liveBeltpacks != null;
    liveBeltpacks = res && res.connected ? res.beltpacks : null;
    applyLiveIndicators();
    // L'apparition/disparition de la batterie change la place dispo pour les noms → réajuste.
    if ((liveBeltpacks != null) !== hadBattery) fitDisplayText();
  }
  // Récupération initiale (au chargement) ; les mises à jour arrivent ensuite
  // en push via le SSE `live` — plus aucune requête périodique.
  async function pollLive() {
    try { applyLive(await fetch("/api/live").then((r) => r.json())); } catch { /* ignore */ }
  }

  /* ---------- Auto-scroll fluide (transform GPU) avec pauses en haut/bas ---------- */
  function setOffset(y) {
    scroll.offset = y;
    grid.style.transform = `translate3d(0, ${-y}px, 0)`;
  }
  function maxOffset() {
    return Math.max(scrollContainer.scrollHeight - scrollContainer.clientHeight, 0);
  }

  function stopAutoScroll() {
    scroll.active = false;
    if (scroll.frameId !== null) { cancelAnimationFrame(scroll.frameId); scroll.frameId = null; }
    if (scroll.pauseId !== null) { clearTimeout(scroll.pauseId); scroll.pauseId = null; }
  }

  function animateScrollTo(target, onComplete) {
    if (!scrollContainer || !scroll.active) return;
    const clamped = Math.min(Math.max(target, 0), maxOffset());
    const start = scroll.offset;
    const distance = clamped - start;
    if (Math.abs(distance) < 1) { setOffset(clamped); onComplete?.(); return; }
    const duration = Math.max((Math.abs(distance) / AUTO_SCROLL_SPEED) * 1000, AUTO_SCROLL_MIN_DURATION);
    const startTime = performance.now();
    const step = (now) => {
      if (!scroll.active) return;
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      setOffset(start + distance * eased);
      if (progress < 1) scroll.frameId = requestAnimationFrame(step);
      else { scroll.frameId = null; onComplete?.(); }
    };
    scroll.frameId = requestAnimationFrame(step);
  }

  function runPhase() {
    if (!scrollContainer || !scroll.active) return;
    const max = maxOffset();
    if (max <= 0) { stopAutoScroll(); setOffset(0); return; }
    const target = scroll.direction > 0 ? max : 0;
    animateScrollTo(target, () => {
      if (!scroll.active) return;
      scroll.direction *= -1;
      scroll.pauseId = setTimeout(runPhase, AUTO_SCROLL_EDGE_PAUSE);
    });
  }

  function startAutoScroll() {
    stopAutoScroll();
    setOffset(0);
    if (!scrollContainer || document.hidden || REDUCED_MOTION) return;
    if (maxOffset() <= 0) return;
    scroll.direction = 1;
    scroll.active = true;
    scroll.pauseId = setTimeout(runPhase, AUTO_SCROLL_INITIAL_DELAY);
  }

  /* ---------- Horloge ---------- */
  function updateClock() {
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("fr-FR");
  }

  /* ---------- Anti-veille écran (Screen Wake Lock) ----------
     Empêche l'écran de s'éteindre. Nécessite un contexte sécurisé (HTTPS ou localhost) :
     sur le Pi en kiosk servi en 127.0.0.1, ça fonctionne. La désactivation du blanking
     côté OS (voir deploy/kiosk.md) reste le filet de sécurité. */
  let wakeLock = null;
  async function requestWakeLock() {
    if (!("wakeLock" in navigator)) return;
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => { wakeLock = null; });
    } catch { /* refusé (contexte non sécurisé / onglet masqué) — la config OS prend le relais */ }
  }

  /* ---------- SSE ---------- */
  function apply(eventData) {
    try {
      const json = JSON.parse(eventData);
      state.data = json;
      render(json);
      setLive("updated");
    } catch (err) {
      console.error("SSE parse", err);
      setLive("error");
    }
  }

  function subscribe() {
    if (!window.EventSource) { if (syncHint) syncHint.textContent = "Temps réel indisponible"; return; }
    if (eventSource) eventSource.close();
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (syncHint) syncHint.textContent = "Connexion en cours…";

    eventSource = new EventSource("/events");
    eventSource.addEventListener("snapshot", (e) => { apply(e.data); setLive("idle"); });
    eventSource.addEventListener("published", (e) => apply(e.data));
    eventSource.addEventListener("live", (e) => { try { applyLive(JSON.parse(e.data)); } catch { /* ignore */ } });
    eventSource.onopen = () => { setLive("idle"); if (syncHint) syncHint.textContent = "Mises à jour en direct actives"; };
    eventSource.onerror = () => {
      setLive("error");
      if (syncHint) syncHint.textContent = "Tentative de reconnexion…";
      if (eventSource) { eventSource.close(); eventSource = null; }
      if (!reconnectTimer) reconnectTimer = setTimeout(() => { reconnectTimer = null; subscribe(); }, 4000);
    };
  }

  /* ---------- Onboarding (box neuve : guide + QR à l'écran) ---------- */
  const shortUrl = (u) => (u || "").replace(/^https?:\/\//, "").replace(/\/admin$/, "");
  let onboardingTimer = null;
  async function loadOnboarding() {
    let ob;
    try { ob = await fetch("/api/onboarding").then((r) => r.json()); } catch { return; }
    const overlay = document.getElementById("onboarding");
    const hint = document.getElementById("admin-hint");
    if (!ob.configured) {
      document.getElementById("ob-url").textContent = shortUrl(ob.hostname_url);
      document.getElementById("ob-ip").textContent = shortUrl(ob.admin_url);
      const img = document.getElementById("ob-qr-img");
      if (!img.getAttribute("src")) img.src = "/display/qr.svg";
      overlay.hidden = false;
      if (hint) hint.hidden = true;
    } else {
      overlay.hidden = true;
      if (hint) { hint.textContent = "⚙ Admin : " + shortUrl(ob.hostname_url); hint.hidden = false; }
      // Box configurée : plus besoin de sonder (le tableau arrive par le SSE).
      if (onboardingTimer) { clearInterval(onboardingTimer); onboardingTimer = null; }
    }
  }

  /* ---------- Init ---------- */
  render(state.data);
  // Les polices web (Inter/Outfit) chargent après le 1er rendu : on réajuste dès qu'elles
  // sont prêtes, sinon la mesure se ferait sur une police de repli (tailles faussées).
  document.fonts?.ready?.then(() => { fitDisplayText(); startAutoScroll(); });
  setLive("idle");
  updateClock();
  setInterval(updateClock, 1000);
  subscribe();
  pollLive();                 // état initial ; les MAJ arrivent en push via le SSE `live`
  loadOnboarding();
  onboardingTimer = setInterval(loadOnboarding, 8000);
  requestWakeLock();

  if (scrollContainer) {
    scrollContainer.addEventListener("wheel", (e) => e.cancelable && e.preventDefault(), { passive: false });
    scrollContainer.addEventListener("touchmove", (e) => e.cancelable && e.preventDefault(), { passive: false });
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { startAutoScroll(); requestWakeLock(); }
    else stopAutoScroll();
  });
  window.addEventListener("resize", () => { fitDisplayText(); startAutoScroll(); });
  window.addEventListener("beforeunload", () => { if (eventSource) eventSource.close(); });
})();
