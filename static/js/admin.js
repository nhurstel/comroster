/* ComRoster — Administration (édition du brouillon, branché sur l'API REST) */
(() => {
  // Optionnel chaîné : si le meta disparaissait, on n'arrête pas tout le script au
  // chargement (les requêtes échoueraient proprement côté serveur avec un CSRF vide).
  const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const SKINS = ["basique", "lineaire", "grille"];   // miroir de model.SKINS
  const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

  // Données initiales injectées via un bloc <script type="application/json">
  // (non exécuté → compatible CSP stricte sans script inline).
  let INITIAL = null;
  try { INITIAL = JSON.parse(document.getElementById("initial-data")?.textContent || "null"); } catch { /* bloc absent ou invalide */ }

  const state = {
    data: INITIAL || { title: "", subtitle: "", theme: "night", skin: "basique", groups: [], people: [], beltpack_roles: {} },
    drag: null,
    dragGroup: null,        // id du groupe en cours de réordonnancement
    context: null,
    busy: false,
    unpublished: false,
    editingPersonId: null,
    selection: new Set(),
    lastSelectedId: null,   // pour la sélection par plage (MAJ+clic)
    view: null,             // vue filtrante active de l'inventaire (null = aucune)
  };

  const el = {
    available: document.getElementById("available-users"),
    availableCount: document.getElementById("available-count"),
    blocks: document.getElementById("blocks-container"),
    blockCount: document.getElementById("board-count"),
    title: document.getElementById("board-title"),
    subtitle: document.getElementById("board-subtitle"),
    syncStatus: document.getElementById("sync-status"),
    syncLabel: document.getElementById("sync-label"),
    dirty: document.getElementById("dirty-indicator"),
    lastUpdated: document.getElementById("last-updated"),
    publishBtn: document.getElementById("publish-btn"),
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
    renderStatusBar();   // recalcule l'écart brouillon ↔ publié (dirty-indicator)
  }

  /* ---------- Notification transitoire (toast) ----------
     NB: cette fonction manquait — chaque appel `toast(...)` levait un ReferenceError.
     Comme les succès l'appellent DANS le try, le catch se déclenchait et affichait un
     faux message d'erreur (historique, réseau, imports, reconnexion antenne…). */
  let toastTimer = null;
  function toast(msg, isError) {
    let t = document.getElementById("cr-toast");
    if (!t) { t = document.createElement("div"); t.id = "cr-toast"; t.className = "cr-toast"; }
    // Un <dialog> MODAL vit dans le top layer du navigateur, au-dessus de tout z-index :
    // un toast laissé dans <body> est invisible tant qu'un dialogue est ouvert — le
    // refus (« n° déjà utilisé ») semblait muet. On monte donc le toast dans le dialogue
    // ouvert le plus récent s'il y en a un, sinon dans <body>.
    const modal = [...document.querySelectorAll("dialog[open]")].pop();
    const host = modal || document.body;
    if (t.parentElement !== host) host.appendChild(t);
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
        toast("Deux beltpacks ont le même numéro. Corrigez avant d'enregistrer.", true);
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
    card.dataset.bp = person.beltpack;      // pour le filtrage par vue (inventaire)
    if (blockId) card.dataset.blockId = blockId;

    // Contenu normal (toujours affiché)
    const bp = document.createElement("div");
    bp.className = "bp";
    bp.title = "Beltpack n°" + person.beltpack;
    bp.textContent = person.beltpack;

    const who = document.createElement("div");
    who.className = "who";
    const role = document.createElement("span");
    role.className = "role";
    role.textContent = person.role || "—";
    who.append(role);

    const live = document.createElement("div");
    live.className = "card-live";
    const batt = document.createElement("span"); batt.className = "bp-batt"; batt.dataset.bp = person.beltpack; batt.hidden = true;
    // Voyant temps réel : à droite de la ligne, dans un conteneur centré — pas dans le
    // flux de texte, où un élément invisible décalerait la ligne de base des voisins.
    const dot = document.createElement("span");
    dot.className = "bp-dot";
    dot.dataset.bp = person.beltpack;
    live.append(batt, dot);
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
    // Zone de dépôt pointillée (registre maquette) : le bloc est déjà cible de
    // glisser-déposer ; ce même encart sert aussi à ajouter un beltpack au clic.
    const t = document.createElement("button");
    t.type = "button";
    t.className = "drop-tile";
    t.title = "Ajouter un beltpack";
    t.textContent = "déposer un beltpack";
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
    el.availableCount.textContent = all.length;
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
    // L'ajout se fait par le bouton de pied « + Ajouter un beltpack » (pas de tuile dans
    // la liste : elle ferait doublon).
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

  // La cascade ne joue qu'à l'ARRIVÉE sur le plateau : chaque édition re-crée les
  // blocs, et une cascade rejouée à chaque frappe faisait sauter toute la grille.
  let cascadePlayed = false;
  function renderBlocks() {
    el.blocks.innerHTML = "";
    const groups = [...state.data.groups].sort((a, b) => (a.order || 0) - (b.order || 0));
    const assigned = state.data.people.filter((p) => p.group_id).length;
    el.blockCount.textContent =
      `${groups.length} groupe${groups.length > 1 ? "s" : ""} · ${assigned} affecté${assigned > 1 ? "s" : ""}`;
    if (!cascadePlayed) {
      cascadePlayed = true;
      el.blocks.dataset.cascade = "1";
      // Attribut retiré après le dernier délai + la durée : les rendus suivants
      // (éditions) n'animent plus rien.
      setTimeout(() => { delete el.blocks.dataset.cascade; }, groups.length * 40 + 400);
    }
    groups.forEach((block, bi) => {
      const members = state.data.people.filter((p) => p.group_id === block.id);
      const wrap = document.createElement("section");
      wrap.className = "admin-block";
      wrap.dataset.blockId = block.id;
      // Loi de la maquette : i×40+20 ms (sans effet hors cascade initiale).
      wrap.style.animationDelay = `${bi * 40 + 20}ms`;
      const gel = sanitizeColor(block.color);
      wrap.style.setProperty("--block-accent", gel || "var(--primary)");
      // Aplat plein : le bloc EST la couleur du groupe. L'encre suit la luminance
      // réelle de cette couleur (static/js/ink.js, la même que l'écran de régie) ;
      // sans verdict — couleur absente ou non littérale — la CSS garde son fond sombre.
      wrap.style.setProperty("--gel", gel || "");
      const ink = window.ComRoster.inkFor(gel);
      if (ink) wrap.dataset.ink = ink;
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
      // Compte seul (pas « 2 affectations ») : dans une carte de ~300 px, le libellé
      // long poussait les actions hors de l'en-tête. Le mot complet passe en infobulle.
      badge.textContent = String(members.length).padStart(2, "0");
      badge.title = `${members.length} affectation${members.length > 1 ? "s" : ""}`;
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
    // Si la vue Table est active, la maintenir à jour avec les mêmes données.
    const table = document.getElementById("blocks-table");
    if (table && !table.hidden) renderTable();
  }

  /* Vue Table : tous les beltpacks à plat (n° / rôle / groupe), pour trier et lire en
     diagonale. Rendu en CSSOM (aucun attribut style — CSP stricte). */
  function renderTable() {
    const host = document.getElementById("blocks-table");
    if (!host) return;
    const byId = new Map(state.data.groups.map((g) => [g.id, g]));
    const rows = [...state.data.people].sort((a, b) =>
      String(a.beltpack).localeCompare(String(b.beltpack), "fr", { numeric: true }));
    host.innerHTML =
      `<div class="bt-head"><span>BP</span><span>Rôle</span><span>Groupe</span></div>`
      + rows.map((p) => {
        const g = byId.get(p.group_id);
        // Le groupe est une PASTILLE à l'aplat du groupe (même langage que les blocs) :
        // une barrette de 3 px était illisible à ces tailles.
        return `<div class="bt-row" data-user-id="${esc(p.id)}">`
          + `<span class="bt-bp">${esc(p.beltpack)}</span>`
          + `<span class="bt-role">${esc(p.role || "—")}</span>`
          + `<span class="bt-grp">${g ? `<span class="bt-chip" data-color="${esc(sanitizeColor(g.color) || "")}">${esc(g.name)}</span>` : "—"}</span></div>`;
      }).join("");
    host.querySelectorAll(".bt-chip").forEach((c) => {
      const color = c.dataset.color;
      if (!color) return;
      c.style.background = color;                       // CSSOM : la CSP interdit style=""
      const ink = window.ComRoster.inkFor(color);       // même règle d'encre que l'écran
      if (ink) c.dataset.ink = ink;
    });
    host.querySelectorAll(".bt-row").forEach((r) =>
      r.addEventListener("dblclick", () => openPersonDialog(r.dataset.userId)));
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
    renderInventory();
    applyView();
    renderStatusBar();   // apparence + écart suivent le brouillon (sans appel réseau)
  }

  /* ---------- Inventaire (barre latérale) ----------
     Liste des groupes (clic = aller au groupe dans le plan de travail) et vues
     filtrantes. Les compteurs « Hors ligne » / « Batterie faible » dépendent de l'état
     temps réel : renderInventory() est donc rappelé aussi depuis applyLiveIndicators(). */
  const LOW_BATTERY = 30;                  // seuil de la vue « batterie faible » (%)
  function liveStat(bp) {                   // état temps réel d'un beltpack, ou null
    return liveBeltpacks ? (liveBeltpacks[bp] || { online: false }) : null;
  }
  function viewCounts() {
    let offline = 0, low = 0;
    if (liveBeltpacks) {
      state.data.people.forEach((p) => {
        const s = liveStat(p.beltpack);
        if (!s.online) offline += 1;
        else if (typeof s.battery === "number" && s.battery < LOW_BATTERY) low += 1;
      });
    }
    return { offline, low };
  }
  function renderInventory() {
    const host = document.getElementById("group-inventory");
    if (!host) return;
    const c = viewCounts();
    const groups = [...state.data.groups].sort((a, b) => (a.order || 0) - (b.order || 0));
    // Pas de `style="…"` en attribut : la CSP stricte de l'admin le bloque (leçon
    // 2026-07-07). La couleur de pastille est portée par data-color et appliquée en
    // CSSOM après l'insertion, comme le reste du rendu (renderBlocks).
    const row = (attr, color, label, count, cls) =>
      `<a class="inv-item${cls ? " " + cls : ""}" ${attr} role="button" tabindex="0">`
      + `<i class="inv-dot"${color ? ` data-color="${esc(color)}"` : ""}></i>`
      + `<span class="inv-label">${esc(label)}</span>`
      + `<span class="inv-count">${count}</span></a>`;
    // Les vues temps réel n'ont de sens qu'antenne connectée : la section entière est
    // masquée sinon. Pas de vue « Tous » (c'est l'état par défaut) ni « Non affectés »
    // (la réserve, toujours visible à droite, EST cette vue).
    const liveRows = liveBeltpacks
      ? `<div class="nav-label">Vues</div>`
        + row('data-view="offline"', "", "Hors ligne", c.offline, "inv-warn")
        + row('data-view="low"', "", `Batterie < ${LOW_BATTERY} %`, c.low, "inv-warn")
      : "";
    host.innerHTML =
      `<div class="nav-label">Groupes</div>`
      + groups.map((g) => row(`data-group="${g.id}"`, sanitizeColor(g.color) || "var(--primary)",
                              g.name, state.data.people.filter((p) => p.group_id === g.id).length)).join("")
      + liveRows;
    host.querySelectorAll(".inv-dot[data-color]").forEach((i) => { i.style.background = i.dataset.color; });
    host.querySelectorAll("[data-group]").forEach((a) =>
      a.addEventListener("click", () => goToGroup(a.dataset.group)));
    host.querySelectorAll("[data-view]").forEach((a) => {
      const act = () => toggleView(a.dataset.view);
      a.addEventListener("click", act);
      a.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); act(); } });
    });
    host.querySelectorAll("[data-view]").forEach((a) =>
      a.classList.toggle("active", a.dataset.view === state.view));
  }

  function goToGroup(gid) {
    selectTab("board");
    const wrap = el.blocks.querySelector(`.admin-block[data-block-id="${gid}"]`);
    if (!wrap) return;
    wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
    wrap.classList.add("flash");
    setTimeout(() => wrap.classList.remove("flash"), 900);
  }

  /* Vue filtrante : marque en direct les cartes qui NE correspondent PAS pour que le CSS
     les estompe. Purement visuel et réversible — ni les données ni le glisser-déposer ne
     sont touchés (un second clic sur la vue active la retire). */
  function toggleView(v) {
    state.view = state.view === v ? null : v;
    renderInventory();
    applyView();
  }
  function groupNameOf(gid) {
    const g = state.data.groups.find((x) => x.id === gid);
    return g ? g.name : "";
  }
  function personMatchesText(card) {
    const q = (state.boardQuery || "").trim().toLowerCase();
    if (!q) return true;
    const bp = (card.dataset.bp || "").toLowerCase();
    const role = (card.querySelector(".role")?.textContent || "").toLowerCase();
    const gname = groupNameOf(card.dataset.blockId || "").toLowerCase();
    return bp.includes(q) || role.includes(q) || gname.includes(q);
  }
  function personMatchesView(bp) {
    switch (state.view) {
      case "offline": { const s = liveStat(bp); return s ? !s.online : false; }
      case "low": { const s = liveStat(bp); return !!(s && s.online && typeof s.battery === "number" && s.battery < LOW_BATTERY); }
      default: return true;   // null → tout correspond
    }
  }
  function applyView() {
    const viewActive = !!state.view;
    const textActive = !!(state.boardQuery || "").trim();
    const active = viewActive || textActive;
    document.querySelectorAll(".person[data-bp]").forEach((card) => {
      const okView = !viewActive || personMatchesView(card.dataset.bp);
      const okText = personMatchesText(card);
      card.classList.toggle("view-dim", active && !(okView && okText));
    });
    // Un groupe entièrement estompé est lui-même mis en retrait.
    el.blocks.querySelectorAll(".admin-block").forEach((wrap) => {
      const people = wrap.querySelectorAll(".person[data-bp]");
      const anyMatch = !active || [...people].some((c) => !c.classList.contains("view-dim"));
      wrap.classList.toggle("view-dim", active && people.length > 0 && !anyMatch);
    });
  }

  /* ---------- État temps réel des beltpacks (statut connecté / batterie) ---------- */
  const DEFAULT_IND = { online: true, battery: true };
  let liveBeltpacks = null;   // null = antenne non connectée → aucun indicateur
  function applyLiveIndicators() {
    const ind = state.data.indicators || DEFAULT_IND;
    document.querySelectorAll(".bp-dot[data-bp]").forEach((d) => {
      const on = liveBeltpacks?.[d.dataset.bp]?.online;
      // Indicateur décoché → masqué ; sinon point neutre (état inconnu) ou vert/gris.
      if (!ind.online) { d.className = "bp-dot hidden"; d.title = ""; }
      else if (on === undefined) { d.className = "bp-dot"; d.title = ""; }
      else { d.className = "bp-dot " + (on ? "on" : "down"); d.title = on ? "En ligne" : "Hors ligne"; }
    });
    document.querySelectorAll(".bp-batt[data-bp]").forEach((b) => {
      const info = liveBeltpacks?.[b.dataset.bp];
      const pct = info?.online ? info.battery : null;
      if (!ind.battery || pct == null) { b.hidden = true; b.textContent = ""; }
      else { b.hidden = false; b.textContent = (info.charging ? "⚡" : "") + pct + "%"; b.className = "bp-batt" + (pct <= 20 ? " low" : ""); b.title = "Batterie " + pct + "%"; }
    });
  }
  function applyLiveData(res) {
    liveBeltpacks = res && res.connected ? res.beltpacks : null;
    applyLiveIndicators();
    renderInventory();      // compteurs « hors ligne » / « batterie » + apparition des vues
    applyView();
  }
  async function pollLive() {
    let res;
    try { res = await apiSend("GET", "/api/antenna/live"); } catch { return; }
    applyLiveData(res);
  }

  /* ---------- Mutations ---------- */
  function assign(personId, groupId) {
    const p = findPerson(personId);
    if (!p || p.group_id === groupId) return;   // inconnu ou déjà dans ce groupe
    p.group_id = groupId; markDirty(); render();
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
  // Dialog de groupe partagé création/renommage (plus de prompt() natif).
  let renamingBlockId = null;
  function openCreateBlock() {
    renamingBlockId = null;
    el.blockForm.reset();
    document.getElementById("block-dialog-title").textContent = "Créer un nouveau groupe";
    document.getElementById("block-submit").textContent = "Ajouter le groupe";
    el.blockDialog.showModal();
    requestAnimationFrame(() => el.blockName.focus());
  }
  function renameBlock(id) {
    const b = findBlock(id);
    if (!b) return;
    renamingBlockId = id;
    document.getElementById("block-dialog-title").textContent = "Renommer le groupe";
    document.getElementById("block-submit").textContent = "Renommer";
    el.blockName.value = b.name;
    el.blockDialog.showModal();
    requestAnimationFrame(() => { el.blockName.focus(); el.blockName.select(); });
  }
  function deleteBlock(id) {
    const b = findBlock(id);
    if (!confirm(`Supprimer le groupe « ${b.name} » ? Les beltpacks retournent dans la liste disponible.`)) return;
    state.data.people.forEach((p) => { if (p.group_id === id) p.group_id = null; });
    state.data.groups = state.data.groups.filter((g) => g.id !== id);
    markDirty(); render();
  }

  /* ---------- Color picker ---------- */
  /* Palette bornée des couleurs de groupe. Chaque teinte est calibrée pour donner un
     contraste ≥ 4.5:1 (WCAG AA) avec l'encre calculée par inkFor(), dans les DEUX modes de
     luminosité — c'est ce que le sélecteur natif ne garantissait pas (d'où le rouge
     #C4544A retenu au banc, illisible à 4.2:1 sur son aplat). Vives à encre sombre puis
     profondes à encre claire. */
  const GROUP_PALETTE = [
    "#E1554C", "#E8863B", "#E4B93C", "#8FBF52", "#3FA6B0", "#4F86C6",
    "#8B7CC8", "#C062A6", "#B0B7C0", "#9B2F2F", "#2C4C8E", "#2E6B34",
  ];
  const colorDialog = document.getElementById("color-dialog");
  const colorGrid = document.getElementById("color-grid");

  function openColorPicker(blockId) {
    const b = findBlock(blockId);
    if (!b) return;
    const current = sanitizeColor(b.color);
    colorGrid.innerHTML = "";
    GROUP_PALETTE.forEach((hex) => {
      const sw = document.createElement("button");
      sw.type = "button";
      sw.className = "color-choice" + (hex === current ? " selected" : "");
      sw.style.background = hex;                 // CSSOM, jamais un attribut style (CSP)
      sw.title = hex;
      sw.setAttribute("aria-label", "Couleur " + hex);
      sw.addEventListener("click", () => {
        if (b.color !== hex) { b.color = hex; markDirty(); render(); }
        colorDialog.close();
      });
      colorGrid.append(sw);
    });
    colorDialog.showModal();
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
    roleAutofilled = false;
    el.personDialog.showModal();
    requestAnimationFrame(() => el.personBeltpack.focus());
  }

  // Le nom suit le beltpack : proposer le nom déjà connu pour ce numéro. La proposition
  // reste VIVANTE tant que l'utilisateur n'a pas touché le champ nom lui-même : taper
  // « 2 » propose le nom du 2, continuer en « 22 » doit re-proposer (ou vider) — un
  // remplissage qui se fige au premier chiffre est un piège. Une saisie manuelle du
  // nom, elle, ne doit jamais être écrasée.
  let roleAutofilled = false;
  el.personBeltpack.addEventListener("input", () => {
    if (el.personRole.value && !roleAutofilled) return;   // nom saisi à la main : intouchable
    const known = state.data.beltpack_roles?.[normBp(el.personBeltpack.value)];
    el.personRole.value = known || "";
    roleAutofilled = !!known;
  });
  el.personRole.addEventListener("input", () => { roleAutofilled = false; });

  function submitPerson(e) {
    e.preventDefault();
    const beltpack = normBp(el.personBeltpack.value);
    if (!beltpack) { toast("Indiquez le numéro du beltpack.", true); el.personBeltpack.focus(); return; }
    if (beltpackTaken(beltpack, state.editingPersonId)) {
      // Dire OÙ il est : « déjà utilisé » seul oblige à chercher dans tous les groupes.
      const holder = state.data.people.find(
        (p) => p.id !== state.editingPersonId && normBp(p.beltpack) === beltpack);
      const where = holder?.group_id
        ? `dans « ${groupNameOf(holder.group_id)} »` : "dans la réserve";
      toast(`Le n°${beltpack} existe déjà ${where}.`, true);
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
    setVal("skin-select", SKINS.includes(d.skin) ? d.skin : "basique");
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
    const crumbSep = document.getElementById("crumb-sep");
    sub.addEventListener("input", () => {
      state.data.subtitle = sub.value;
      const has = !!sub.value.trim();
      if (has) { el.subtitle.textContent = sub.value.trim(); }
      el.subtitle.hidden = !has;
      if (crumbSep) crumbSep.hidden = !has;   // le « / » ne s'affiche qu'avec un sous-titre
      markDirty();
    });
    document.getElementById("meta-columns").addEventListener("change", (e) => {
      state.data.columns = parseInt(e.target.value, 10) || 0; markDirty();
    });
    document.getElementById("theme-select").addEventListener("change", (e) => {
      state.data.theme = e.target.value === "day" ? "day" : "night"; markDirty();
    });
    document.getElementById("skin-select").addEventListener("change", (e) => {
      state.data.skin = SKINS.includes(e.target.value) ? e.target.value : "basique"; markDirty();
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
      reloadPreview();                 // le témoin suit l'écran de régie, il vient de changer
      refreshStatus();                 // nouveau résumé publié → écart remis à zéro
      setStatus("Envoyé à l'affichage ✓", "updated");
      // Après le flash de confirmation, la chip retourne à sa vérité recalculée
      // (« À jour » / « N en attente »), pas à un libellé figé.
      setTimeout(() => { if (el.syncStatus?.dataset.state === "updated") { el.syncStatus.dataset.state = "idle"; renderStatusBar(); } }, 2500);
    } catch (err) {
      if (err.message === "beltpack_conflict") toast("Beltpack en double : impossible de publier.", true);
      else toast("Échec de la publication.", true);
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
          skin: SKINS.includes(json.skin) ? json.skin : "basique",
          indicators: json.indicators || DEFAULT_IND, columns: json.columns || 0,
          perf: json.perf === true,
          groups: json.groups || [], people: json.people || [], beltpack_roles: json.beltpack_roles || {},
        };
        markDirty(); render();
      } catch { toast("Fichier invalide.", true); }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  /* ---------- Historique des publications ---------- */
  async function refreshHistory() {
    let items = [];
    try { items = await apiSend("GET", "/api/history"); } catch { toast("Historique indisponible.", true); return; }
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
        setTimeout(() => { if (el.syncStatus?.dataset.state === "updated") { el.syncStatus.dataset.state = "idle"; renderStatusBar(); } }, 2500);
      } catch { toast("Restauration impossible.", true); }
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
    catch { toast("Suppression impossible.", true); }
  }

  /* ---------- Journal d'événements ----------
     Ce qu'il s'est PASSÉ (événements serveur), par opposition aux « Publications »
     qui archivent des états restaurables. Codes stables côté serveur, libellés ici. */
  const JOURNAL_LABELS = {
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
  const journalWhen = (iso) => {
    try {
      return new Date(iso).toLocaleString("fr-FR",
        { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch { return "—"; }
  };
  async function openJournal() {
    let entries = [];
    try { entries = await apiSend("GET", "/api/journal"); }
    catch { toast("Journal indisponible.", true); return; }
    const list = document.getElementById("journal-list");
    list.innerHTML = entries.length
      ? entries.map((e) =>
          `<li><span class="j-time">${esc(journalWhen(e.ts))}</span>`
          + `<span class="j-label">${esc(JOURNAL_LABELS[e.event] || e.event)}</span>`
          + (e.detail ? `<span class="j-detail">${esc(e.detail)}</span>` : "")
          + "</li>").join("")
      : "<li class='empty-hint'>Rien à signaler pour l'instant.</li>";
    document.getElementById("journal-dialog").showModal();
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
  document.getElementById("add-block-btn").addEventListener("click", openCreateBlock);
  el.blockForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = el.blockName.value.trim();
    if (!v) return;
    el.blockDialog.close();
    if (renamingBlockId) {
      const b = findBlock(renamingBlockId);
      if (b) { b.name = v; markDirty(); render(); }
      renamingBlockId = null;
    } else {
      createBlock(v);
    }
  });
  el.personForm.addEventListener("submit", submitPerson);
  bindSettings();
  el.publishBtn.addEventListener("click", publish);
  document.getElementById("export-btn").addEventListener("click", exportConfig);
  el.importInput.addEventListener("change", importConfig);
  document.getElementById("history-btn").addEventListener("click", openHistory);
  document.getElementById("history-clear").addEventListener("click", clearHistory);
  document.getElementById("history-close").addEventListener("click", () => document.getElementById("history-dialog").close());
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

  /* ---------- Report de l'écran de régie ----------
     Une iframe sur /admin/preview : c'est la VRAIE page display servant l'état PUBLIÉ,
     avec son vrai CSS et son vrai JS. Aucun moteur de rendu parallèle à maintenir, donc
     aucune dérive possible. Rendue à 1920x1080 (résolution du kiosk) puis mise à l'échelle.
     Elle ne suit PAS le brouillon : elle se rafraîchit aux publications (locale ou
     distante), pas aux enregistrements. */
  const previewDialog = document.getElementById("preview-dialog");
  const previewFrame = document.getElementById("preview-iframe");
  const previewMini = document.getElementById("preview-mini");   // témoin permanent
  const previewDock = document.getElementById("preview-dock");
  const dockToggle = document.getElementById("preview-dock-toggle");

  // L'échelle se déduit de la largeur de rendu déclarée en CSS (`offsetWidth`, insensible
  // au transform) : la résolution de l'écran de régie n'est écrite qu'à un seul endroit.
  function fitPreview(frame) {
    const box = frame?.parentElement;
    if (!box || !box.clientWidth || !frame.offsetWidth) return;
    frame.style.transform = `scale(${box.clientWidth / frame.offsetWidth})`;
  }
  function fitPreviews() { fitPreview(previewMini); fitPreview(previewFrame); }

  // Un seul horodatage pour les deux : ils montrent forcément le même état publié.
  // `scroll=1` n'est demandé que pour le grand aperçu (cf. commentaire de /admin/preview).
  function reloadPreview() {
    const t = Date.now();
    if (previewMini && previewDock.dataset.open === "1") previewMini.src = `/admin/preview?t=${t}`;
    if (previewDialog?.open) previewFrame.src = `/admin/preview?scroll=1&t=${t}`;
  }

  // Repli mémorisé : sans persistance il se rouvrirait à chaque publication (l'admin
  // recharge la page rarement, mais assez pour que ce soit agaçant).
  const DOCK_KEY = "comroster.preview-dock";
  function setDock(open) {
    previewDock.dataset.open = open ? "1" : "0";
    dockToggle.setAttribute("aria-expanded", String(open));
    try { localStorage.setItem(DOCK_KEY, open ? "1" : "0"); } catch { /* mode privé */ }
    // Replié, l'iframe est retirée du DOM de rendu : on la recharge (et remesure) au
    // dépliage, sinon elle afficherait l'état publié d'il y a peut-être une heure.
    if (open) { fitPreview(previewMini); reloadPreview(); }
  }
  dockToggle.addEventListener("click", () => setDock(previewDock.dataset.open !== "1"));
  let dockOpen = true;
  try { dockOpen = localStorage.getItem(DOCK_KEY) !== "0"; } catch { /* mode privé */ }

  function openBigPreview() {
    previewDialog.showModal();
    fitPreviews();
    reloadPreview();
  }
  document.getElementById("preview-btn").addEventListener("click", openBigPreview);
  // Clic hors du panneau = fermeture. On teste les COORDONNÉES contre le rectangle du
  // dialog, pas `e.target === previewDialog` : le padding du dialog appartient au dialog
  // lui-même, un clic dedans le fermerait alors qu'il est visuellement à l'intérieur.
  previewDialog.addEventListener("click", (e) => {
    const r = previewDialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) {
      previewDialog.close();
    }
  });
  document.getElementById("preview-refresh").addEventListener("click", reloadPreview);
  window.addEventListener("resize", fitPreviews);
  setDock(dockOpen);               // pose l'état + premier chargement du témoin
  fitPreview(previewFrame);

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
    const applyBtn = document.getElementById("net-apply-btn");
    const label = submitBtn ? submitBtn.textContent : "";
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Enregistrement…"; }
    if (prog) prog.hidden = false;
    try {
      await apiSend("PUT", "/api/network", cfg);
      const where = link === "wifi" ? `en Wi-Fi sur <b>${esc(cfg.wifi.ssid)}</b>` : "en filaire (RJ45)";
      res.innerHTML = mode === "static"
        ? `Enregistré. Cliquez <b>Appliquer maintenant</b> — le boîtier passera ${where} sur `
          + `<b>${esc(cfg.address)}</b> (adresse affichée à l'écran). Reconnectez-vous ensuite sur cette adresse.`
        : `Enregistré. Cliquez <b>Appliquer maintenant</b> — le boîtier passera ${where} en adresse automatique.`;
      res.hidden = false;
      if (applyBtn) applyBtn.hidden = false;
      toast("Configuration réseau enregistrée");
    } catch (ex) {
      err.textContent = ex.payload?.error || "Configuration invalide";
      err.hidden = false;
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = label; }
      if (prog) prog.hidden = true;
    }
  });

  // Applique la config réseau à chaud (nmcli), sans redémarrer le boîtier.
  document.getElementById("net-apply-btn").addEventListener("click", async (ev) => {
    if (!confirm("Appliquer la configuration réseau maintenant ?\n\nSi l'adresse change, cette page perdra la connexion : rouvrez l'admin sur la nouvelle adresse.")) return;
    const btn = ev.currentTarget;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Application…";
    try {
      await apiSend("POST", "/api/network/apply");
      toast("Configuration réseau appliquée");
    } catch (e) {
      // Comme pour le redémarrage : une coupure est ATTENDUE si l'IP change.
      const refus = e && e.payload && e.payload.error;
      toast(refus || "Appliqué — reconnectez-vous sur la nouvelle adresse", Boolean(refus));
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });

  document.getElementById("reboot-btn").addEventListener("click", async (ev) => {
    if (!confirm("Redémarrer le boîtier maintenant ? L'écran et l'administration seront indisponibles ~1 minute.")) return;
    const btn = ev.currentTarget;
    const original = btn.innerHTML;            // le bouton de nav contient une icône SVG
    btn.disabled = true; btn.textContent = "Redémarrage…";
    try {
      await apiSend("POST", "/api/reboot");
      toast("Redémarrage du boîtier en cours…");
    } catch (e) {
      // Si le boîtier redémarre VRAIMENT, la requête peut échouer (connexion coupée).
      // Seule une réponse d'erreur explicite du serveur signifie que ça n'a pas marché.
      const refus = e && e.payload && e.payload.error;
      if (refus) {
        toast(refus, true);
        btn.disabled = false; btn.innerHTML = original;
      } else {
        toast("Redémarrage du boîtier en cours…");
      }
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
    try {
      await apiSend("POST", "/api/configs", { name });
    } catch (e) { toast(e.payload?.error || "Sauvegarde impossible", true); return; }
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
      es.addEventListener("open", () => setSseHealth(true));
      es.addEventListener("error", () => setSseHealth(false));
      es.addEventListener("published", () => {
        reloadPreview();          // publication venue d'ailleurs (autre poste, auto-sync)
        refreshStatus();          // l'état à l'antenne a changé
        if (!state.unpublished) load();
      });
      // État live des beltpacks poussé par le serveur (même flux `live` que l'affichage) :
      // remplace l'ancien polling périodique. L'admin restant abonné, le poller publie.
      es.addEventListener("live", (e) => { try { applyLiveData(JSON.parse(e.data)); } catch { /* ignore */ } });
    } catch { /* SSE indisponible : l'admin reste sur son état courant */ }
  }

  /* ---------- Barre d'état ----------
     Ce qui est réellement à l'antenne (état publié, afficheurs connectés) et l'écart avec
     le brouillon en cours. Le résumé publié vient de /api/status ; l'écart se calcule
     contre les compteurs du brouillon local (state.data). L'apparence affichée est celle
     du BROUILLON — c'est ce que la prochaine publication enverra. */
  let publishedSummary = null;   // {groups, people, updated_at} ou null (rien de publié)

  function setSseHealth(ok) {
    const seg = document.getElementById("status-sse");
    if (seg) seg.dataset.ok = ok ? "1" : "0";
  }
  const hhmm = (iso) => { try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); } catch { return "—"; } };

  function renderStatusBar(displays) {
    const skinLabel = { basique: "Basique", lineaire: "Linéaire", grille: "Grille" };
    const setTxt = (id, v) => { const n = document.getElementById(id); if (n) n.textContent = v; };
    if (displays != null) {
      setTxt("status-sse-text", displays === 0 ? "aucun afficheur"
        : displays + " afficheur" + (displays > 1 ? "s" : ""));
    }
    setTxt("status-published", publishedSummary ? "publié " + hhmm(publishedSummary.updated_at) : "jamais publié");
    setTxt("status-skin", skinLabel[state.data.skin] || "Basique");

    // Écart brouillon ↔ publié. Le drapeau `unpublished` couvre la session (toute édition
    // le lève) ; la comparaison d'horodatages couvre le RECHARGEMENT de la page — un
    // brouillon plus récent que le publié est en attente même si on n'a encore rien
    // touché ici. Les compteurs ne servent qu'à préciser « combien ».
    const pend = document.getElementById("dirty-indicator");
    if (!pend) return;
    // Sans rien de publié, l'écart est le brouillon entier (le segment « jamais publié »
    // du pied de page dit déjà l'absence de publication : pas de doublon de texte).
    const dg = state.data.groups.length - (publishedSummary ? publishedSummary.groups : 0);
    const dp = state.data.people.length - (publishedSummary ? publishedSummary.people : 0);
    const draftAhead = publishedSummary
      ? (state.data.updated_at || "") > (publishedSummary.updated_at || "")   // ISO : ordre lexical
      : (state.data.groups.length > 0 || state.data.people.length > 0);
    const unpublished = state.unpublished || draftAhead;
    if (!unpublished) { pend.textContent = ""; }
    else {
      const parts = [];
      let lastAbs = 1;
      if (dg) { lastAbs = Math.abs(dg); parts.push((dg > 0 ? "+" : "") + dg + " groupe" + (lastAbs > 1 ? "s" : "")); }
      if (dp) { lastAbs = Math.abs(dp); parts.push((dp > 0 ? "+" : "") + dp + " beltpack" + (lastAbs > 1 ? "s" : "")); }
      // « non publié » s'accorde avec le dernier terme énuméré (« +1 groupe non publié »,
      // « +1 groupe, +2 beltpacks non publiés »).
      pend.textContent = parts.length
        ? parts.join(", ") + " non publié" + (lastAbs > 1 ? "s" : "")
        : "modifications non publiées";
    }

    // Chip d'en-tête « N en attente » (maquette) : même vérité que le pied de page, en
    // résumé. Les états transitoires (enregistrement en cours, erreur) restent
    // prioritaires — on ne les écrase pas.
    const chipState = el.syncStatus?.dataset.state;
    if (chipState === "syncing" || chipState === "error" || chipState === "updated") return;
    if (!unpublished) { setStatus("À jour", "idle"); return; }
    const n = Math.abs(dg) + Math.abs(dp);
    setStatus(n ? `${n} en attente` : "En attente de publication", "pending");
  }

  async function refreshStatus() {
    let res;
    try { res = await apiSend("GET", "/api/status"); } catch { return; }
    publishedSummary = res.published || null;
    renderStatusBar(res.displays);
  }

  /* ---------- Onglets ----------
     Affectations / Écran sont des panneaux ; Journal ouvre son dialogue (data-launch)
     sans changer de panneau. Antenne et réseau ont leur bouton unique ailleurs
     (chip d'en-tête, barre latérale) : pas de lanceur en doublon ici. */
  function selectTab(name) {
    document.querySelectorAll(".admin-tabs .tab[data-tab]").forEach((t) =>
      t.setAttribute("aria-selected", String(t.dataset.tab === name)));
    document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.dataset.panel !== name; });
  }
  document.querySelectorAll(".admin-tabs .tab[data-tab]").forEach((t) =>
    t.addEventListener("click", () => selectTab(t.dataset.tab)));

  const TAB_LAUNCHERS = { journal: openJournal };
  document.querySelectorAll(".admin-tabs [data-launch]").forEach((t) =>
    t.addEventListener("click", () => TAB_LAUNCHERS[t.dataset.launch]?.()));

  /* ---------- Barre d'outils du plateau ---------- */
  // Recherche grep : estompe en direct les cartes hors correspondance (combiné aux vues).
  const boardFilter = document.getElementById("board-filter");
  boardFilter?.addEventListener("input", () => { state.boardQuery = boardFilter.value; applyView(); });

  // Bascule Blocs / Table.
  function setViewMode(mode) {
    document.querySelectorAll(".tb-seg .seg-btn").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.viewMode === mode)));
    document.getElementById("blocks-container").hidden = mode !== "blocs";
    const table = document.getElementById("blocks-table");
    table.hidden = mode !== "table";
    if (mode === "table") renderTable();
  }
  document.querySelectorAll(".tb-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => setViewMode(b.dataset.viewMode)));

  // Ajout de beltpack : UN seul bouton, au pied de la réserve (il arrive non affecté).
  document.getElementById("add-beltpack-pool")?.addEventListener("click", () => openPersonDialog(null, null));

  /* ---------- Horloge de l'en-tête ---------- */
  const clockEl = document.getElementById("admin-clock");
  function tickClock() {
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("fr-FR");
  }
  tickClock();
  setInterval(tickClock, 1000);

  /* ---------- Init ---------- */
  render();
  updateSelectionBar();
  refreshAntennaBadge();
  refreshStatus();            // résumé publié + afficheurs connectés (barre d'état)
  pollLive();                 // état initial ; les MAJ arrivent en push via le SSE `live`
  subscribeAdmin();
  renderStatusBar();          // chip d'état initiale (« À jour » / « N en attente »)
})();
