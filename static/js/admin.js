/* ComRoster — Administration (édition du brouillon, branché sur l'API REST) */
(() => {
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const DEFAULT_COLOR = "#3AAFA9";
  const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

  // Données initiales injectées via un bloc <script type="application/json">
  // (non exécuté → compatible CSP stricte sans script inline).
  let INITIAL = null;
  try { INITIAL = JSON.parse(document.getElementById("initial-data")?.textContent || "null"); } catch { /* bloc absent ou invalide */ }

  const state = {
    data: INITIAL || { title: "", subtitle: "", theme: "night", groups: [], people: [], beltpack_roles: {} },
    drag: null,
    dragGroup: null,        // id du groupe en cours de réordonnancement
    context: null,
    busy: false,
    unpublished: false,
    editingPersonId: null,
    selection: new Set(),
    lastSelectedId: null,   // pour la sélection par plage (MAJ+clic)
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
    colorPicker: document.getElementById("block-color-picker"),
    contextMenu: document.getElementById("context-menu"),
    blockDialog: document.getElementById("block-dialog"),
    blockForm: document.getElementById("block-form"),
    blockName: document.getElementById("block-name"),
    personDialog: document.getElementById("person-dialog"),
    personForm: document.getElementById("person-form"),
    personTitle: document.getElementById("person-dialog-title"),
    personRole: document.getElementById("person-role"),
    personBeltpack: document.getElementById("person-beltpack"),
    personAssign: document.getElementById("person-assign"),
    importInput: document.getElementById("import-input"),
  };

  /* ---------- Utilitaires ---------- */
  // Échappe aussi les guillemets : esc() est utilisé en contexte attribut (data-…="…").
  const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;"); };
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

  /* ---------- Notification transitoire (toast) ----------
     NB: cette fonction manquait — chaque appel `toast(...)` levait un ReferenceError.
     Comme les succès l'appellent DANS le try, le catch se déclenchait et affichait un
     faux message d'erreur (historique, réseau, imports, reconnexion antenne…). */
  let toastTimer = null;
  function toast(msg, isError) {
    let t = document.getElementById("cr-toast");
    if (!t) { t = document.createElement("div"); t.id = "cr-toast"; t.className = "cr-toast"; document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.toggle("error", !!isError);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
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
    // Le mode Clair/Sombre ne pilote QUE l'écran de diffusion ; l'admin reste sombre.
    // (Le sélecteur est synchronisé via syncSettingsInputs.)
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

    const live = document.createElement("div");
    live.className = "card-live";
    const batt = document.createElement("span"); batt.className = "bp-batt"; batt.dataset.bp = person.beltpack; batt.hidden = true;
    live.append(batt);
    card.append(bp, who, live);

    // Clic = (dé)sélection (MAJ+clic = plage). Le drag déplace la sélection si l'item
    // en fait partie, sinon juste lui. Double-clic = éditer, clic droit = menu.
    card.classList.add("selectable");
    if (state.selection.has(person.id)) card.classList.add("selected");
    card.addEventListener("click", (e) => {
      if (e.shiftKey && state.lastSelectedId) {
        selectRange(state.lastSelectedId, person.id);
      } else if (state.selection.has(person.id)) {
        state.selection.delete(person.id);
      } else {
        state.selection.add(person.id);
      }
      state.lastSelectedId = person.id;
      refreshSelectionClasses();
      updateSelectionBar();
    });
    card.addEventListener("dragstart", (e) => {
      card.classList.add("dragging");
      if (state.selection.has(person.id) && state.selection.size) {
        const ids = [...state.selection];
        state.drag = { multi: true, ids, source, blockId: blockId || null };
        if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", ids.join(",")); } catch (_) { /* IE */ } }
      } else {
        state.drag = { userId: person.id, source, blockId: blockId || null };
        if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", person.id); } catch (_) { /* IE */ } }
      }
    });
    card.addEventListener("dragend", () => { card.classList.remove("dragging"); state.drag = null; });
    card.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      state.context = { userId: person.id, blockId: blockId || null };
      el.contextMenu.style.display = "block";
      el.contextMenu.style.left = e.pageX + "px";
      el.contextMenu.style.top = e.pageY + "px";
    });
    // Double-clic directement sur le numéro ou le nom → édition sur place.
    bp.title = "Double-cliquez pour changer le numéro";
    role.title = "Double-cliquez pour renommer";
    bp.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); startInlineEdit(person, "beltpack", bp); });
    role.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); startInlineEdit(person, "role", role); });
    return card;
  }

  // Case « + » ajoutée en fin de liste pour créer un beltpack (remplace le bouton dédié).
  function addTile(onClick) {
    const t = document.createElement("button");
    t.type = "button";
    t.className = "person-add";
    t.title = "Ajouter un beltpack";
    t.innerHTML = '<span class="pa-chip" aria-hidden="true">+</span><span class="pa-label">Beltpack</span>';
    t.addEventListener("click", onClick);
    return t;
  }

  // Édition sur place du nom (rôle) ou du numéro, déclenchée au double-clic.
  function startInlineEdit(person, field, target) {
    const input = document.createElement("input");
    input.className = "inline-edit";
    input.value = field === "beltpack" ? String(person.beltpack) : (person.role || "");
    if (field === "beltpack") { input.inputMode = "numeric"; input.maxLength = 12; }
    else input.maxLength = 80;
    target.textContent = "";
    target.appendChild(input);
    input.focus(); input.select();
    let done = false;
    const commit = () => {
      if (done) return; done = true;
      const v = input.value.trim();
      if (field === "beltpack") {
        if (!v) { toast("Numéro de beltpack requis", true); render(); return; }
        if (beltpackTaken(v, person.id)) { toast("Ce numéro de beltpack existe déjà", true); render(); return; }
        person.beltpack = v;
      } else {
        person.role = v;
      }
      markDirty(); render();
    };
    const cancel = () => { if (done) return; done = true; render(); };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); commit(); }
      else if (e.key === "Escape") { e.preventDefault(); cancel(); }
    });
    // On n'écoute le blur qu'au frame suivant : sinon un blur parasite synchrone,
    // en fin de double-clic, referme le champ aussitôt (bug intermittent).
    requestAnimationFrame(() => input.addEventListener("blur", commit));
    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("dblclick", (e) => e.stopPropagation());
  }

  function renderAvailable() {
    el.available.innerHTML = "";
    const all = state.data.people.filter((p) => !p.group_id);
    el.availableCount.textContent = `${all.length} beltpack${all.length > 1 ? "s" : ""}`;
    const q = (state.filter || "").trim().toLowerCase();
    const avail = q
      ? all.filter((p) => String(p.beltpack).toLowerCase().includes(q) || (p.role || "").toLowerCase().includes(q))
      : all;
    if (!all.length) {
      const h = document.createElement("div");
      h.className = "empty-hint";
      h.textContent = "Tous les beltpacks sont affectés";
      el.available.append(h);
    } else if (!avail.length) {
      const h = document.createElement("div");
      h.className = "empty-hint";
      h.textContent = "Aucun beltpack ne correspond";
      el.available.append(h);
    } else {
      avail.forEach((p) => el.available.append(personCard(p, "available", null)));
    }
    // La case « + » n'apparaît pas pendant une recherche (on cherche, on n'ajoute pas).
    if (!q) el.available.append(addTile(() => openPersonDialog(null, null)));
  }
  document.getElementById("available-filter").addEventListener("input", (e) => {
    state.filter = e.target.value;
    renderAvailable();
  });

  // Déplace un groupe à la position d'un autre et renumérote les 'order'.
  function moveGroup(draggedId, targetId) {
    if (draggedId === targetId) return;
    const groups = [...state.data.groups].sort((a, b) => (a.order || 0) - (b.order || 0));
    const from = groups.findIndex((g) => g.id === draggedId);
    const to = groups.findIndex((g) => g.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = groups.splice(from, 1);
    groups.splice(to, 0, moved);
    groups.forEach((g, i) => { g.order = i; });
    markDirty(); render();
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
      // Réordonnancement des groupes : dépose un groupe (glissé par son titre) sur un autre.
      wrap.addEventListener("dragover", (e) => {
        if (state.dragGroup && state.dragGroup !== block.id) { e.preventDefault(); wrap.classList.add("group-drop-target"); }
      });
      wrap.addEventListener("dragleave", (e) => { if (e.target === wrap) wrap.classList.remove("group-drop-target"); });
      wrap.addEventListener("drop", (e) => {
        if (state.dragGroup && state.dragGroup !== block.id) { e.preventDefault(); wrap.classList.remove("group-drop-target"); moveGroup(state.dragGroup, block.id); }
      });

      const header = document.createElement("div");
      header.className = "block-header";
      const titleWrap = document.createElement("div");
      titleWrap.className = "block-title";
      const swatch = document.createElement("span");
      swatch.className = "color-swatch";
      swatch.style.setProperty("--swatch-color", sanitizeColor(block.color) || "transparent");
      // Cliquer la case colorée change la couleur du groupe (remplace le bouton « Couleur »).
      swatch.title = "Changer la couleur du groupe";
      swatch.setAttribute("role", "button");
      swatch.setAttribute("aria-label", "Changer la couleur du groupe");
      swatch.tabIndex = 0;
      swatch.draggable = false;
      swatch.addEventListener("mousedown", (e) => e.stopPropagation());
      swatch.addEventListener("click", (e) => { e.stopPropagation(); openColorPicker(block.id); });
      swatch.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openColorPicker(block.id); } });
      const h3 = document.createElement("h3");
      h3.textContent = block.name;
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `${members.length} affectation${members.length > 1 ? "s" : ""}`;
      titleWrap.append(swatch, h3, badge);
      // Poignée de réordonnancement : on glisse le groupe par son titre.
      titleWrap.draggable = true;
      titleWrap.title = "Glisser pour réordonner les groupes";
      titleWrap.addEventListener("dragstart", (e) => {
        state.dragGroup = block.id; wrap.classList.add("group-dragging");
        if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", "group"); } catch (_) { /* IE */ } }
      });
      titleWrap.addEventListener("dragend", () => { state.dragGroup = null; wrap.classList.remove("group-dragging"); });

      const actions = document.createElement("div");
      actions.className = "block-actions";
      actions.append(
        chip("Renommer", () => renameBlock(block.id)),
        chip("Supprimer", () => deleteBlock(block.id), "danger"),
      );
      header.append(titleWrap, actions);

      const list = document.createElement("div");
      list.className = "block-items";
      list.dataset.blockId = block.id;
      list.addEventListener("dragover", (e) => { if (state.dragGroup) return; e.preventDefault(); list.dataset.dragover = "true"; if (e.dataTransfer) e.dataTransfer.dropEffect = "move"; });
      list.addEventListener("dragleave", () => { delete list.dataset.dragover; });
      list.addEventListener("drop", (e) => {
        e.preventDefault(); delete list.dataset.dragover;
        if (!state.drag || state.dragGroup) return;
        if (state.drag.multi) assignMany(state.drag.ids, block.id);
        else assign(state.drag.userId, block.id);
      });

      if (members.length) members.forEach((p) => list.append(personCard(p, "block", block.id)));
      else {
        const h = document.createElement("div");
        h.className = "empty-hint";
        h.textContent = "Déposez des beltpacks ici, ou";
        list.append(h);
      }
      list.append(addTile(() => openPersonDialog(null, block.id)));   // case « + » du groupe
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
    syncSettingsInputs();
    renderAvailable();
    renderBlocks();
    refreshAssignOptions();
    applyLiveIndicators();
  }

  /* ---------- État temps réel des beltpacks (statut connecté / batterie) ---------- */
  const DEFAULT_IND = { online: true, battery: true };
  let liveBeltpacks = null;   // null = antenne non connectée → aucun indicateur
  function applyLiveIndicators() {
    const ind = state.data.indicators || DEFAULT_IND;
    document.querySelectorAll(".bp-dot[data-bp]").forEach((d) => {
      const on = liveBeltpacks?.[d.dataset.bp]?.online;
      if (!ind.online || on === undefined) { d.className = "bp-dot"; d.title = ""; }
      else { d.className = "bp-dot " + (on ? "on" : "down"); d.title = on ? "En ligne" : "Hors ligne"; }
    });
    document.querySelectorAll(".bp-batt[data-bp]").forEach((b) => {
      const info = liveBeltpacks?.[b.dataset.bp];
      const pct = info?.online ? info.battery : null;
      if (!ind.battery || pct == null) { b.hidden = true; b.textContent = ""; }
      else { b.hidden = false; b.textContent = (info.charging ? "⚡" : "") + pct + "%"; b.className = "bp-batt" + (pct <= 20 ? " low" : ""); b.title = "Batterie " + pct + "%"; }
    });
  }
  async function pollLive() {
    let res;
    try { res = await apiSend("GET", "/api/antenna/live"); } catch { return; }
    liveBeltpacks = res.connected ? res.beltpacks : null;
    applyLiveIndicators();
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
  // Affectation/retrait en lot (drag d'une sélection multiple)
  function assignMany(ids, groupId) {
    ids.forEach((id) => { const p = findPerson(id); if (p) p.group_id = groupId; });
    exitSelection(); markDirty(); render();
  }
  function removeManyFromGroup(ids) {
    ids.forEach((id) => { const p = findPerson(id); if (p) p.group_id = null; });
    exitSelection(); markDirty(); render();
  }
  // Sélection d'une plage (MAJ+clic) selon l'ordre visuel des cartes.
  function selectRange(fromId, toId) {
    const ids = [...document.querySelectorAll(".person[data-user-id]")].map((c) => c.dataset.userId);
    let i = ids.indexOf(fromId), j = ids.indexOf(toId);
    if (i < 0 || j < 0) { state.selection.add(toId); return; }
    if (i > j) { const t = i; i = j; j = t; }
    for (let k = i; k <= j; k++) state.selection.add(ids[k]);
  }
  // Reflète la sélection sans reconstruire le DOM (sinon le double-clic est cassé).
  function refreshSelectionClasses() {
    document.querySelectorAll(".person[data-user-id]").forEach((c) => {
      c.classList.toggle("selected", state.selection.has(c.dataset.userId));
    });
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

  /* ---------- Réglages du tableau (inline dans la sidebar, live) ---------- */
  function syncSettingsInputs() {
    const d = state.data;
    const setVal = (id, v) => { const n = document.getElementById(id); if (n && document.activeElement !== n) n.value = v; };
    const setChk = (id, v) => { const n = document.getElementById(id); if (n) n.checked = v; };
    setVal("meta-title", d.title || "");
    setVal("meta-subtitle", d.subtitle || "");
    setVal("meta-columns", String(d.columns || 0));
    setVal("theme-select", d.theme === "day" ? "day" : "night");
    const ind = d.indicators || DEFAULT_IND;
    setChk("ind-online", ind.online !== false);
    setChk("ind-battery", ind.battery !== false);
    setChk("meta-perf", d.perf === true);
  }
  function bindSettings() {
    const title = document.getElementById("meta-title");
    title.addEventListener("input", () => {
      state.data.title = title.value;
      el.title.textContent = title.value.trim() || "Affectation Intercom";
      document.title = "Administration · " + (title.value.trim() || "ComRoster");
      markDirty();
    });
    const sub = document.getElementById("meta-subtitle");
    sub.addEventListener("input", () => {
      state.data.subtitle = sub.value;
      if (sub.value.trim()) { el.subtitle.textContent = sub.value.trim(); el.subtitle.hidden = false; }
      else el.subtitle.hidden = true;
      markDirty();
    });
    document.getElementById("meta-columns").addEventListener("change", (e) => {
      state.data.columns = parseInt(e.target.value, 10) || 0; markDirty();
    });
    document.getElementById("theme-select").addEventListener("change", (e) => {
      state.data.theme = e.target.value === "day" ? "day" : "night"; markDirty();
    });
    const onInd = () => {
      state.data.indicators = {
        online: document.getElementById("ind-online").checked,
        battery: document.getElementById("ind-battery").checked,
      };
      markDirty(); applyLiveIndicators();
    };
    document.getElementById("ind-online").addEventListener("change", onInd);
    document.getElementById("ind-battery").addEventListener("change", onInd);
    document.getElementById("meta-perf").addEventListener("change", (e) => {
      state.data.perf = e.target.checked; markDirty();
    });
    syncSettingsInputs();
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
      setStatus("Envoyé à l'affichage ✓", "updated");
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
    // Fichier de configuration ComRoster — extension .rost (contenu JSON).
    const blob = new Blob([JSON.stringify(state.data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `comroster-${Date.now()}.rost`;
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
          indicators: json.indicators || DEFAULT_IND, columns: json.columns || 0,
          perf: json.perf === true,
          groups: json.groups || [], people: json.people || [], beltpack_roles: json.beltpack_roles || {},
        };
        markDirty(); render();
      } catch { alert("Fichier invalide."); }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  /* ---------- Historique des publications ---------- */
  async function refreshHistory() {
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
    const clearBtn = document.getElementById("history-clear");
    if (clearBtn) clearBtn.disabled = !items.length;
  }
  async function openHistory() {
    await refreshHistory();
    document.getElementById("history-dialog").showModal();
  }
  async function clearHistory() {
    if (!confirm("Supprimer tout l'historique des publications ? Cette action est irréversible.")) return;
    try { await apiSend("POST", "/api/history/clear"); await refreshHistory(); toast("Historique supprimé"); }
    catch { alert("Suppression impossible."); }
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
    if (!state.drag) return;
    if (state.drag.multi) removeManyFromGroup(state.drag.ids.filter((id) => { const p = findPerson(id); return p && p.group_id; }));
    else if (state.drag.source === "block") removeFromGroup(state.drag.userId);
  });

  /* ---------- Branchements ---------- */
  // Déconnexion en POST (CSRF) via le formulaire caché — pas de onclick inline (CSP).
  document.getElementById("logout-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("logout-form").submit();
  });
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
  el.personForm.addEventListener("submit", submitPerson);
  bindSettings();
  el.publishBtn.addEventListener("click", publish);
  document.getElementById("export-btn").addEventListener("click", exportConfig);
  el.importInput.addEventListener("change", importConfig);
  document.getElementById("history-btn").addEventListener("click", openHistory);
  document.getElementById("history-clear").addEventListener("click", clearHistory);
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
    document.getElementById("dash-autosync").checked = !!settings.auto_sync;
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

  document.getElementById("wiz-connect-btn").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const ip = document.getElementById("wiz-ip").value.trim();
    const password = document.getElementById("wiz-password").value;
    const err = document.getElementById("wiz-error");
    const prog = document.getElementById("wiz-progress");
    err.hidden = true;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Connexion…"; if (prog) prog.hidden = false;
    try {
      await apiSend("POST", "/api/antenna/connect", { ip, password });
      await refreshAntennaBadge();
      await pollLive();
      wizGo(2);
    } catch (e) {
      err.textContent = e.payload?.error || "Connexion échouée — vérifiez l'adresse IP et le mot de passe.";
      err.hidden = false;
    } finally {
      btn.disabled = false; btn.textContent = label; if (prog) prog.hidden = true;
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

  document.getElementById("dash-autosync").addEventListener("change", async (e) => {
    const on = e.target.checked;
    try {
      await apiSend("PUT", "/api/settings", { auto_sync: on });
      toast(on ? "Mise à jour automatique activée" : "Mise à jour automatique désactivée");
    } catch { e.target.checked = !on; toast("Réglage impossible", true); }
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

  /* ---------- Réseau du boîtier ---------- */
  const networkDialog = document.getElementById("network-dialog");
  function toggleNetFields() {
    const link = document.getElementById("net-link").value;
    const modeSel = document.getElementById("net-mode");
    document.getElementById("net-wifi-fields").hidden = link !== "wifi";
    // link-local n'a pas de sens en Wi-Fi : option masquée, bascule vers DHCP
    const ll = modeSel.querySelector('option[value="link-local"]');
    ll.disabled = link === "wifi";
    ll.hidden = link === "wifi";
    if (link === "wifi" && modeSel.value === "link-local") modeSel.value = "dhcp";
    document.getElementById("net-static-fields").hidden = modeSel.value !== "static";
  }
  document.getElementById("net-mode").addEventListener("change", toggleNetFields);
  document.getElementById("net-link").addEventListener("change", toggleNetFields);

  async function openNetwork() {
    document.getElementById("net-error").hidden = true;
    document.getElementById("net-result").hidden = true;
    let cfg;
    try { cfg = await apiSend("GET", "/api/network"); } catch { cfg = { mode: "link-local" }; }
    document.getElementById("net-link").value = cfg.link || "ethernet";
    document.getElementById("net-ssid").value = (cfg.wifi && cfg.wifi.ssid) || "";
    const pskInput = document.getElementById("net-psk");
    pskInput.value = "";
    // Le psk ne redescend jamais de l'API : champ vide = « conserver l'existant »
    pskInput.placeholder = cfg.wifi && cfg.wifi.psk_set ? "•••••••• (inchangé si vide)" : "";
    document.getElementById("net-mode").value = cfg.mode || "link-local";
    document.getElementById("net-address").value = cfg.address || "";
    document.getElementById("net-prefix").value = cfg.prefix || 24;
    document.getElementById("net-gateway").value = cfg.gateway || "";
    document.getElementById("net-dns").value = (cfg.dns || []).join(", ");
    toggleNetFields();
    networkDialog.showModal();
  }
  document.getElementById("network-btn").addEventListener("click", openNetwork);

  document.getElementById("network-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const link = document.getElementById("net-link").value;
    const mode = document.getElementById("net-mode").value;
    const err = document.getElementById("net-error");
    const res = document.getElementById("net-result");
    err.hidden = true; res.hidden = true;
    const cfg = { link, mode };
    if (link === "wifi") {
      cfg.wifi = { ssid: document.getElementById("net-ssid").value.trim() };
      const psk = document.getElementById("net-psk").value;
      if (psk) cfg.wifi.psk = psk;   // vide → le serveur conserve le psk existant
    }
    if (mode === "static") {
      let addr = document.getElementById("net-address").value.trim();
      let prefix = parseInt(document.getElementById("net-prefix").value || "24", 10);
      // Tolère « 192.168.1.50/24 » saisi dans le champ IP → sépare IP et masque.
      const cidr = addr.match(/^(.+?)\s*\/\s*(\d{1,2})$/);
      if (cidr) { addr = cidr[1].trim(); prefix = parseInt(cidr[2], 10); }
      if (!addr) { err.textContent = "Saisissez l'adresse IP fixe (ex. 192.168.1.50)."; err.hidden = false; return; }
      cfg.address = addr;
      cfg.prefix = Number.isFinite(prefix) ? prefix : 24;
      const gw = document.getElementById("net-gateway").value.trim();
      if (gw) cfg.gateway = gw;
      const dns = document.getElementById("net-dns").value.split(",").map((s) => s.trim()).filter(Boolean);
      if (dns.length) cfg.dns = dns;
    }
    const submitBtn = e.submitter || document.querySelector("#network-form button[type=submit]");
    const prog = document.getElementById("net-progress");
    const rebootBtn = document.getElementById("reboot-btn");
    const label = submitBtn ? submitBtn.textContent : "";
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Enregistrement…"; }
    if (prog) prog.hidden = false;
    try {
      const r = await apiSend("PUT", "/api/network", cfg);
      const where = link === "wifi" ? `en Wi-Fi sur <b>${esc(cfg.wifi.ssid)}</b>` : "en filaire (RJ45)";
      res.innerHTML = mode === "static"
        ? `Enregistré. <b>Redémarrez le boîtier</b> pour appliquer — il repartira ${where} sur `
          + `<b>${esc(cfg.address)}</b> (adresse affichée à l'écran).`
        : `Enregistré. <b>Redémarrez le boîtier</b> pour appliquer — il repartira ${where} en adresse automatique.`;
      res.hidden = false;
      if (rebootBtn && r && r.reboot_required) rebootBtn.hidden = false;
      toast("Configuration réseau enregistrée");
    } catch (ex) {
      err.textContent = ex.payload?.error || "Configuration invalide";
      err.hidden = false;
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = label; }
      if (prog) prog.hidden = true;
    }
  });

  document.getElementById("reboot-btn").addEventListener("click", async (ev) => {
    if (!confirm("Redémarrer le boîtier maintenant ? L'écran et l'administration seront indisponibles ~1 minute.")) return;
    const btn = ev.currentTarget;
    btn.disabled = true; btn.textContent = "Redémarrage…";
    try {
      await apiSend("POST", "/api/reboot");
      toast("Redémarrage du boîtier en cours…");
    } catch {
      toast("Redémarrage impossible", true);
      btn.disabled = false; btn.textContent = "⟳ Redémarrer le boîtier";
    }
  });

  /* ---------- Sélection (clic direct sur un beltpack) ---------- */
  function updateSelectionBar() {
    document.getElementById("selection-count").textContent = `${state.selection.size} sélectionné(s)`;
    document.getElementById("selection-bar").classList.toggle("active", state.selection.size > 0);
  }
  function exitSelection() {
    state.selection.clear();
    state.lastSelectedId = null;
    refreshSelectionClasses();
    updateSelectionBar();
  }
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

  /* ---------- Synchro admin (auto-sync / autre poste) ---------- */
  // Si l'auto-sync (ou un autre poste) publie une nouvelle version, on recharge le
  // brouillon — mais SEULEMENT sans édits locaux en attente, pour ne pas écraser
  // un travail en cours dans cet onglet.
  function subscribeAdmin() {
    try {
      const es = new EventSource("/events");
      es.addEventListener("published", () => { if (!state.unpublished) load(); });
    } catch { /* SSE indisponible : l'admin reste sur son état courant */ }
  }

  /* ---------- Init ---------- */
  render();
  updateSelectionBar();
  refreshAntennaBadge();
  pollLive();
  setInterval(pollLive, 5000);
  subscribeAdmin();
  setStatus("Brouillon synchronisé", "idle");
})();
