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
    personName: document.getElementById("person-name"),
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
        alert("Deux personnes ont le même numéro de beltpack. Corrigez avant d'enregistrer.");
      }
    }
  }

  function markDirty() { setUnpublished(true); scheduleSave(); }

  /* ---------- Rendu ---------- */
  function applyTheme() {
    const mode = state.data.theme === "day" ? "day" : "night";
    document.body.dataset.theme = mode;
    if (el.themeBtn) el.themeBtn.textContent = mode === "day" ? "Passer en mode nuit" : "Passer en mode jour";
  }

  function personCard(person, source, blockId) {
    const card = document.createElement("article");
    card.className = "person";
    card.draggable = true;
    card.dataset.userId = person.id;
    card.dataset.source = source;
    if (blockId) card.dataset.blockId = blockId;

    const badge = document.createElement("div");
    badge.className = "beltpack-tag";
    badge.textContent = "Beltpack n°" + esc(person.beltpack);

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = person.name;
    const meta = document.createElement("div");
    meta.className = "meta";
    const role = document.createElement("span");
    role.textContent = person.role || "—";
    meta.append(role, badge);
    card.append(name, meta);

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
    el.availableCount.textContent = `${avail.length} personne${avail.length > 1 ? "s" : ""}`;
    if (!avail.length) {
      const h = document.createElement("div");
      h.className = "empty-hint";
      h.textContent = "Toutes les personnes sont affectées";
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
        chip("Ajouter", () => openPersonDialog(null, block.id)),
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
        h.textContent = "Déposez des personnes ici";
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
    if (!confirm(`Supprimer le groupe « ${b.name} » ? Les personnes retournent dans la liste disponible.`)) return;
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
      el.personTitle.textContent = "Modifier la personne";
      el.personBeltpack.value = p.beltpack;
      el.personRole.value = p.role || "";
      el.personName.value = p.name;
      el.personAssign.value = p.group_id || "";
    } else {
      el.personTitle.textContent = "Ajouter une personne";
      el.personAssign.value = defaultBlockId || "";
    }
    el.personDialog.showModal();
    requestAnimationFrame(() => el.personBeltpack.focus());
  }

  // Le rôle suit le beltpack : proposer le rôle déjà connu pour ce numéro
  el.personBeltpack.addEventListener("input", () => {
    const known = state.data.beltpack_roles?.[normBp(el.personBeltpack.value)];
    if (known && !el.personRole.value) el.personRole.value = known;
  });

  function submitPerson(e) {
    e.preventDefault();
    const beltpack = normBp(el.personBeltpack.value);
    if (!beltpack) { el.personBeltpack.focus(); return; }
    if (beltpackTaken(beltpack, state.editingPersonId)) {
      alert(`Le beltpack n°${beltpack} est déjà attribué à une autre personne.`);
      el.personBeltpack.focus();
      return;
    }
    const name = el.personName.value.trim();
    if (!name) { el.personName.focus(); return; }
    const role = el.personRole.value.trim();
    const groupId = el.personAssign.value || null;

    if (state.editingPersonId) {
      const p = findPerson(state.editingPersonId);
      Object.assign(p, { beltpack, role, name, group_id: groupId });
    } else {
      state.data.people.push({ id: uid(), name, role, beltpack, group_id: groupId });
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

  /* ---------- Menu contextuel ---------- */
  function hideContextMenu() { el.contextMenu.style.display = "none"; state.context = null; }
  el.contextMenu.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn || !state.context) return;
    const { userId } = state.context;
    const action = btn.dataset.action;
    if (action === "edit") openPersonDialog(userId);
    else if (action === "remove") removeFromGroup(userId);
    else if (action === "delete") { if (confirm("Supprimer cette personne ?")) deletePerson(userId); }
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
  el.colorPicker.addEventListener("input", onColorPick);
  el.colorPicker.addEventListener("change", onColorPick);
  document.querySelectorAll("button[data-close]").forEach((b) =>
    b.addEventListener("click", () => document.getElementById(b.dataset.close)?.close()));
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); publish(); }
  });

  /* ---------- Init ---------- */
  render();
  setStatus("Brouillon synchronisé", "idle");
})();
