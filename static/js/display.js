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

  const state = { data: window.__INITIAL__ || { groups: [], people: [] } };
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
    badge.innerHTML = `<span class="bp-n">${esc(beltpackNumber(person.beltpack))}</span><span class="bp-l">BP</span>`;
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
    const sig = document.createElement("span"); sig.className = "bp-sig"; sig.dataset.bp = num; sig.hidden = true;
    live.append(batt, sig);

    el.append(badge, body, live);
    return el;
  }

  const TEXT_SCALE = { normal: "", large: "118%", xlarge: "135%" };

  function render(data) {
    stopAutoScroll();
    bodyEl.dataset.theme = resolveTheme(data.theme);
    // Taille du texte de l'écran (les polices sont en rem → la racine les met à l'échelle)
    document.documentElement.style.fontSize = TEXT_SCALE[data.scale] || "";

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
      badge.textContent = `${members.length} ${members.length > 1 ? "affectations" : "affectation"}`;
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
    startAutoScroll();
  }

  /* ---------- État temps réel des beltpacks (statut / batterie / réception) ---------- */
  const DEFAULT_IND = { online: true, battery: true, signal: true };
  let liveBeltpacks = null;   // null = antenne déconnectée → aucun indicateur
  function signalBarsHtml(n) {
    let h = ""; for (let i = 1; i <= 4; i++) h += `<i class="${i <= n ? "on" : ""}"></i>`; return h;
  }
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
    grid.querySelectorAll(".bp-sig[data-bp]").forEach((s) => {
      const info = liveBeltpacks?.[s.dataset.bp];
      const bars = info?.online ? info.signal : null;
      if (!ind.signal || bars == null) { s.hidden = true; s.innerHTML = ""; }
      else { s.hidden = false; s.innerHTML = signalBarsHtml(bars); }
    });
  }
  async function pollLive() {
    let res;
    try { res = await fetch("/api/live").then((r) => r.json()); } catch { return; }
    liveBeltpacks = res.connected ? res.beltpacks : null;
    applyLiveIndicators();
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
  setLive("idle");
  updateClock();
  setInterval(updateClock, 1000);
  subscribe();
  pollLive();
  setInterval(pollLive, 5000);
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
  window.addEventListener("resize", startAutoScroll);
  window.addEventListener("beforeunload", () => { if (eventSource) eventSource.close(); });
})();
