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
  const scroll = { frameId: null, pauseId: null, direction: 1, active: false };
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

    const body = document.createElement("div");
    body.className = "person-body";
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = person.role || "—";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = person.name;
    body.append(role, name);

    el.append(badge, body);
    return el;
  }

  function render(data) {
    stopAutoScroll();
    bodyEl.dataset.theme = resolveTheme(data.theme);

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

    startAutoScroll();
  }

  /* ---------- Auto-scroll fluide avec pauses en haut/bas ---------- */
  function stopAutoScroll() {
    scroll.active = false;
    if (scroll.frameId !== null) { cancelAnimationFrame(scroll.frameId); scroll.frameId = null; }
    if (scroll.pauseId !== null) { clearTimeout(scroll.pauseId); scroll.pauseId = null; }
  }

  function animateScrollTo(target, onComplete) {
    if (!scrollContainer || !scroll.active) return;
    const maxScroll = Math.max(scrollContainer.scrollHeight - scrollContainer.clientHeight, 0);
    const clamped = Math.min(Math.max(target, 0), maxScroll);
    const start = scrollContainer.scrollTop;
    const distance = clamped - start;
    if (Math.abs(distance) < 1) { scrollContainer.scrollTop = clamped; onComplete?.(); return; }
    const duration = Math.max((Math.abs(distance) / AUTO_SCROLL_SPEED) * 1000, AUTO_SCROLL_MIN_DURATION);
    const startTime = performance.now();
    const step = (now) => {
      if (!scroll.active) return;
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      scrollContainer.scrollTop = start + distance * eased;
      if (progress < 1) scroll.frameId = requestAnimationFrame(step);
      else { scroll.frameId = null; onComplete?.(); }
    };
    scroll.frameId = requestAnimationFrame(step);
  }

  function runPhase() {
    if (!scrollContainer || !scroll.active) return;
    const maxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;
    if (maxScroll <= 0) { stopAutoScroll(); scrollContainer.scrollTop = 0; return; }
    const target = scroll.direction > 0 ? maxScroll : 0;
    animateScrollTo(target, () => {
      if (!scroll.active) return;
      scroll.direction *= -1;
      scroll.pauseId = setTimeout(runPhase, AUTO_SCROLL_EDGE_PAUSE);
    });
  }

  function startAutoScroll() {
    stopAutoScroll();
    if (!scrollContainer || document.hidden) return;
    scroll.direction = 1;
    scrollContainer.scrollTop = 0;
    if (scrollContainer.scrollHeight - scrollContainer.clientHeight <= 0) return;
    scroll.active = true;
    scroll.pauseId = setTimeout(runPhase, AUTO_SCROLL_INITIAL_DELAY);
  }

  /* ---------- Horloge ---------- */
  function updateClock() {
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("fr-FR");
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

  /* ---------- Init ---------- */
  render(state.data);
  setLive("idle");
  updateClock();
  setInterval(updateClock, 1000);
  subscribe();

  if (scrollContainer) {
    scrollContainer.addEventListener("wheel", (e) => e.cancelable && e.preventDefault(), { passive: false });
    scrollContainer.addEventListener("touchmove", (e) => e.cancelable && e.preventDefault(), { passive: false });
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) startAutoScroll(); else stopAutoScroll(); });
  window.addEventListener("resize", startAutoScroll);
  window.addEventListener("beforeunload", () => { if (eventSource) eventSource.close(); });
})();
