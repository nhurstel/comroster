/* ComRoster — Administration (édition du brouillon, branché sur l'API REST) */
(() => {
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const DEFAULT_COLOR = "#3AAFA9";
  const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

  const state = {
    data: window.__INITIAL__ || { title: "", subtitle: "", theme: "night", groups: [], people: [], beltpack_roles: {} },
    drag: null,
    context: null,
    busy: false,
    unpublished: false,
    editingPersonId: null,
    selectionMode: false,
    selection: new Set(),
  };

  const el = {
    available: document.getElementById("available-users"),
    availableCount: document.getElementById("available-count"),
    blocks: document.getElementById("blocks-container"),
    blockCount: document.getElementById("block-count"),
    title: document.getElementById("board-title"),
    subtitle: document.getElementById("board-subtitle"),
    syncStatus: document.getElementById("sync-status"),
    syncLabel: document.getElementById("sync-label"),
    dirty: document.getElementById("dirty-indicator"),
    lastUpdated: document.getElementById("last-updated"),
    publishBtn: document.getElementById("publish-btn"),
    themeBtn: document.getElementById("toggle-theme-btn"),
    colorPicker: document.getElementById("block-color-picker"),
    contextMenu: document.getElementById("context-menu"),
    blockDialog: document.getElementById("block-dialog"),
    blockForm: document.getElementById("block-form"),
    blockName: document.getElementById("block-name"),
    metaDialog: document.getElementById("meta-dialog"),
    metaForm: document.getElementById("meta-form"),
    metaTitle: document.getElementById("meta-title"),
    metaSubtitle: document.getElementById("meta-subtitle"),
    personDialog: document.getElementById("person-dialog"),
    personForm: document.getElementById("person-form"),
    personTitle: document.getElementById("person-dialog-title"),
    personRole: document.getElementById("person-role"),
    personBeltpack: document.getElementById("person-beltpack"),
    personAssign: document.getElementById("person-assign"),
    importInput: document.getElementById("import-input"),
  };

  /* ---------- Utilitaires ---------- */
  const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
  const uid = () => "x" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  const normBp = (v) => String(v ?? "").trim();
  const sanitizeColor = (v) => (v && HEX.test(String(v).trim()) ? String(v).trim().toUpperCase() : "");

  function setStatus(label, mode) {
    if (el.syncStatus) el.syncStatus.dataset.state = mode || "idle";
    if (el.syncLabel) el.syncLabel.textContent = label;
  }

  function setUnpublished(v) {
    state.unpublished = v;
    el.dirty.textContent = v ? "Modifications non publiées" : "";
  }

  function findBlock(id) { return state.data.groups.find((g) => g.id === id); }
  function findPerson(id) { return state.data.people.find((p) => p.id === id); }
  function beltpackTaken(num, ignoreId) {
    const n = normBp(num);
    return state.data.people.some((p) => p.id !== ignoreId && normBp(p.beltpack) === n);
  }

  /* ---------- Communication serveur ---------- */
  async function apiSend(method, url, body) {
    const opts = { method, headers: { "X-CSRFToken": CSRF } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const resp = await fetch(url, opts);
    const data = resp.headers.get("content-type")?.includes("json") ? await resp.json() : null;
    if (!resp.ok) { const e = new Error(data?.code || resp.status); e.payload = data; throw e; }
    return data;
  }

  let saveTimer = null;
  let savePending = false;
  function scheduleSave() {
    savePending = true;
    if (saveTimer) clearTimeout(saveTimer);
    setStatus("Enregistrement…", "syncing");
    saveTimer = setTimeout(saveDraft, 500);
  }

  async function saveDraft() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    savePending = false;
    try {
      const saved = await apiSend("PUT", "/api/draft", state.data);
      state.data = saved;
      setStatus("Brouillon enregistré", "idle");
      if (el.lastUpdated) el.lastUpdated.textContent =
        "Dernier enregistrement : " + new Date(saved.updated_at).toLocaleString("fr-FR");
      render();
    } catch (err) {
      setStatus("Échec de l'enregistrement", "error");
      if (err.message === "beltpack_conflict") {
        alert("Deux beltpacks ont le même numéro. Corrigez avant d'enregistrer.");
      }
    }
  }

  function markDirty() { setUnpublished(true); scheduleSave(); }

  // Recharge l'état du brouillon depuis le serveur et ré-affiche.
  async function load() {
    state.data = await apiSend("GET", "/api/state");
    render();
  }

  /* ---------- Rendu ---------- */
  function applyTheme() {
    // L'admin reste en thème sombre ; le bouton ne pilote QUE l'écran de diffusion.
    const mode = state.data.theme === "day" ? "day" : "night";
    if (el.themeBtn) el.themeBtn.textContent = mode === "day" ? "Écran : jour" : "Écran : nuit";
  }

  function personCard(person, source, blockId) {
    const card = document.createElement("article");
    card.className = "person";
    card.draggable = true;
    card.dataset.userId = person.id;
    card.dataset.source = source;
    if (blockId) card.dataset.blockId = blockId;

    // Contenu normal (toujours affiché)
    const bp = document.createElement("div");
    bp.className = "bp";
    bp.title = "Beltpack n°" + person.beltpack;
    bp.textContent = person.beltpack;
    const dot = document.createElement("span");
    dot.className = "bp-dot";
    dot.dataset.bp = person.beltpack;
    bp.append(dot);

    const who = document.createElement("div");
    who.className = "who";
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = person.role || "—";
    who.append(role);
    card.append(bp, who);

    // Mode sélection : checkbox + clic pour cocher, pas de drag
    if (state.selectionMode) {
      card.classList.add("selectable");
      card.draggable = false;
      if (state.selection.has(person.id)) card.classList.add("selected");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "sel-check";
      chk.checked = state.selection.has(person.id);
      chk.tabIndex = -1;
      card.prepend(chk);
      card.addEventListener("click", (e) => {
        e.preventDefault();
        if (state.selection.has(person.id)) state.selection.delete(person.id);
        else state.selection.add(person.id);
        chk.checked = state.selection.has(person.id);
        card.classList.toggle("selected", state.selection.has(person.id));
        updateSelectionBar();
      });
      return card;
    }

    card.addEventListener("dragstart", (e) => {
      card.classList.add("dragging");
      state.drag = { userId: person.id, source, blockId: blockId || null };
      if (e.dataTransfer) { e.dataTransfer.setData("text/plain", person.id); e.dataTransfer.effectAllowed = "move"; }
    });
    card.addEventListener("dragend", () => { card.classList.remove("dragging"); state.drag = null; });
    card.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      state.context = { userId: person.id, blockId: blockId || null };
      el.contextMenu.style.display = "block";
      el.contextMenu.style.left = e.pageX + "px";
      el.contextMenu.style.top = e.pageY + "px";
    });
    card.addEventListener("dblclick", () => openPersonDialog(person.id));
    return card;
  }

  function renderAvailable() {
    el.available.innerHTML = "";
    const avail = state.data.people.filter((p) => !p.group_id);
    el.availableCount.textContent = `${avail.length} beltpack${avail.length > 1 ? "s" : ""}`;
    if (!avail.length) {
      const h = document.createElement("div");
      h.className = "empty-hint";
      h.textContent = "Tous les beltpacks sont affectés";
      el.available.append(h);
      return;
    }
    avail.forEach((p) => el.available.append(personCard(p, "available", null)));
  }

  function renderBlocks() {
    el.blocks.innerHTML = "";
    const groups = [...state.data.groups].sort((a, b) => (a.order || 0) - (b.order || 0));
    el.blockCount.textContent = `${groups.length} groupe${groups.length > 1 ? "s" : ""}`;
    groups.forEach((block) => {
      const members = state.data.people.filter((p) => p.group_id === block.id);
      const wrap = document.createElement("section");
      wrap.className = "admin-block";
      wrap.dataset.blockId = block.id;
      wrap.style.setProperty("--block-accent", sanitizeColor(block.color) || "var(--primary)");

      const header = document.createElement("div");
      header.className = "block-header";
      const titleWrap = document.createElement("div");
      titleWrap.className = "block-title";
      const swatch = document.createElement("span");
      swatch.className = "color-swatch";
      swatch.style.setProperty("--swatch-color", sanitizeColor(block.color) || "transparent");
      const h3 = document.createElement("h3");
      h3.textContent = block.name;
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `${members.length} affectation${members.length > 1 ? "s" : ""}`;
      titleWrap.append(swatch, h3, badge);

      const actions = document.createElement("div");
      actions.className = "block-actions";
      actions.append(
        chip("+ Beltpack", () => openPersonDialog(null, block.id)),
        chip("Renommer", () => renameBlock(block.id)),
        colorChip(block),
        chip("Supprimer", () => deleteBlock(block.id), "danger"),
      );
      header.append(titleWrap, actions);

      const list = document.createElement("div");
      list.className = "block-items";
      list.dataset.blockId = block.id;
      list.addEventListener("dragover", (e) => { e.preventDefault(); list.dataset.dragover = "true"; if (e.dataTransfer) e.dataTransfer.dropEffect = "move"; });
      list.addEventListener("dragleave", () => { delete list.dataset.dragover; });
      list.addEventListener("drop", (e) => { e.preventDefault(); delete list.dataset.dragover; if (state.drag) assign(state.drag.userId, block.id); });

      if (members.length) members.forEach((p) => list.append(personCard(p, "block", block.id)));
      else {
        const h = document.createElement("div");
        h.className = "empty-hint";
        h.textContent = "Déposez des beltpacks ici";
        list.append(h);
      }
      wrap.append(header, list);
      el.blocks.append(wrap);
    });
  }

  function chip(label, onClick, extra) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn" + (extra ? " " + extra : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }
  function colorChip(block) {
    const b = chip("Couleur", () => openColorPicker(block.id), "color-chip");
    b.style.setProperty("--chip-color", sanitizeColor(block.color) || DEFAULT_COLOR);
    return b;
  }

  function refreshAssignOptions() {
    if (!el.personAssign) return;
    const current = el.personAssign.value;
    el.personAssign.innerHTML = '<option value="">Conserver dans la liste disponible</option>';
    state.data.groups.forEach((g) => {
      const o = document.createElement("option");
      o.value = g.id; o.textContent = g.name;
      el.personAssign.append(o);
    });
    if ([...el.personAssign.options].some((o) => o.value === current)) el.personAssign.value = current;
  }

  function render() {
    document.title = "Administration · " + (state.data.title || "ComRoster");
    if (el.title) el.title.textContent = state.data.title || "Affectation Intercom";
    if (el.subtitle) {
      if (state.data.subtitle) { el.subtitle.textContent = state.data.subtitle; el.subtitle.hidden = false; }
      else el.subtitle.hidden = true;
    }
    applyTheme();
    renderAvailable();
    renderBlocks();
    refreshAssignOptions();
    applyLiveDots();
  }

  /* ---------- État temps réel des beltpacks (en ligne / hors ligne) ---------- */
  let liveOnline = null;   // null = antenne non connectée → pas de pastille
  function applyLiveDots() {
    document.querySelectorAll(".bp-dot[data-bp]").forEach((d) => {
      const on = liveOnline ? liveOnline[d.dataset.bp] : undefined;
      if (on === undefined) { d.className = "bp-dot"; d.title = ""; }
      else { d.className = "bp-dot " + (on ? "on" : "down"); d.title = on ? "En ligne" : "Hors ligne"; }
    });
  }
  async function pollLive() {
    let res;
    try { res = await apiSend("GET", "/api/antenna/live"); } catch { return; }
    liveOnline = res.connected ? res.online : null;
    applyLiveDots();
  }

  /* ---------- Mutations ---------- */
  function assign(personId, groupId) {
    const p = findPerson(personId);
    if (!p || p.group_id === groupId) { if (p && p.group_id === groupId) return; }
    if (p) { p.group_id = groupId; markDirty(); render(); }
  }
  function removeFromGroup(personId) {
    const p = findPerson(personId);
    if (p && p.group_id) { p.group_id = null; markDirty(); render(); }
  }
  function deletePerson(personId) {
    state.data.people = state.data.people.filter((p) => p.id !== personId);
    markDirty(); render();
  }
  function createBlock(name) {
    state.data.groups.push({ id: uid(), name, color: "", order: state.data.groups.length });
    markDirty(); render();
  }
  function renameBlock(id) {
    const b = findBlock(id);
    const next = prompt("Nouveau nom du groupe", b.name);
    if (!next) return;
    b.name = next.trim() || b.name;
    markDirty(); render();
  }
  function deleteBlock(id) {
    const b = findBlock(id);
    if (!confirm(`Supprimer le groupe « ${b.name} » ? Les beltpacks retournent dans la liste disponible.`)) return;
    state.data.people.forEach((p) => { if (p.group_id === id) p.group_id = null; });
    state.data.groups = state.data.groups.filter((g) => g.id !== id);
    markDirty(); render();
  }

  /* ---------- Color picker ---------- */
  function openColorPicker(blockId) {
    const b = findBlock(blockId);
    if (!b) return;
    el.colorPicker.value = sanitizeColor(b.color) || DEFAULT_COLOR;
    el.colorPicker.dataset.blockId = blockId;
    if (typeof el.colorPicker.showPicker === "function") el.colorPicker.showPicker();
    else el.colorPicker.click();
  }
  function onColorPick(e) {
    const b = findBlock(e.target.dataset.blockId);
    if (!b) return;
    const next = sanitizeColor(e.target.value);
    if (b.color === next) return;
    b.color = next; markDirty(); render();
  }

  /* ---------- Dialog personne (création + édition) ---------- */
  function openPersonDialog(personId, defaultBlockId) {
    state.editingPersonId = personId || null;
    refreshAssignOptions();
    el.personForm.reset();
    if (personId) {
      const p = findPerson(personId);
      el.personTitle.textContent = "Modifier le beltpack";
      el.personBeltpack.value = p.beltpack;
      el.personRole.value = p.role || "";
      el.personAssign.value = p.group_id || "";
    } else {
      el.personTitle.textContent = "Ajouter un beltpack";
      el.personAssign.value = defaultBlockId || "";
    }
    el.personDialog.showModal();
    requestAnimationFrame(() => el.personBeltpack.focus());
  }

  // Le nom suit le beltpack : proposer le nom déjà connu pour ce numéro
  el.personBeltpack.addEventListener("input", () => {
    const known = state.data.beltpack_roles?.[normBp(el.personBeltpack.value)];
    if (known && !el.personRole.value) el.personRole.value = known;
  });

  function submitPerson(e) {
    e.preventDefault();
    const beltpack = normBp(el.personBeltpack.value);
    if (!beltpack) { el.personBeltpack.focus(); return; }
    if (beltpackTaken(beltpack, state.editingPersonId)) {
      alert(`Le beltpack n°${beltpack} est déjà utilisé.`);
      el.personBeltpack.focus();
      return;
    }
    const role = el.personRole.value.trim();
    const groupId = el.personAssign.value || null;

    if (state.editingPersonId) {
      const p = findPerson(state.editingPersonId);
      Object.assign(p, { beltpack, role, group_id: groupId });
    } else {
      state.data.people.push({ id: uid(), role, beltpack, group_id: groupId });
    }
    el.personDialog.close();
    markDirty(); render();
  }

  /* ---------- Dialog meta ---------- */
  function openMetaDialog() {
    el.metaTitle.value = state.data.title || "";
    el.metaSubtitle.value = state.data.subtitle || "";
    el.metaDialog.showModal();
    requestAnimationFrame(() => el.metaTitle.select());
  }
  function submitMeta(e) {
    e.preventDefault();
    const t = el.metaTitle.value.trim();
    if (!t) { el.metaTitle.focus(); return; }
    state.data.title = t;
    state.data.subtitle = el.metaSubtitle.value.trim();
    el.metaDialog.close();
    markDirty(); render();
  }

  /* ---------- Publication ---------- */
  async function publish() {
    if (state.busy) return;
    state.busy = true;
    el.publishBtn.disabled = true;
    try {
      if (savePending || saveTimer) await saveDraft();
      await apiSend("POST", "/api/publish");
      setUnpublished(false);
      setStatus("Publié vers l'affichage ✓", "updated");
      setTimeout(() => setStatus("Brouillon synchronisé", "idle"), 2500);
    } catch (err) {
      if (err.message === "beltpack_conflict") alert("Beltpack en double : impossible de publier.");
      else alert("Échec de la publication.");
      setStatus("Échec de la publication", "error");
    } finally {
      state.busy = false;
      el.publishBtn.disabled = false;
    }
  }

  /* ---------- Export / Import ---------- */
  function exportConfig() {
    const blob = new Blob([JSON.stringify(state.data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `comroster-${Date.now()}.json`;
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
  }
  function importConfig(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const json = JSON.parse(ev.target.result);
        if (!json || typeof json !== "object") throw new Error("invalide");
        state.data = {
          title: json.title || "", subtitle: json.subtitle || "", theme: json.theme || "night",
          groups: json.groups || [], people: json.people || [], beltpack_roles: json.beltpack_roles || {},
        };
        markDirty(); render();
      } catch { alert("Fichier invalide."); }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  /* ---------- Historique des publications ---------- */
  async function openHistory() {
    let items = [];
    try { items = await apiSend("GET", "/api/history"); } catch { alert("Historique indisponible."); return; }
    const list = document.getElementById("history-list");
    list.innerHTML = items.length
      ? items.map((i) => `<li><span>${esc(i.datetime)}</span><button type="button" data-restore="${i.timestamp}">Restaurer</button></li>`).join("")
      : "<li class='empty-hint'>Aucune publication enregistrée.</li>";
    list.querySelectorAll("[data-restore]").forEach((b) => b.addEventListener("click", async () => {
      try {
        state.data = await apiSend("POST", `/api/history/${b.dataset.restore}/restore`);
        setUnpublished(true);
        render();
        document.getElementById("history-dialog").close();
        setStatus("Snapshot restauré dans le brouillon", "updated");
        setTimeout(() => setStatus("Brouillon synchronisé", "idle"), 2500);
      } catch { alert("Restauration impossible."); }
    }));
    document.getElementById("history-dialog").showModal();
  }

  /* ---------- Menu contextuel ---------- */
  function hideContextMenu() { el.contextMenu.style.display = "none"; state.context = null; }
  el.contextMenu.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn || !state.context) return;
    const { userId } = state.context;
    const action = btn.dataset.action;
    if (action === "edit") openPersonDialog(userId);
    else if (action === "remove") removeFromGroup(userId);
    else if (action === "delete") { if (confirm("Supprimer ce beltpack ?")) deletePerson(userId); }
    hideContextMenu();
  });
  document.addEventListener("click", (e) => { if (!el.contextMenu.contains(e.target)) hideContextMenu(); });
  document.addEventListener("scroll", hideContextMenu, true);

  /* ---------- Zone "disponibles" comme drop pour retirer ---------- */
  el.available.addEventListener("dragover", (e) => { e.preventDefault(); el.available.dataset.dragover = "true"; });
  el.available.addEventListener("dragleave", () => { delete el.available.dataset.dragover; });
  el.available.addEventListener("drop", (e) => {
    e.preventDefault();
    delete el.available.dataset.dragover;
    if (state.drag && state.drag.source === "block") removeFromGroup(state.drag.userId);
  });

  /* ---------- Branchements ---------- */
  document.getElementById("add-block-btn").addEventListener("click", () => {
    el.blockForm.reset(); el.blockDialog.showModal();
    requestAnimationFrame(() => el.blockName.focus());
  });
  el.blockForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = el.blockName.value.trim();
    if (!v) return;
    el.blockDialog.close(); createBlock(v);
  });
  document.getElementById("add-user-btn").addEventListener("click", () => openPersonDialog(null, null));
  el.personForm.addEventListener("submit", submitPerson);
  el.metaForm.addEventListener("submit", submitMeta);
  document.getElementById("edit-meta-btn").addEventListener("click", openMetaDialog);
  el.themeBtn.addEventListener("click", () => {
    state.data.theme = state.data.theme === "day" ? "night" : "day";
    markDirty(); render();
  });
  el.publishBtn.addEventListener("click", publish);
  document.getElementById("export-btn").addEventListener("click", exportConfig);
  el.importInput.addEventListener("change", importConfig);
  document.getElementById("history-btn").addEventListener("click", openHistory);
  document.getElementById("history-close").addEventListener("click", () => document.getElementById("history-dialog").close());
  el.colorPicker.addEventListener("input", onColorPick);
  el.colorPicker.addEventListener("change", onColorPick);
  document.querySelectorAll("button[data-close]").forEach((b) =>
    b.addEventListener("click", () => document.getElementById(b.dataset.close)?.close()));
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); publish(); }
  });

  /* ---------- Antenne : pastille, assistant, tableau de bord ---------- */
  const antennaDialog = document.getElementById("antenna-dialog");
  let currentRanges = [];
  let rangesListEl = null;

  function summaryHtml(p) {
    return [
      `<li><b>${p.new.length}</b> à ajouter${p.new.length ? " : " + p.new.map((n) => esc(`#${n.number} ${n.name}`)).join(", ") : ""}</li>`,
      `<li><b>${p.changed.length}</b> rôle(s) mis à jour${p.changed.length ? " : " + p.changed.map((c) => esc(`#${c.number} ${c.old_role}→${c.new_role}`)).join(", ") : ""}</li>`,
      `<li><b>${p.unchanged}</b> inchangé(s)</li>`,
      `<li><b>${p.missing.length}</b> à retirer${p.missing.length ? " : " + p.missing.map((m) => esc(`#${m.number} ${m.role}`)).join(", ") : ""}</li>`,
    ].join("");
  }

  async function refreshAntennaBadge() {
    const dot = document.getElementById("antenna-dot");
    let st;
    try { st = await apiSend("GET", "/api/antenna/status"); } catch { return; }
    dot.className = "dot " + (st.connected ? "online" : st.ip ? "offline" : "off");
    return st;
  }

  function renderRanges() {
    if (!rangesListEl) return;
    rangesListEl.innerHTML = "";
    currentRanges.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "range-row";
      row.innerHTML = `de <input type="number" min="1" value="${r[0]}" data-i="${i}" data-k="0"> à `
        + `<input type="number" min="1" value="${r[1]}" data-i="${i}" data-k="1">`;
      const del = document.createElement("button");
      del.type = "button"; del.className = "range-del"; del.textContent = "✕";
      del.addEventListener("click", () => { currentRanges.splice(i, 1); renderRanges(); saveRanges(); });
      row.appendChild(del);
      rangesListEl.appendChild(row);
    });
    rangesListEl.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
      currentRanges[+inp.dataset.i][+inp.dataset.k] = parseInt(inp.value || "0", 10);
      saveRanges();
    }));
  }
  async function saveRanges() {
    const clean = currentRanges
      .map((r) => [parseInt(r[0] || 0, 10), parseInt(r[1] || 0, 10)])
      .filter((r) => r[0] >= 1 && r[1] >= r[0]);
    try { await apiSend("PUT", "/api/settings", { antenna_ranges: clean }); }
    catch { toast("Plages invalides", true); }
  }
  function addRange() { currentRanges.push([1, 25]); renderRanges(); saveRanges(); }
  document.getElementById("wiz-add-range").addEventListener("click", addRange);
  document.getElementById("dash-add-range").addEventListener("click", addRange);

  function wizGo(step) {
    antennaDialog.querySelectorAll(".wiz-step").forEach((s) => { s.hidden = +s.dataset.step !== step; });
    antennaDialog.querySelectorAll(".wiz-dot").forEach((d) => {
      const n = +d.dataset.dot;
      d.classList.toggle("active", n === step);
      d.classList.toggle("done", n < step);
    });
    if (step === 2) { rangesListEl = document.getElementById("wiz-ranges-list"); renderRanges(); }
  }

  async function openAntenna() {
    const settings = await apiSend("GET", "/api/settings");
    currentRanges = (settings.antenna_ranges || []).map((r) => [r[0], r[1]]);
    const st = await refreshAntennaBadge();
    if (st && st.ip) {
      document.getElementById("antenna-wizard").hidden = true;
      document.getElementById("antenna-dashboard").hidden = false;
      const online = st.connected;
      const fw = st.info?.firmware?.version || "?";
      const name = st.info?.local?.name || st.ip;
      const nbp = (st.info?.nodes || []).reduce((a, n) => a + (n.bp ? n.bp.length : 0), 0);
      document.getElementById("dash-state").innerHTML =
        `<div class="ds-line"><span class="dot ${online ? "online" : "offline"}"></span>`
        + `<b>${online ? "Connecté" : "Hors ligne"}</b></div>`
        + `<div class="ds-sub">${esc(name)}${online ? ` · firmware ${esc(fw)}` : ""}</div>`
        + (online && nbp ? `<div class="ds-sub">${nbp} beltpack(s) sur le réseau</div>` : "");
      document.getElementById("dash-reconnect-btn").hidden = online;
      document.getElementById("dash-refresh-btn").hidden = !online;
      rangesListEl = document.getElementById("dash-ranges-list"); renderRanges();
    } else {
      document.getElementById("antenna-dashboard").hidden = true;
      document.getElementById("antenna-wizard").hidden = false;
      document.getElementById("wiz-ip").value = "";
      document.getElementById("wiz-password").value = "";
      document.getElementById("wiz-error").hidden = true;
      wizGo(1);
    }
    if (!antennaDialog.open) antennaDialog.showModal();
  }
  document.getElementById("antenna-btn").addEventListener("click", openAntenna);

  document.getElementById("wiz-connect-btn").addEventListener("click", async () => {
    const ip = document.getElementById("wiz-ip").value.trim();
    const password = document.getElementById("wiz-password").value;
    const err = document.getElementById("wiz-error");
    err.hidden = true;
    try {
      await apiSend("POST", "/api/antenna/connect", { ip, password });
      await refreshAntennaBadge();
      await pollLive();
      wizGo(2);
    } catch (e) {
      err.textContent = e.payload?.error || "Connexion échouée";
      err.hidden = false;
    }
  });
  document.getElementById("wiz-back-2").addEventListener("click", () => wizGo(1));
  document.getElementById("wiz-back-3").addEventListener("click", () => wizGo(2));

  document.getElementById("wiz-next-2").addEventListener("click", async () => {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    document.getElementById("wiz-summary").innerHTML = summaryHtml(p);
    wizGo(3);
  });
  document.getElementById("wiz-import-btn").addEventListener("click", async () => {
    try {
      await apiSend("POST", "/api/antenna/import/apply");
      antennaDialog.close();
      setUnpublished(true);
      await load();
      await refreshAntennaBadge();
      await pollLive();
      toast("Beltpacks importés");
    } catch { toast("Import impossible", true); }
  });

  document.getElementById("dash-reconnect-btn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Connexion…";
    try {
      await apiSend("POST", "/api/antenna/reconnect");
      toast("Antenne reconnectée");
      await openAntenna();          // ré-affiche le tableau de bord à jour
    } catch (err) {
      toast(err.payload?.error || "Reconnexion échouée", true);
      await refreshAntennaBadge();
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });
  document.getElementById("dash-disconnect-btn").addEventListener("click", async () => {
    try { await apiSend("POST", "/api/antenna/disconnect"); } finally {
      antennaDialog.close();
      await refreshAntennaBadge();
      await pollLive();                 // efface les pastilles immédiatement
    }
  });
  document.getElementById("dash-refresh-btn").addEventListener("click", async () => {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    document.getElementById("import-summary").innerHTML = summaryHtml(p);
    document.getElementById("import-dialog").showModal();
  });

  document.getElementById("import-apply-btn").addEventListener("click", async () => {
    try {
      await apiSend("POST", "/api/antenna/import/apply");
      document.getElementById("import-dialog").close();
      antennaDialog.close();
      setUnpublished(true);
      await load();
      await refreshAntennaBadge();
      await pollLive();
      toast("Beltpacks importés");
    } catch { toast("Import impossible", true); }
  });

  /* ---------- Mode sélection ---------- */
  function updateSelectionBar() {
    document.getElementById("selection-count").textContent = `${state.selection.size} sélectionné(s)`;
    document.getElementById("selection-bar").classList.toggle("active", state.selectionMode);
  }
  function exitSelection() {
    state.selectionMode = false;
    state.selection.clear();
    document.getElementById("select-btn").textContent = "Sélectionner";
    updateSelectionBar();
    render();
  }
  document.getElementById("select-btn").addEventListener("click", () => {
    state.selectionMode = !state.selectionMode;
    state.selection.clear();
    document.getElementById("select-btn").textContent = state.selectionMode ? "Quitter la sélection" : "Sélectionner";
    updateSelectionBar();
    render();
  });
  document.getElementById("selection-cancel").addEventListener("click", exitSelection);
  document.getElementById("selection-delete").addEventListener("click", async () => {
    if (!state.selection.size) return;
    if (!confirm(`Supprimer ${state.selection.size} beltpack(s) ?`)) return;
    const ids = [...state.selection];
    try {
      const res = await apiSend("POST", "/api/people/delete-batch", { ids });
      exitSelection();
      setUnpublished(true);
      await load();
      toast(`${res.deleted} beltpack(s) supprimé(s)`);
    } catch { toast("Suppression impossible", true); }
  });

  /* ---------- Configurations ---------- */
  async function openConfigs() {
    const items = await apiSend("GET", "/api/configs");
    const ul = document.getElementById("configs-list");
    ul.innerHTML = items.length
      ? items.map((c) => `<li><span>${esc(c.name)}</span><span class="cfg-actions">`
          + `<button type="button" data-load="${esc(c.name)}">Charger</button>`
          + `<button type="button" data-del="${esc(c.name)}" class="chip-btn danger">Supprimer</button></span></li>`).join("")
      : "<li class='empty-hint'>Aucune configuration enregistrée.</li>";
    ul.querySelectorAll("[data-load]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`Charger « ${b.dataset.load} » ? Le tableau actuel sera remplacé et l'antenne déconnectée.`)) return;
      await apiSend("POST", `/api/configs/${encodeURIComponent(b.dataset.load)}/load`);
      document.getElementById("configs-dialog").close();
      setUnpublished(true);
      await load();
      toast("Configuration chargée");
    }));
    ul.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`Supprimer « ${b.dataset.del} » ?`)) return;
      await apiSend("DELETE", `/api/configs/${encodeURIComponent(b.dataset.del)}`);
      openConfigs();
    }));
    document.getElementById("configs-dialog").showModal();
  }
  document.getElementById("configs-btn").addEventListener("click", openConfigs);
  document.getElementById("config-save-btn").addEventListener("click", async () => {
    const name = document.getElementById("config-name").value.trim();
    if (!name) return;
    await apiSend("POST", "/api/configs", { name });
    document.getElementById("config-name").value = "";
    openConfigs();
    toast("Configuration sauvegardée");
  });

  /* ---------- Init ---------- */
  render();
  updateSelectionBar();
  refreshAntennaBadge();
  pollLive();
  setInterval(pollLive, 5000);
  setStatus("Brouillon synchronisé", "idle");
})();
