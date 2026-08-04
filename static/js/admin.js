/* ComRoster — Administration (édition du brouillon, branché sur l'API REST) */
(() => {
  // Optionnel chaîné : si le meta disparaissait, on n'arrête pas tout le script au
  // chargement (les requêtes échoueraient proprement côté serveur avec un CSRF vide).
  const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";
  // Logique pure sortie d'ici pour être testable sans navigateur (static/js/board.js,
  // static/js/netmask.js). Les allowlists n'ont plus de copie locale : elles vivaient en
  // trois exemplaires, entretenus par des commentaires « miroir de… ».
  const Board = window.ComRoster.Board;
  const Netmask = window.ComRoster.Netmask;
  const SKINS = Board.SKINS;
  const TEXT_SCALES = Board.TEXT_SCALES;
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
    tableSort: { key: "bp", dir: 1 },   // tri de la vue Table (re-clic = inverse)
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

  /* ---------- Confirmation dans l'interface ----------
     Remplace window.confirm (chrome système étranger à la DA). Boutons value=… d'un
     form method=dialog : le returnValue porte le choix, Échap vaut annulation. */
  function confirmDialog(text, { title = "Confirmer", okLabel = "Confirmer", danger = false } = {}) {
    const dlg = document.getElementById("confirm-dialog");
    document.getElementById("confirm-title").textContent = title;
    document.getElementById("confirm-text").textContent = text;
    const ok = document.getElementById("confirm-ok");
    ok.textContent = okLabel;
    ok.classList.toggle("confirm-danger", danger);
    dlg.returnValue = "";
    return new Promise((resolve) => {
      dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
      dlg.showModal();
    });
  }

  /* Ordre d'affichage des beltpacks — la règle vit dans board.js, partagée avec l'écran
     de régie : deux copies finiraient par montrer deux ordres différents à la salle et au
     régisseur, ce qui était exactement le cas avant ce lot. */
  const parNumero = window.ComRoster.Board.parNumero;
  const ordonnerMembres = window.ComRoster.Board.ordonnerMembres;

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

  /* Regroupement des écritures du brouillon. Chaque enregistrement est une écriture
     atomique fsyncée sur la CARTE SD du boîtier : à 500 ms, une saisie soutenue en
     produisait environ deux par seconde. 900 ms divise ce volume par deux sans que
     l'enregistrement cesse d'être perçu comme immédiat — et rien n'est jamais perdu, la
     publication vide d'abord la file (`savePending`). */
  const SAVE_DEBOUNCE_MS = 900;
  let saveTimer = null;
  let savePending = false;

  /* GÉNÉRATION DU BROUILLON — protège les remplacements EN BLOC des enregistrements
     différés encore en vol.

     Le scénario, observé au banc : on supprime un groupe (enregistrement programmé à
     900 ms), puis on restaure une sauvegarde. La restauration réécrit le brouillon côté
     serveur et `load()` le réaffiche… mais l'enregistrement différé, parti entre-temps
     avec l'ANCIEN contenu, revient après et réassigne `state.data` — le groupe restauré
     disparaît de l'écran ET du serveur, sans le moindre message. Même famille que le
     read-modify-write concurrent corrigé côté serveur le 2026-07-06 : l'atomicité d'une
     écriture ne dit rien de l'ordre de deux écritures.

     Toute reprise en bloc (restauration de sauvegarde, import, chargement de
     configuration, resynchro distante) incrémente le compteur ; une réponse
     d'enregistrement d'une génération périmée est ignorée. */
  let saveGeneration = 0;
  function cancelPendingSave() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    savePending = false;
    saveGeneration += 1;
    return saveGeneration;
  }

  function scheduleSave() {
    savePending = true;
    if (saveTimer) clearTimeout(saveTimer);
    setStatus("Enregistrement…", "syncing");
    saveTimer = setTimeout(saveDraft, SAVE_DEBOUNCE_MS);
  }

  async function saveDraft() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    savePending = false;
    const generation = saveGeneration;
    try {
      const saved = await apiSend("PUT", "/api/draft", state.data);
      // Un remplacement en bloc est survenu pendant l'aller-retour : cette réponse
      // décrit un état périmé, l'appliquer annulerait la reprise.
      if (generation !== saveGeneration) return;
      state.data = saved;
      setStatus("Brouillon enregistré", "idle");
      if (el.lastUpdated) el.lastUpdated.textContent =
        "Dernier enregistrement : " + new Date(saved.updated_at).toLocaleString("fr-FR");
      render();
      // L'aperçu de l'onglet Écran lit le brouillon CÔTÉ SERVEUR : on ne le rafraîchit
      // qu'une fois l'enregistrement confirmé, sinon il montrerait l'état d'avant.
      reloadScreenPreview();
    } catch (err) {
      if (generation !== saveGeneration) return;
      setStatus("Échec de l'enregistrement", "error");
      if (err.message === "beltpack_conflict") {
        toast("Deux beltpacks ont le même numéro. Corrigez avant d'enregistrer.", true);
      }
    }
  }

  /* ---------- Annulation ⌘Z / Ctrl+Z ----------
     PORTÉE : le brouillon seul — groupes, noms, numéros, affectations, réglages d'écran.
     Jamais la configuration du boîtier : réseau, IP, Wi-Fi, antenne et mot de passe ne
     transitent pas par `state.data` (endpoints distincts, écriture immédiate côté
     serveur). Ils sont donc hors d'atteinte PAR CONSTRUCTION, et non par une liste
     d'exclusions qu'il faudrait tenir à jour à chaque nouveau réglage.
     Annuler ne dépublie rien non plus : l'écran en salle ne bouge qu'à la publication.

     Mécanique : `snapshot` garde le brouillon tel qu'il était AVANT la modification en
     cours. markDirty() étant appelé APRÈS la mutation, c'est exactement ce qu'il faut
     empiler. Copie par JSON — `state.data` vient de l'API, donc du JSON pur. */
  const UNDO_MAX = 50;
  let undoStack = [];
  let redoStack = [];
  let snapshot = null;
  let lastPushAt = 0;
  function resetUndo() {
    undoStack = []; redoStack = [];
    snapshot = JSON.stringify(state.data);
  }
  function pushUndo(coalesce) {
    if (snapshot === null) { snapshot = JSON.stringify(state.data); return; }
    const now = Date.now();
    // Une saisie émet un `input` PAR CARACTÈRE : sans regroupement, effacer un mot
    // demanderait dix ⌘Z. On n'empile pas de nouveau dans le fil d'une frappe continue.
    if (!(coalesce && now - lastPushAt < 700)) {
      undoStack.push(snapshot);
      if (undoStack.length > UNDO_MAX) undoStack.shift();
      redoStack = [];                       // une nouvelle action clôt la branche défaite
    }
    lastPushAt = now;
    snapshot = JSON.stringify(state.data);
  }
  function markDirty(opts) { pushUndo(opts?.coalesce); setUnpublished(true); scheduleSave(); }

  // Restauration : passe par scheduleSave() et NON par markDirty(), sinon annuler
  // s'empilerait lui-même et l'on tournerait en rond.
  function applyHistoryState(json) {
    state.data = JSON.parse(json);
    snapshot = json;
    exitSelection();
    setUnpublished(true); scheduleSave(); render();
  }
  function undo() {
    if (!undoStack.length) { toast("Rien à annuler"); return; }
    redoStack.push(JSON.stringify(state.data));
    applyHistoryState(undoStack.pop());
    toast("Modification annulée");
  }
  function redo() {
    if (!redoStack.length) { toast("Rien à rétablir"); return; }
    undoStack.push(JSON.stringify(state.data));
    applyHistoryState(redoStack.pop());
    toast("Modification rétablie");
  }

  // Recharge l'état du brouillon depuis le serveur et ré-affiche.
  async function load() {
    // AVANT la requête : tout enregistrement programmé ou déjà en vol devient périmé.
    // Sans cela, une sauvegarde différée partie avec l'ancien contenu revient après le
    // rechargement et écrase ce qu'on vient de reprendre (cf. saveGeneration).
    cancelPendingSave();
    state.data = await apiSend("GET", "/api/state");
    // L'historique repart de zéro : le brouillon vient d'être REMPLACÉ en bloc (import,
    // restauration, resynchro d'une publication distante). Annuler par-dessus
    // ressusciterait un état antérieur à ce remplacement — y compris celui d'un autre
    // opérateur.
    resetUndo();
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
    // (setDragGhost est défini plus bas, au même niveau : la déclaration est hoistée.)
    card.classList.add("selectable");
    if (state.selection.has(person.id)) card.classList.add("selected");
    card.addEventListener("click", (e) => selectClick(e, person.id));
    card.addEventListener("dragstart", (e) => {
      card.classList.add("dragging");
      if (state.selection.has(person.id) && state.selection.size) {
        const ids = [...state.selection];
        state.drag = { multi: true, ids, source, blockId: blockId || null };
        if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", ids.join(",")); } catch (_) { /* IE */ } }
        // Le fantôme par défaut est la SEULE carte saisie : on croit ne déplacer qu'elle
        // alors que toute la sélection suit. Au-delà d'un beltpack, on montre le compte.
        if (ids.length > 1) setDragGhost(e, `${ids.length} beltpacks`);
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
    t.textContent = "ajouter un beltpack";
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
    const all = state.data.people.filter((p) => !p.group_id).sort(parNumero);
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
      const members = ordonnerMembres(
        state.data.people.filter((p) => p.group_id === block.id), block);
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
      // Double-clic = renommer, exactement comme sur le numéro ou le rôle d'un
      // beltpack. `stopPropagation` : sans lui le double-clic remonterait à la carte,
      // qui ouvre l'édition d'un membre. Le `h3` seul est la cible — pas le titleWrap,
      // qui est aussi la poignée de glisser-déposer du groupe.
      h3.title = "Double-cliquer pour renommer";
      h3.addEventListener("dblclick", (e) => {
        e.preventDefault(); e.stopPropagation(); renameBlock(block.id);
      });
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
      // « Trier par n° » n'apparaît que sur un groupe rangé à la main : ailleurs le tri
      // est déjà l'état courant, et le bouton ne ferait rien qu'on puisse constater.
      if (block.manual_order) {
        actions.append(chip("Trier par n°", () => {
          block.manual_order = false; markDirty(); render();
        }));
      }
      actions.append(
        chip("Renommer", () => renameBlock(block.id)),
        chip("Supprimer", () => deleteBlock(block.id), "danger"),
      );
      header.append(titleWrap, actions);

      const list = document.createElement("div");
      list.className = "block-items";
      list.dataset.blockId = block.id;
      /* Un dépôt est un RANGEMENT quand il porte sur un seul beltpack déjà membre du
         groupe, ou sur un groupe qu'on a déjà rangé à la main : là, la place visée compte.
         Amener un beltpack de la réserve dans un groupe trié n'est pas « toucher à
         l'ordre » — ça reste une simple affectation, et le tri par numéro doit survivre. */
      const rangement = (drag) => !!drag && !drag.multi
        && (block.manual_order || findPerson(drag.userId)?.group_id === block.id);
      list.addEventListener("dragover", (e) => {
        if (state.dragGroup) return;
        e.preventDefault(); list.dataset.dragover = "true";
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
        marquerInsertion(list, rangement(state.drag) ? indexInsertion(list, e.clientY) : -1);
      });
      list.addEventListener("dragleave", () => { delete list.dataset.dragover; marquerInsertion(list, -1); });
      list.addEventListener("drop", (e) => {
        e.preventDefault(); delete list.dataset.dragover; marquerInsertion(list, -1);
        if (!state.drag || state.dragGroup) return;
        if (rangement(state.drag)) reorderInto(state.drag.userId, block.id, indexInsertion(list, e.clientY));
        else if (state.drag.multi) assignMany(state.drag.ids, block.id);
        else assign(state.drag.userId, block.id);
      });

      members.forEach((p) => list.append(personCard(p, "block", block.id)));
      list.append(addTile(() => openPersonDialog(null, block.id)));   // case « + » du groupe
      wrap.append(header, list);
      el.blocks.append(wrap);
    });
    // Si la vue Table est active, la maintenir à jour avec les mêmes données.
    const table = document.getElementById("blocks-table");
    if (table && !table.hidden) renderTable();
  }

  /* Vue Table : tous les beltpacks à plat — un poste d'administration COMPLET, pas un
     tableau informatif : tri par colonne (re-clic = ordre inverse), sélection et clic
     droit comme la vue Blocs, double-clic sur n°/nom = édition sur place, et le groupe
     est un SÉLECTEUR à l'aplat du groupe : réaffecter se fait dans la rangée. */
  const cmpBp = (a, b) =>
    String(a.beltpack).localeCompare(String(b.beltpack), "fr", { numeric: true });
  function renderTable() {
    const host = document.getElementById("blocks-table");
    if (!host) return;
    const groups = [...state.data.groups].sort((a, b) => (a.order || 0) - (b.order || 0));
    const byId = new Map(groups.map((g) => [g.id, g]));
    const orderOf = new Map(groups.map((g, i) => [g.id, i]));
    const cmp = {
      bp: cmpBp,
      role: (a, b) => String(a.role || "").localeCompare(String(b.role || ""), "fr") || cmpBp(a, b),
      // Groupe : l'ordre du plateau (celui des blocs), réserve en queue, n° croissant dedans.
      group: (a, b) => {
        const ia = a.group_id ? (orderOf.get(a.group_id) ?? 1e8) : 1e9;
        const ib = b.group_id ? (orderOf.get(b.group_id) ?? 1e8) : 1e9;
        return (ia - ib) || cmpBp(a, b);
      },
    }[state.tableSort.key] || cmpBp;
    const rows = [...state.data.people].sort((a, b) => cmp(a, b) * state.tableSort.dir);

    host.innerHTML = "";
    const head = document.createElement("div");
    head.className = "bt-head";
    [["bp", "BP"], ["role", "Nom"], ["group", "Groupe"]].forEach(([k, label]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "bt-sort";
      b.textContent = label;
      if (k === state.tableSort.key) b.dataset.dir = state.tableSort.dir > 0 ? "asc" : "desc";
      b.addEventListener("click", () => {
        if (state.tableSort.key === k) state.tableSort.dir *= -1;
        else state.tableSort = { key: k, dir: 1 };
        renderTable();
      });
      head.append(b);
    });
    host.append(head);
    rows.forEach((p) => host.append(tableRow(p, byId, groups)));
  }

  function tableRow(p, byId, groups) {
    const g = byId.get(p.group_id);
    const row = document.createElement("div");
    row.className = "bt-row selectable";
    row.dataset.userId = p.id;
    row.dataset.bp = p.beltpack;                       // filtre/vues, comme les cartes
    if (p.group_id) row.dataset.blockId = p.group_id;
    if (state.selection.has(p.id)) row.classList.add("selected");

    const bp = document.createElement("span");
    bp.className = "bt-bp";
    bp.textContent = p.beltpack;
    bp.title = "Double-cliquez pour changer le numéro";
    bp.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); startInlineEdit(p, "beltpack", bp); });

    const role = document.createElement("span");
    role.className = "bt-role role";                   // .role : requis par le filtre texte
    role.textContent = p.role || "—";
    role.title = "Double-cliquez pour renommer";
    role.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); startInlineEdit(p, "role", role); });

    // Sélecteur de groupe à l'aplat du groupe : réaffectation sur place.
    const cell = document.createElement("span");
    cell.className = "bt-grp";
    const sel = document.createElement("select");
    sel.className = "bt-assign";
    sel.title = "Affecter à un groupe";
    const optNone = document.createElement("option");
    optNone.value = "";
    optNone.textContent = "— réserve —";
    sel.append(optNone);
    groups.forEach((grp) => {
      const o = document.createElement("option");
      o.value = grp.id;
      o.textContent = grp.name;
      sel.append(o);
    });
    sel.value = p.group_id || "";
    const gel = g ? sanitizeColor(g.color) : "";
    if (gel) {
      sel.style.background = gel;                      // CSSOM : la CSP interdit style=""
      const ink = window.ComRoster.inkFor(gel);        // même règle d'encre que l'écran
      if (ink) sel.dataset.ink = ink;
    }
    sel.addEventListener("click", (e) => e.stopPropagation());   // ne pas (dé)sélectionner
    // Si la rangée appartient à une sélection multiple, son sélecteur vaut pour TOUTE la
    // sélection — même règle que le glisser-déposer d'une sélection (cf. personCard).
    // Sans ça, sélectionner dix rangées puis choisir un groupe n'en déplaçait qu'une.
    sel.addEventListener("change", () => {
      const target = sel.value || null;
      if (state.selection.size > 1 && state.selection.has(p.id)) {
        const n = state.selection.size;
        assignMany([...state.selection], target);
        toast(`${n} beltpacks déplacés vers ${target ? groupNameOf(target) : "la réserve"}`);
      } else {
        assign(p.id, target);
      }
    });
    cell.append(sel);

    row.append(bp, role, cell);
    row.addEventListener("click", (e) => selectClick(e, p.id));
    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      state.context = { userId: p.id, blockId: p.group_id || null };
      el.contextMenu.style.display = "block";
      el.contextMenu.style.left = e.pageX + "px";
      el.contextMenu.style.top = e.pageY + "px";
    });
    return row;
  }

  /* Fantôme de glissement d'une sélection multiple : une pastille « N beltpacks ».
     Le navigateur PHOTOGRAPHIE l'élément au moment de setDragImage — il doit donc être
     dans le document et rendu (d'où le hors-champ plutôt que `display:none`), et ne peut
     être retiré qu'au tour de boucle suivant, une fois la capture faite. */
  function setDragGhost(e, label) {
    if (!e.dataTransfer?.setDragImage) return;
    const ghost = document.createElement("div");
    ghost.className = "drag-ghost";
    ghost.textContent = label;
    document.body.append(ghost);
    e.dataTransfer.setDragImage(ghost, 12, 12);
    setTimeout(() => ghost.remove(), 0);
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
      + `<a class="inv-item inv-add" data-add-group role="button" tabindex="0">`
      + `<i class="inv-dot"></i><span class="inv-label">+ Ajouter un groupe</span></a>`
      + liveRows;
    host.querySelectorAll(".inv-dot[data-color]").forEach((i) => { i.style.background = i.dataset.color; });
    const addRow = host.querySelector("[data-add-group]");
    addRow.addEventListener("click", openCreateBlock);
    addRow.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCreateBlock(); } });
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
    // Cartes de la vue Blocs ET rangées de la vue Table : même filtre, mêmes vues.
    document.querySelectorAll(".person[data-bp], .bt-row[data-bp]").forEach((card) => {
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
  /* Ranger un beltpack À UNE PLACE PRÉCISE dans un groupe.
     Ce geste fait basculer le groupe en ordre manuel : c'est le « on touche à l'ordre »
     de la règle. L'ordre AFFICHÉ au moment du dépôt devient l'ordre enregistré, sans quoi
     le premier rangement à la main réarrangerait tout le reste du groupe sous les yeux
     de l'utilisateur.

     Le tableau `people` est la seule donnée d'ordre : on y remet les membres du groupe
     dans leur nouvel ordre. Les déplacer en fin de tableau est sans effet visible — chaque
     groupe est lu par filtrage, et la réserve est triée par numéro — mais évite d'avoir à
     réinsérer au bon endroit un bloc de lignes entrelacées avec d'autres groupes. */
  function reorderInto(personId, groupId, index) {
    const block = findBlock(groupId);
    const perso = findPerson(personId);
    if (!block || !perso) return;
    const membres = ordonnerMembres(
      state.data.people.filter((p) => p.group_id === groupId && p.id !== personId), block);
    const cible = Math.max(0, Math.min(index, membres.length));
    membres.splice(cible, 0, perso);
    perso.group_id = groupId;
    const dansLeGroupe = new Set(membres.map((p) => p.id));
    state.data.people = state.data.people.filter((p) => !dansLeGroupe.has(p.id)).concat(membres);
    block.manual_order = true;
    markDirty(); render();
  }

  /* Trait d'insertion : sans lui on dépose à l'aveugle, et un rangement à la main dont on
     ne voit pas la cible se retente jusqu'à tomber juste. `index === -1` efface le trait.
     Posé sur la carte visée (ou la dernière, par en dessous) plutôt que sur un élément
     ajouté : rien à retirer du DOM, donc rien à oublier d'y retirer. */
  function marquerInsertion(list, index) {
    const cartes = [...list.querySelectorAll(".person")];
    cartes.forEach((c) => { delete c.dataset.insertBefore; delete c.dataset.insertAfter; });
    if (index < 0) return;
    if (index < cartes.length) cartes[index].dataset.insertBefore = "true";
    else if (cartes.length) cartes[cartes.length - 1].dataset.insertAfter = "true";
  }

  /* Place d'insertion visée par le curseur : le nombre de cartes dont la MOITIÉ est
     au-dessus de lui. Comparer au milieu et non au bord donne le comportement attendu
     (déposer sur la moitié haute d'une carte insère avant elle). */
  function indexInsertion(list, clientY) {
    const cartes = [...list.querySelectorAll(".person")];
    return cartes.filter((c) => {
      const r = c.getBoundingClientRect();
      return clientY > r.top + r.height / 2;
    }).length;
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
  // Geste de sélection partagé entre les vues Blocs (cartes) et Table (rangées).
  function selectClick(e, personId) {
    if (e.shiftKey && state.lastSelectedId) {
      selectRange(state.lastSelectedId, personId);
    } else if (state.selection.has(personId)) {
      state.selection.delete(personId);
    } else {
      state.selection.add(personId);
    }
    state.lastSelectedId = personId;
    refreshSelectionClasses();
    updateSelectionBar();
  }
  /* Nœuds sélectionnables de la vue ACTIVE, dans l'ordre où l'utilisateur les voit.
     Piège corrigé ici : la vue Blocs n'est pas démontée quand on passe en Tableau, elle
     est seulement `hidden`. Un `querySelectorAll` global voyait donc CHAQUE personne
     deux fois — une carte cachée + une rangée visible — et dans l'ordre des blocs, pas
     celui du tableau trié. MAJ+clic balayait alors une plage qui n'avait aucun rapport
     avec ce qui est à l'écran (la sélection « sautait »).
     Les rangées estompées par un filtre ou une vue sont exclues : elles ne sont pas
     cliquables (`pointer-events: none`), les balayer sélectionnait de l'invisible. */
  function selectableNodes() {
    const table = document.getElementById("blocks-table");
    const scope = table && !table.hidden
      ? [...table.querySelectorAll(".bt-row[data-user-id]")]
      : [...document.querySelectorAll("#blocks-container .person[data-user-id], #available-users .person[data-user-id]")];
    return scope.filter((n) => !n.classList.contains("view-dim"));
  }
  // ⌘A : tout ce qui est sélectionnable DANS LA VUE ACTIVE — donc affectés + réserve en
  // vue Blocs, toutes les rangées en vue Tableau. Un filtre ou une vue en cours restreint
  // naturellement la portée : `selectableNodes` écarte l'estompé, qui n'est pas cliquable.
  function selectAll() {
    const nodes = selectableNodes();
    if (!nodes.length) return;
    nodes.forEach((n) => state.selection.add(n.dataset.userId));
    state.lastSelectedId = nodes[nodes.length - 1].dataset.userId;
    refreshSelectionClasses();
    updateSelectionBar();
  }
  function selectRange(fromId, toId) {
    // L'ordre visuel vient de selectableNodes() (vue active seule) ; le balayage lui-même
    // est pur et testé sans navigateur (Board.rangeIds).
    const ids = selectableNodes().map((c) => c.dataset.userId);
    const swept = Board.rangeIds(ids, fromId, toId);
    if (!swept.length) { state.selection.add(toId); return; }
    swept.forEach((id) => state.selection.add(id));
  }
  // Reflète la sélection sans reconstruire le DOM (sinon le double-clic est cassé).
  function refreshSelectionClasses() {
    document.querySelectorAll(".person[data-user-id], .bt-row[data-user-id]").forEach((c) => {
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
  async function deleteBlock(id) {
    const b = findBlock(id);
    if (!await confirmDialog(`Supprimer le groupe « ${b.name} » ? Ses beltpacks retournent en réserve.`,
                             { title: "Supprimer le groupe", okLabel: "Supprimer", danger: true })) return;
    state.data.people.forEach((p) => { if (p.group_id === id) p.group_id = null; });
    state.data.groups = state.data.groups.filter((g) => g.id !== id);
    markDirty(); render();
  }

  /* ---------- Color picker ---------- */
  /* Palette bornée des couleurs de groupe. Chaque teinte est calibrée pour donner un
     contraste ≥ 4.5:1 (WCAG AA) avec l'encre calculée par inkFor(), dans les DEUX modes de
     luminosité — c'est ce que le sélecteur natif ne garantissait pas (d'où le rouge
     #C4544A retenu au banc, illisible à 4.2:1 sur son aplat). Deux rangées vives à encre
     sombre, une pastel, une profonde à encre claire — 24 teintes, toutes vérifiées par
     calcul avant admission (jamais à l'œil). */
  /* ORDRE : par famille de teinte (rouge → orange → jaune → vert → turquoise → bleu →
     violet → magenta), et du plus clair au plus sombre dans chaque famille ; les
     neutres, qui n'ont pas de teinte, ferment la marche. Les VALEURS sont inchangées —
     seul leur rang bouge, donc les contrastes validés le restent par construction.
     Un tri sur la teinte seule faisait sauter la luminosité d'une case à l'autre ; le
     regroupement par famille donne une rampe qui se lit d'un coup d'œil. */
  const GROUP_PALETTE = [
    "#C77E6A", "#E1554C", "#9B2F2F", "#F4A259", "#E8863B", "#7A5230",
    "#E4B93C", "#C9A227", "#8FBF52", "#6B8E23", "#2E6B34", "#7FC8D6",
    "#3FA6B0", "#2A6E60", "#5C6BC0", "#4F86C6", "#2C4C8E", "#8B7CC8",
    "#6A4FA3", "#D98CB3", "#C062A6", "#8E3B6B", "#B0B7C0", "#55606E",
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
    const role = el.personRole.value.trim();
    const groupId = el.personAssign.value || null;
    if (beltpackTaken(beltpack, state.editingPersonId)) {
      const holder = state.data.people.find(
        (p) => p.id !== state.editingPersonId && normBp(p.beltpack) === beltpack);
      // Reprise depuis la réserve : « déposer le n°22 » dans un groupe alors que le 22
      // ATTEND en réserve n'est pas un conflit, c'est l'affectation qu'on cherchait —
      // on le reprend (et on retire le doublon de saisie). Uniquement en CRÉATION vers
      // un groupe : un beltpack déjà affecté AILLEURS ne bouge jamais silencieusement.
      if (!state.editingPersonId && holder && !holder.group_id && groupId) {
        if (role) holder.role = role;         // nom retapé → mis à jour ; vide → conservé
        holder.group_id = groupId;
        el.personDialog.close();
        toast(`N°${beltpack} repris de la réserve → « ${groupNameOf(groupId)} ».`);
        markDirty(); render();
        return;
      }
      // Dire OÙ il est : « déjà utilisé » seul oblige à chercher dans tous les groupes.
      const where = holder?.group_id
        ? `dans « ${groupNameOf(holder.group_id)} »` : "dans la réserve";
      toast(`Le n°${beltpack} existe déjà ${where}.`, true);
      el.personBeltpack.focus();
      return;
    }

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
    setVal("meta-production", d.production_name || "");
    setVal("meta-title", d.title || "");
    setVal("meta-subtitle", d.subtitle || "");
    setVal("meta-columns", String(d.columns || 0));
    setVal("meta-text-scale", TEXT_SCALES.includes(d.text_scale) ? d.text_scale : "original");
    setVal("theme-select", d.theme === "day" ? "day" : "night");
    setVal("skin-select", SKINS.includes(d.skin) ? d.skin : "basique");
    const ind = d.indicators || DEFAULT_IND;
    setChk("ind-online", ind.online !== false);
    setChk("ind-battery", ind.battery !== false);
    setChk("meta-perf", d.perf === true);
  }
  function bindSettings() {
    const production = document.getElementById("meta-production");
    production.addEventListener("input", () => {
      state.data.production_name = production.value;   // titre centré de l'écran
      markDirty({ coalesce: true });
    });
    const title = document.getElementById("meta-title");
    title.addEventListener("input", () => {
      state.data.title = title.value;
      el.title.textContent = title.value.trim() || "Affectation Intercom";
      document.title = "Administration · " + (title.value.trim() || "ComRoster");
      markDirty({ coalesce: true });
    });
    const sub = document.getElementById("meta-subtitle");
    const crumbSep = document.getElementById("crumb-sep");
    sub.addEventListener("input", () => {
      state.data.subtitle = sub.value;
      const has = !!sub.value.trim();
      if (has) { el.subtitle.textContent = sub.value.trim(); }
      el.subtitle.hidden = !has;
      if (crumbSep) crumbSep.hidden = !has;   // le « / » ne s'affiche qu'avec un sous-titre
      markDirty({ coalesce: true });
    });
    document.getElementById("meta-columns").addEventListener("change", (e) => {
      state.data.columns = parseInt(e.target.value, 10) || 0; markDirty();
    });
    document.getElementById("meta-text-scale").addEventListener("change", (e) => {
      state.data.text_scale = TEXT_SCALES.includes(e.target.value) ? e.target.value : "original";
      markDirty();
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

  /* ---------- Publication : garde-fou de 5 s annulable, INTÉGRÉ AU BOUTON ----------
     Cliquer « Publier » ne publie pas tout de suite : le bouton se remplit d'une
     progression sur 5 s et devient « Annuler la publication » (re-clic = annuler), comme
     l'« annuler l'envoi » d'un mail. ⌘↵ pendant le décompte envoie tout de suite. */
  const PUBLISH_DELAY = 5000;
  const PUB_IDLE = "Publier";
  // « Annuler » et non « Annuler la publication » : ce libellé est le PLUS LONG des trois,
  // donc c'est lui qui fixait la largeur du bouton (184 px) — et cette largeur était payée
  // EN PERMANENCE, laissant 48 px de vide autour du mot « Publier » au repos. C'est le même
  // arbitrage qu'en juillet pour la chip d'état (ne pas réserver la place d'un état rare),
  // qui n'avait alors été appliqué qu'à elle. Le mot suffit : le bouton se remplit d'une
  // progression et affiche le décompte, le contexte est donné par ce qui bouge.
  const PUB_ARM = (n) => `Annuler · ${n}`;
  const PUB_DONE = "Publié ✓";
  const pubLabel = () => document.getElementById("pub-label");
  const pubFill = () => document.getElementById("pub-fill");
  let publishTimer = null, publishTick = null;

  // Largeurs figées sur le PLUS LONG état (mesuré) : les libellés changent sans décaler
  // l'en-tête (le bouton ET la chip d'état varient au fil de la publication). Appelé à
  // l'init, puis à nouveau une fois les polices prêtes.
  function fixWidthToLongest(el2, texts, apply) {
    el2.style.minWidth = "";                     // repart de la largeur naturelle (re-mesure)
    let max = 0;
    const restore = apply(null, true);           // sauvegarde l'état courant
    texts.forEach((t) => { apply(t); max = Math.max(max, el2.scrollWidth); });
    restore();
    el2.style.minWidth = Math.ceil(max) + "px";
  }
  function lockHeaderWidths() {
    const btn = el.publishBtn, label = pubLabel(), kbd = btn.querySelector("kbd");
    fixWidthToLongest(btn, [PUB_IDLE, PUB_ARM(5), PUB_DONE], (t, save) => {
      if (save) { const s = label.textContent, k = kbd.style.display; return () => { label.textContent = s; kbd.style.display = k; }; }
      label.textContent = t; kbd.style.display = t === PUB_IDLE ? "" : "none";   // ⌘↵ visible au repos seul
    });
    // Chip d'état : figée sur son libellé le plus long → l'horloge ne saute plus.
    // La liste ne retient que les états NOMINAUX : la figer aussi sur « Échec de
    // l'enregistrement » réservait en permanence la largeur d'un cas exceptionnel, ce qui
    // éloignait le menu de « Publier ». Un échec élargit donc la chip d'un cran — c'est
    // rare, et le sursaut attire justement l'œil dessus.
    if (el.syncStatus && el.syncLabel) {
      fixWidthToLongest(el.syncStatus,
        ["À jour", "88 en attente", "Enregistrement…"],
        (t, save) => { if (save) { const s = el.syncLabel.textContent; return () => { el.syncLabel.textContent = s; }; } el.syncLabel.textContent = t; });
    }
  }

  function armPublish() {
    if (state.busy || publishTimer) return;
    const btn = el.publishBtn, fill = pubFill(), label = pubLabel();
    const start = Date.now();
    btn.classList.add("arming");
    fill.style.transition = "none"; fill.style.width = "0%";
    requestAnimationFrame(() => { fill.style.transition = `width ${PUBLISH_DELAY}ms linear`; fill.style.width = "100%"; });
    const render = () => {
      const left = Math.max(0, Math.ceil((PUBLISH_DELAY - (Date.now() - start)) / 1000));
      label.textContent = PUB_ARM(left);
    };
    render();
    publishTick = setInterval(render, 200);
    publishTimer = setTimeout(() => { endCountdown(); publish(); }, PUBLISH_DELAY);
  }
  function endCountdown() {
    if (publishTimer) { clearTimeout(publishTimer); publishTimer = null; }
    if (publishTick) { clearInterval(publishTick); publishTick = null; }
    el.publishBtn.classList.remove("arming");
    const fill = pubFill();
    fill.style.transition = "none"; fill.style.width = "0%";
    pubLabel().textContent = PUB_IDLE;
  }
  function cancelPublish() {
    if (!publishTimer) return;
    endCountdown();
    toast("Publication annulée");
  }
  function sendNow() { if (publishTimer) { endCountdown(); publish(); } }
  // Confirmation : bref balayage vert + « Publié ✓ », au niveau du bouton.
  function flashSent() {
    const btn = el.publishBtn, fill = pubFill(), label = pubLabel();
    btn.classList.add("sent");
    label.textContent = PUB_DONE;
    fill.style.transition = "none"; fill.style.width = "0%";
    requestAnimationFrame(() => { fill.style.transition = "width 0.4s ease"; fill.style.width = "100%"; });
    setTimeout(() => {
      if (publishTimer) return;              // un nouveau décompte a repris la main
      btn.classList.remove("sent");
      fill.style.transition = "width 0.3s ease"; fill.style.width = "0%";
      label.textContent = PUB_IDLE;
    }, 1300);
  }
  // Clic sur le bouton : armer, ou annuler s'il est déjà armé (il affiche « Annuler · N »).
  function publishButtonClick() { if (publishTimer) cancelPublish(); else armPublish(); }
  // Raccourci ⌘↵ : armer, ou envoyer tout de suite si déjà armé.
  function publishShortcut() { if (publishTimer) sendNow(); else armPublish(); }

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
      flashSent();                     // confirmation « envoyé » discrète, au niveau du bouton
    } catch (err) {
      if (err.message === "beltpack_conflict") toast("Beltpack en double : impossible de publier.", true);
      else toast("Échec de la publication.", true);
      setStatus("Échec de la publication", "error");
    } finally {
      state.busy = false;
      el.publishBtn.disabled = false;
    }
  }

  /* ---------- Export / Import ----------
     Deux sources possibles pour un même fichier : le plateau À L'ÉCRAN (modifications
     non enregistrées comprises) et une configuration SUR LE DISQUE, relue par l'API.
     La fabrication du fichier, elle, est identique — d'où une seule fonction. */
  function downloadRost(data, nom) {
    // Fichier de configuration ComRoster — extension .rost (contenu JSON).
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `comroster-${nom}.rost`;
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
  }
  const exportConfig = () => downloadRost(state.data, Date.now());
  /* Reconstruction du brouillon depuis un fichier importé.

     On NE RÉÉNUMÈRE PLUS les champs à la main. L'ancienne version listait les clés une à
     une, et deux champs ajoutés après coup — `production_name` et `text_scale` — n'y
     avaient jamais été reportés : importer un fichier exporté la minute d'avant effaçait
     silencieusement le nom de la production et la taille du texte. Le piège avait déjà
     été relevé pour `skin` (« ⚠️ sinon perdu ») et il a resservi deux fois.

     Le remède est structurel : `board.js` détient LA liste des champs du brouillon, et le
     serveur la revalide de toute façon (`build_draft`). Ajouter un champ au modèle ne
     demande plus de penser à ce chemin-ci. */
  function importConfig(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (ev) => {
      let json;
      try {
        json = JSON.parse(ev.target.result);
      } catch { toast("Fichier illisible : ce n'est pas du JSON.", true); return; }
      if (!json || typeof json !== "object" || Array.isArray(json)) {
        toast("Fichier invalide : structure inattendue.", true); return;
      }
      /* La confirmation ne peut venir qu'ICI : le sélecteur de fichiers du système
         s'ouvre en premier, et faire confirmer un fichier illisible n'apporterait rien.
         Elle existe parce que l'import remplace TOUT le plateau — le voisin de dialogue
         (« Charger ») demande la même chose pour le même geste. */
      if (!await confirmDialog(
        `Remplacer le plateau actuel par « ${file.name} » ? Le travail en cours sera perdu.`,
        { title: "Importer un fichier", okLabel: "Remplacer" })) return;
      state.data = Board.draftFromImport(json);
      markDirty(); render();
      document.getElementById("configs-dialog").close();
      toast("Plateau importé");
    };
    reader.onerror = () => toast("Lecture du fichier impossible.", true);
    reader.readAsText(file);
    // Vidé tout de suite : sans ça, réimporter LE MÊME fichier n'émettrait pas de
    // « change ». La lecture est déjà lancée sur l'objet File, elle ne s'en trouve pas
    // interrompue.
    e.target.value = "";
  }

  /* ---------- Historique des publications ---------- */
  /* Historique : chaque publication peut recevoir un NOM et être ÉPINGLÉE.
     Une équipe ne pense pas ses publications en horodatages mais en « Filage »,
     « Générale », « Première » — une liste de dates n'est navigable que si l'on se
     souvient de l'heure qu'il était, ce qui n'arrive jamais. L'épingle met le repère à
     l'abri de la purge : sans elle, la configuration de la première ne survit pas à
     trente jours de filages. */
  async function refreshHistory() {
    let items = [];
    try { items = await apiSend("GET", "/api/history"); } catch { toast("Historique indisponible.", true); return; }
    const list = document.getElementById("history-list");
    list.innerHTML = items.length
      ? items.map((i) => `<li class="hi-row${i.pinned ? " pinned" : ""}">`
          + `<button type="button" class="hi-pin" data-pin="${i.timestamp}" aria-pressed="${i.pinned}"`
          + ` title="${i.pinned ? "Ne plus conserver indéfiniment" : "Conserver indéfiniment (à l'abri de la purge)"}">`
          + `<span aria-hidden="true">${i.pinned ? "★" : "☆"}</span></button>`
          + `<span class="hi-when">${esc(i.datetime)}</span>`
          + `<span class="hi-label${i.label ? "" : " empty"}" data-label="${i.timestamp}"`
          + ` role="button" tabindex="0" title="Cliquer pour nommer ce repère">`
          + `${esc(i.label || "nommer…")}</span>`
          + `<button type="button" class="hi-restore" data-restore="${i.timestamp}">Restaurer</button></li>`).join("")
      : "<li class='empty-hint'>Aucune publication enregistrée.</li>";

    list.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", async () => {
      const on = b.getAttribute("aria-pressed") !== "true";
      try { await apiSend("POST", `/api/history/${b.dataset.pin}/label`, { pinned: on }); }
      catch (e) { toast(e.payload?.error || "Épinglage impossible", true); return; }
      await refreshHistory();
    }));
    list.querySelectorAll("[data-label]").forEach((el) => {
      const rename = () => startHistoryRename(el);
      el.addEventListener("click", rename);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); rename(); } });
    });
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
  /* Renommage sur place, comme le double-clic d'un beltpack : ouvrir un dialogue
     par-dessus un dialogue pour trois mots serait disproportionné. */
  function startHistoryRename(el) {
    if (el.querySelector("input")) return;
    const ts = el.dataset.label;
    const actuel = el.classList.contains("empty") ? "" : el.textContent.trim();
    const input = document.createElement("input");
    input.className = "inline-edit";
    input.value = actuel;
    input.maxLength = 60;
    input.placeholder = "Filage, Générale, Première…";
    el.textContent = "";
    el.append(input);
    input.focus(); input.select();
    let done = false;
    const commit = async () => {
      if (done) return; done = true;
      const v = input.value.trim();
      if (v === actuel) { await refreshHistory(); return; }
      try { await apiSend("POST", `/api/history/${ts}/label`, { label: v }); }
      catch (e) { toast(e.payload?.error || "Renommage impossible", true); }
      await refreshHistory();
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();          // ⌘Z / Échap gardent leur sens NATIF dans un champ
      if (e.key === "Enter") { e.preventDefault(); commit(); }
      else if (e.key === "Escape") { e.preventDefault(); done = true; refreshHistory(); }
    });
    requestAnimationFrame(() => input.addEventListener("blur", commit));
    input.addEventListener("click", (e) => e.stopPropagation());
  }

  async function openHistory() {
    await refreshHistory();
    document.getElementById("history-dialog").showModal();
  }
  async function clearHistory() {
    if (!await confirmDialog("Supprimer toutes les publications passées ? Action irréversible.",
                             { title: "Vider les publications", okLabel: "Tout supprimer", danger: true })) return;
    try { await apiSend("POST", "/api/history/clear"); await refreshHistory(); toast("Historique supprimé"); }
    catch { toast("Suppression impossible.", true); }
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
    else if (action === "delete") {
      confirmDialog("Supprimer ce beltpack ?", { okLabel: "Supprimer", danger: true })
        .then((ok) => { if (ok) deletePerson(userId); });
    }
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
  el.publishBtn.addEventListener("click", publishButtonClick);
  document.getElementById("export-btn").addEventListener("click", exportConfig);
  // Le bouton porte l'apparence, l'input porte la capacité : lui seul peut ouvrir le
  // sélecteur de fichiers, mais un <input type=file> ne se style pas comme un bouton.
  document.getElementById("import-btn").addEventListener("click", () => el.importInput.click());
  el.importInput.addEventListener("change", importConfig);
  document.getElementById("history-btn").addEventListener("click", openHistory);
  document.getElementById("history-clear").addEventListener("click", clearHistory);
  document.getElementById("history-close").addEventListener("click", () => document.getElementById("history-dialog").close());
  document.querySelectorAll("button[data-close]").forEach((b) =>
    b.addEventListener("click", () => document.getElementById(b.dataset.close)?.close()));
  // ---------- Menu « Réglages » (fonctions du boîtier) ----------
  // Ce n'est PAS un <dialog> : il ne prend pas le focus à l'ouverture et ne bloque pas
  // la page. Déclaré AVANT le handler clavier global, qui s'en sert dès la ligne suivante.
  const settingsBtn = document.getElementById("settings-btn");
  const settingsMenu = document.getElementById("settings-menu");
  const settingsOpen = () => !settingsMenu.hidden;
  function setSettings(open) {
    settingsMenu.hidden = !open;
    settingsBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  function closeSettings({ focus = false } = {}) {
    if (!settingsOpen()) return false;
    setSettings(false);
    if (focus) settingsBtn.focus();
    return true;
  }
  settingsBtn.addEventListener("click", (ev) => {
    // Sans stopPropagation, l'écouteur « clic extérieur » ci-dessous refermerait
    // aussitôt ce que ce clic vient d'ouvrir.
    ev.stopPropagation();
    setSettings(!settingsOpen());
  });
  // Choisir un item referme : les trois dialogues laisseraient sinon le menu ouvert
  // DERRIÈRE eux, et les deux liens quittent la page de toute façon.
  settingsMenu.addEventListener("click", (ev) => {
    if (ev.target.closest(".menu-item")) closeSettings();
  });
  document.addEventListener("click", (ev) => {
    if (settingsOpen() && !ev.target.closest(".tab-menu")) closeSettings();
  });
  // ↓ depuis le déclencheur ouvre et entre dans le menu ; Entrée et Espace n'ont besoin
  // de rien, ce sont des <button> et des <a> — le navigateur les active nativement.
  settingsBtn.addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown") return;
    ev.preventDefault();
    setSettings(true);
    settingsMenu.querySelector(".menu-item")?.focus();
  });
  settingsMenu.addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    ev.preventDefault();
    const items = [...settingsMenu.querySelectorAll(".menu-item")];
    const i = items.indexOf(document.activeElement);
    const suivant = (ev.key === "ArrowDown" ? i + 1 : i - 1 + items.length) % items.length;
    items[suivant].focus();
  });

  window.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    const tag = document.activeElement?.tagName || "";
    // « Sur le plateau » = ni dans un champ de saisie, ni dans un dialogue. Les raccourcis
    // qui EXISTENT AUSSI nativement (⌘Z, ⌘A) ne s'appliquent que là : ailleurs, défaire
    // une frappe ou sélectionner du texte doit rester le comportement du navigateur.
    // Un menu ouvert compte comme « pas sur le plateau » : la condition vit ICI, dans le
    // seul prédicat partagé, jamais recopiée dans les branches — une liste d'exclusions
    // dupliquée se périme au premier raccourci ajouté (leçon 2026-07-27).
    const onBoard = !/INPUT|TEXTAREA|SELECT/.test(tag) && !document.querySelector("dialog[open]")
      && !settingsOpen();
    // Échap pendant le décompte = annuler l'envoi. Il PRIME sur la sortie de sélection :
    // une publication en cours est l'action la plus conséquente à pouvoir rattraper.
    if (e.key === "Escape" && publishTimer) { e.preventDefault(); cancelPublish(); return; }
    // Échap ferme le menu « Réglages ». Le rang QUI COMPTE est celui-ci : APRÈS le décompte
    // de publication, qui reste l'action la plus conséquente à pouvoir rattraper (rang
    // décidé le 2026-07-27) et qui, lui, ne dépend pas d'`onBoard`. Face à la sortie de
    // sélection en dessous, l'ordre est redondant — `onBoard` exclut déjà le menu ouvert,
    // donc la sélection survit de toute façon ; on garde cet ordre pour la lecture.
    if (e.key === "Escape" && closeSettings({ focus: true })) { e.preventDefault(); return; }
    // Échap = quitter la sélection multiple (le bouton « Annuler » de la barre reste,
    // mais le réflexe clavier ne doit pas obliger à viser à la souris).
    if (e.key === "Escape" && state.selection.size && onBoard) { e.preventDefault(); exitSelection(); return; }
    // ⌘Z = annuler la dernière modification du brouillon, ⌘⇧Z = rétablir.
    if (mod && e.key.toLowerCase() === "z" && onBoard) {
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
      return;
    }
    // ⌘A = sélectionner tous les beltpacks de la vue active.
    if (mod && e.key.toLowerCase() === "a" && onBoard) { e.preventDefault(); selectAll(); return; }
    // ⌘/Ctrl+Entrée = publier (⌘↵ affiché). ⌘S accepté (réflexe « enregistrer »).
    // Passe par le garde-fou : arme le décompte, ou envoie tout de suite s'il est déjà armé.
    if (mod && (e.key === "Enter" || e.key.toLowerCase() === "s")) { e.preventDefault(); publishShortcut(); return; }
    // ⌘K = recherche de la réserve (affiché sur son champ).
    if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); document.getElementById("available-filter")?.focus(); return; }
    // « / » = filtre du plateau (affiché sur son champ) — hors saisie et hors dialogue.
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !document.querySelector("dialog[open]")) {
      e.preventDefault();
      document.getElementById("board-filter")?.focus();
    }
  });

  /* ---------- Antenne : pastille, assistant, tableau de bord ---------- */
  const antennaDialog = document.getElementById("antenna-dialog");
  let currentRanges = [];
  let rangesListEl = null;

  function summaryHtml(p) {
    return [
      `<li><b>${p.new.length}</b> à ajouter${p.new.length ? " : " + p.new.map((n) => esc(`#${n.number} ${n.name}`)).join(", ") : ""}</li>`,
      `<li><b>${p.changed.length}</b> nom(s) mis à jour${p.changed.length ? " : " + p.changed.map((c) => esc(`#${c.number} ${c.old_role}→${c.new_role}`)).join(", ") : ""}</li>`,
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

  /* ---------- Portée de l'import : Tous (plages vides) ↔ Certains numéros ----------
     Le même contrôle sert l'assistant et le tableau de bord. `onRangesChanged` permet à
     l'assistant de rafraîchir son aperçu en direct pendant qu'on édite les numéros. */
  let onRangesChanged = null;
  let activeScopeEl = null, activeWrapEl = null;

  function reflectScope() {
    if (!activeScopeEl) return;
    const some = currentRanges.length > 0;
    activeScopeEl.querySelector('[data-scope="all"]').setAttribute("aria-pressed", String(!some));
    activeScopeEl.querySelector('[data-scope="some"]').setAttribute("aria-pressed", String(some));
    activeWrapEl.hidden = !some;
  }
  // Monte le bloc portée du contexte visible (assistant OU tableau de bord).
  function showScope(scopeId, wrapId, listId) {
    activeScopeEl = document.getElementById(scopeId);
    activeWrapEl = document.getElementById(wrapId);
    rangesListEl = document.getElementById(listId);
    reflectScope();
    renderRanges();
  }
  function wireScope(scopeId) {
    document.getElementById(scopeId).addEventListener("click", (e) => {
      const b = e.target.closest("button[data-scope]");
      if (!b) return;
      if (b.dataset.scope === "all") currentRanges = [];
      else if (!currentRanges.length) currentRanges = [[1, 25]];   // amorce une plage
      reflectScope();
      renderRanges();
      saveRanges();
    });
  }
  wireScope("wiz-scope");
  wireScope("dash-scope");

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
      del.addEventListener("click", () => {
        currentRanges.splice(i, 1);
        reflectScope();               // dernière plage retirée → repasse à « Tous »
        renderRanges();
        saveRanges();
      });
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
    try {
      await apiSend("PUT", "/api/settings", { antenna_ranges: clean });
      if (onRangesChanged) onRangesChanged();     // aperçu live de l'assistant
    } catch { toast("Plages invalides", true); }
  }
  function addRange() { currentRanges.push([1, 25]); renderRanges(); saveRanges(); }
  document.getElementById("wiz-add-range").addEventListener("click", addRange);
  document.getElementById("dash-add-range").addEventListener("click", addRange);

  // Aperçu live de ce que l'import va faire (assistant, étape 2).
  async function refreshWizPreview() {
    const box = document.getElementById("wiz-summary");
    box.innerHTML = "<li class='import-note'>Lecture des beltpacks du réseau intercom…</li>";
    try { box.innerHTML = summaryHtml(await apiSend("POST", "/api/antenna/import/preview")); }
    catch { box.innerHTML = "<li class='import-note'>Lecture impossible pour l'instant.</li>"; }
  }

  function wizGo(step) {
    antennaDialog.querySelectorAll(".wiz-step").forEach((s) => { s.hidden = +s.dataset.step !== step; });
    if (step === 2) {
      showScope("wiz-scope", "wiz-ranges-wrap", "wiz-ranges-list");
      onRangesChanged = refreshWizPreview;   // ré-aperçu à chaque changement de portée
      refreshWizPreview();
    } else {
      onRangesChanged = null;
    }
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
      // Bloc structuré (comme l'état réseau) : une ligne par info, valeur alignée à droite.
      const rows = [
        ["Nom", name],
        ["Adresse", st.ip],
        online ? ["Firmware", fw] : null,
        online && nbp ? ["Beltpacks", `${nbp} sur le réseau`] : null,
      ].filter(Boolean);
      document.getElementById("dash-state").innerHTML =
        `<div class="ds-line"><span class="dot ${online ? "online" : "offline"}"></span>`
        + `<b>${online ? "Connecté" : "Hors ligne"}</b></div>`
        + rows.map(([k, v]) => `<div class="ds-row"><span class="ds-key">${esc(k)}</span><span class="ds-val">${esc(v)}</span></div>`).join("");
      document.getElementById("dash-reconnect-btn").hidden = online;
      document.getElementById("dash-refresh-btn").hidden = !online;
      onRangesChanged = null;                 // le tableau de bord n'a pas d'aperçu live
      showScope("dash-scope", "dash-ranges-wrap", "dash-ranges-list");
    } else {
      document.getElementById("antenna-dashboard").hidden = true;
      document.getElementById("antenna-wizard").hidden = false;
      document.getElementById("wiz-ip").value = "";
      document.getElementById("wiz-password").value = "";
      document.getElementById("wiz-error").hidden = true;
      wizGo(1);
      // Boîtier jamais apparié : on cherche d'emblée. C'est le moment où la question
      // « quelle est l'adresse de l'antenne ? » se pose vraiment.
      scanAntennas();
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
      toast("Réseau intercom reconnecté");
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
  function fitPreviews() { fitPreview(previewMini); fitPreview(previewFrame); fitPreview(screenPreviewFrame()); }

  /* Aperçu de l'onglet « Écran » : MÊME mécanique, mais servi par `?draft=1` — donc le
     BROUILLON, pas ce qui est à l'antenne. C'est la seule façon de juger une apparence,
     une luminosité ou un nombre de colonnes sans publier pour voir. Il ne se recharge
     que lorsque l'onglet est visible : une iframe dans un panneau `hidden` mesure 0, elle
     ne pourrait pas être mise à l'échelle (et on paierait un rendu pour rien). */
  const screenPreviewFrame = () => document.getElementById("screen-preview");
  function screenTabVisible() {
    const panel = document.querySelector('.tab-panel[data-panel="screen"]');
    return !!panel && !panel.hidden;
  }
  function reloadScreenPreview() {
    const frame = screenPreviewFrame();
    if (!frame || !screenTabVisible()) return;
    frame.src = `/admin/preview?draft=1&t=${Date.now()}`;
    fitPreview(frame);
  }

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
  function setDock(open, memoriser = true) {
    previewDock.dataset.open = open ? "1" : "0";
    dockToggle.setAttribute("aria-expanded", String(open));
    if (memoriser) {
      try { localStorage.setItem(DOCK_KEY, open ? "1" : "0"); } catch { /* mode privé */ }
    }
    // Replié, l'iframe est retirée du DOM de rendu : on la recharge (et remesure) au
    // dépliage, sinon elle afficherait l'état publié d'il y a peut-être une heure.
    if (open) { fitPreview(previewMini); reloadPreview(); }
  }

  /* Repli CONTEXTUEL sur l'onglet « Écran » (demande de Nathan) : ce panneau montre déjà
     le brouillon en grand, et le témoin de la latérale montre ce qui est à l'antenne —
     deux aperçus côte à côte, dont un minuscule.

     Il ne MÉMORISE rien : ce serait confondre « je n'en veux pas » avec « il gêne ici ».
     L'état d'avant est retenu et rendu en quittant l'onglet, sinon un simple passage par
     Écran effacerait en silence un réglage posé exprès. */
  let dockAvantEcran = null;
  function replierTemoin(surEcran) {
    if (surEcran) {
      if (dockAvantEcran === null) dockAvantEcran = previewDock.dataset.open === "1";
      if (dockAvantEcran) setDock(false, false);
    } else if (dockAvantEcran !== null) {
      if (dockAvantEcran) setDock(true, false);
      dockAvantEcran = null;
    }
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
    const wasHidden = document.getElementById("net-wifi-fields").hidden;
    document.getElementById("net-wifi-fields").hidden = link !== "wifi";
    // link-local n'a pas de sens en Wi-Fi : option masquée, bascule vers DHCP
    const ll = modeSel.querySelector('option[value="link-local"]');
    ll.disabled = link === "wifi";
    ll.hidden = link === "wifi";
    if (link === "wifi" && modeSel.value === "link-local") modeSel.value = "dhcp";
    document.getElementById("net-static-fields").hidden = modeSel.value !== "static";
    // Premier passage en Wi-Fi : lancer le scan une fois, sans le rejouer à chaque toggle.
    if (link === "wifi" && wasHidden && !wifiScanned) scanWifi();
  }

  /* ---------- Scan Wi-Fi : réseaux à proximité (lecture seule) ---------- */
  let wifiScanned = false;
  const wifiListEl = document.getElementById("net-wifi-list");
  function wifiState(html) { wifiListEl.innerHTML = `<li class="wifi-note">${html}</li>`; }
  function renderWifiList(networks) {
    const current = document.getElementById("net-ssid").value.trim();
    if (!networks.length) { wifiState("Aucun réseau détecté. Saisir le nom manuellement."); return; }
    wifiListEl.innerHTML = "";
    networks.forEach((n) => {
      const bars = Math.max(1, Math.min(4, Math.ceil(n.signal / 25)));   // 0-100 → 1-4 barres
      const li = document.createElement("li");
      li.className = "wifi-row" + (n.ssid === current ? " selected" : "");
      li.tabIndex = 0;
      li.setAttribute("role", "button");
      const sig = document.createElement("span");
      sig.className = "wifi-sig";
      for (let i = 1; i <= 4; i++) {
        const b = document.createElement("i");
        if (i <= bars) b.className = "on";
        sig.append(b);
      }
      const name = document.createElement("span");
      name.className = "wifi-name";
      name.textContent = n.ssid;                       // SSID non fiable : textContent, jamais innerHTML
      li.append(sig, name);
      if (n.secured) {
        const lock = document.createElement("span");
        lock.className = "wifi-lock";
        lock.title = "Réseau sécurisé";
        li.append(lock);
      }
      const pick = () => {
        document.getElementById("net-ssid").value = n.ssid;
        wifiListEl.querySelectorAll(".wifi-row").forEach((r) => r.classList.remove("selected"));
        li.classList.add("selected");
        document.getElementById("net-psk").focus();
      };
      li.addEventListener("click", pick);
      li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      wifiListEl.append(li);
    });
  }
  async function scanWifi() {
    wifiScanned = true;
    const btn = document.getElementById("net-scan-btn");
    btn.disabled = true;
    wifiState("Recherche des réseaux…");
    try {
      const res = await apiSend("GET", "/api/network/wifi-scan");
      if (!res.available) { wifiState("Recherche indisponible sur ce ComRoster — saisir le nom manuellement."); }
      else renderWifiList(res.networks || []);
    } catch { wifiState("Recherche impossible — saisir le nom manuellement."); }
    finally { btn.disabled = false; }
  }
  document.getElementById("net-scan-btn").addEventListener("click", scanWifi);
  document.getElementById("net-mode").addEventListener("change", toggleNetFields);
  document.getElementById("net-link").addEventListener("change", toggleNetFields);

  /* ---------- Masque de sous-réseau : préfixe /24 ↔ octets 255.255.255.0 ----------
     Deux écritures du même masque, synchronisées. Le préfixe reste la source de vérité
     (c'est lui qu'envoie le formulaire) ; le champ octets n'est qu'une commodité. */
  const prefixEl = document.getElementById("net-prefix");
  const maskEl = document.getElementById("net-mask");
  // Les deux conversions vivent dans static/js/netmask.js : pures, donc testées aux
  // bornes (/0, /32, masque non contigu type 255.0.255.0) sans passer par le navigateur.
  const { prefixToMask, maskToPrefix } = Netmask;
  function syncMaskFromPrefix() {
    const p = parseInt(prefixEl.value, 10);
    if (!Number.isInteger(p) || p < 1 || p > 32) return;
    maskEl.value = prefixToMask(p);
  }
  prefixEl.addEventListener("input", syncMaskFromPrefix);
  maskEl.addEventListener("input", () => {
    const p = maskToPrefix(maskEl.value);
    if (p !== null) prefixEl.value = p;            // masque valide → met à jour le préfixe
  });
  // En quittant le champ, un masque invalide se rétablit depuis le préfixe (jamais
  // d'état incohérent laissé à l'écran).
  maskEl.addEventListener("blur", () => { if (maskToPrefix(maskEl.value) === null) syncMaskFromPrefix(); });

  // « Joignable actuellement — Wi-Fi « X » · 192.168.1.42 » (état réel, lecture seule).
  async function loadNetCurrent() {
    const box = document.getElementById("net-current");
    box.hidden = true; box.textContent = "";
    let st;
    try { st = await apiSend("GET", "/api/network/status"); } catch { return; }
    if (!st.available || !(st.links || []).length) return;
    // Une ligne par connexion (type à gauche, IP à droite) : jamais de coupure disgracieuse
    // entre un réseau et son adresse.
    const rows = st.links.map((l) => {
      const type = l.type === "wifi" ? `Wi-Fi « ${l.ssid || "?"} »` : "Filaire (RJ45)";
      return `<div class="net-link-row"><span class="net-link-type">${esc(type)}</span>`
        + (l.ip ? `<span class="net-link-ip">${esc(l.ip)}</span>` : "") + "</div>";
    });
    box.innerHTML = '<span class="net-current-label">Joignable actuellement</span>' + rows.join("");
    box.hidden = false;
  }

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
    syncMaskFromPrefix();                // remplit le champ octets à partir du préfixe
    document.getElementById("net-gateway").value = cfg.gateway || "";
    document.getElementById("net-dns").value = (cfg.dns || []).join(", ");
    wifiScanned = false;                 // scan neuf à chaque ouverture
    wifiListEl.innerHTML = "";
    loadNetCurrent();                    // état réel du boîtier, en tête du dialogue
    toggleNetFields();
    if ((cfg.link || "ethernet") === "wifi") scanWifi();   // déjà en Wi-Fi : scanner d'emblée
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
        ? `Enregistré. Cliquez <b>Appliquer maintenant</b> — le ComRoster passera ${where} sur `
          + `<b>${esc(cfg.address)}</b> (adresse affichée à l'écran). Reconnectez-vous ensuite sur cette adresse.`
        : `Enregistré. Cliquez <b>Appliquer maintenant</b> — le ComRoster passera ${where} en adresse automatique.`;
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
    const btn = ev.currentTarget;              // AVANT l'await : currentTarget est nul après
    if (!await confirmDialog("Si l'adresse change, cette page perdra la connexion : rouvrir l'admin sur la nouvelle adresse.",
                             { title: "Appliquer la configuration réseau", okLabel: "Appliquer" })) return;
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
    const btn = ev.currentTarget;              // AVANT l'await : currentTarget est nul après
    if (!await confirmDialog("Écran et administration indisponibles environ une minute.",
                             { title: "Redémarrer le ComRoster", okLabel: "Redémarrer" })) return;
    const original = btn.innerHTML;
    btn.disabled = true; btn.textContent = "Redémarrage…";
    try {
      await apiSend("POST", "/api/reboot");
      toast("Redémarrage du ComRoster en cours…");
    } catch (e) {
      // Si le boîtier redémarre VRAIMENT, la requête peut échouer (connexion coupée).
      // Seule une réponse d'erreur explicite du serveur signifie que ça n'a pas marché.
      const refus = e && e.payload && e.payload.error;
      if (refus) {
        toast(refus, true);
        btn.disabled = false; btn.innerHTML = original;
      } else {
        toast("Redémarrage du ComRoster en cours…");
      }
    }
  });

  /* ---------- Sélection (clic direct sur un beltpack) ---------- */
  function updateSelectionBar() {
    document.getElementById("selection-count").textContent = `${state.selection.size} sélectionné(s)`;
    document.getElementById("selection-bar").classList.toggle("active", state.selection.size > 0);
    // Les groupes changent (création, renommage, suppression) : la liste se reconstruit à
    // chaque ouverture de la barre, et repart sur « — » pour ne rien affecter par erreur.
    const sel = document.getElementById("selection-group");
    if (!sel) return;
    sel.innerHTML = "";
    const none = document.createElement("option");
    none.value = ""; none.textContent = "— réserve —";
    const hold = document.createElement("option");
    hold.value = "__"; hold.textContent = "—";      // état neutre : aucune action
    sel.append(hold, none);
    state.data.groups.forEach((g) => {
      const o = document.createElement("option");
      o.value = g.id; o.textContent = g.name;
      sel.append(o);
    });
    sel.value = "__";
  }
  function exitSelection() {
    state.selection.clear();
    state.lastSelectedId = null;
    refreshSelectionClasses();
    updateSelectionBar();
  }
  document.getElementById("selection-cancel").addEventListener("click", exitSelection);
  // Réaffectation en LOT : le sélecteur de la vue Tableau ne pilote que sa rangée, il
  // fallait donc dix manipulations pour dix beltpacks. `assignMany` vide la sélection
  // et rend — le nombre traité est annoncé, un lot silencieux laisse douter.
  document.getElementById("selection-group").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v === "__" || !state.selection.size) return;   // « — » = état neutre
    const n = state.selection.size;
    const name = v ? (state.data.groups.find((g) => g.id === v)?.name || "ce groupe") : "la réserve";
    assignMany([...state.selection], v || null);
    toast(`${n} beltpack${n > 1 ? "s" : ""} déplacé${n > 1 ? "s" : ""} vers ${name}`);
  });
  document.getElementById("selection-delete").addEventListener("click", async () => {
    if (!state.selection.size) return;
    const n = state.selection.size;
    if (!await confirmDialog(`Supprimer ${n} beltpack${n > 1 ? "s" : ""} ?`,
                             { okLabel: "Supprimer", danger: true })) return;
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
          + `<button type="button" data-export="${esc(c.name)}">Exporter</button>`
          + `<button type="button" data-del="${esc(c.name)}" class="danger">Supprimer</button></span></li>`).join("")
      : "<li class='empty-hint'>Aucune configuration enregistrée.</li>";
    ul.querySelectorAll("[data-load]").forEach((b) => b.addEventListener("click", async () => {
      if (!await confirmDialog(`Charger « ${b.dataset.load} » ? Le Roster actuel sera remplacé et l'antenne déconnectée.`,
                               { title: "Charger la configuration", okLabel: "Charger" })) return;
      await apiSend("POST", `/api/configs/${encodeURIComponent(b.dataset.load)}/load`);
      document.getElementById("configs-dialog").close();
      setUnpublished(true);
      await load();
      toast("Configuration chargée");
    }));
    /* Export d'une config ENREGISTRÉE : son contenu est sur le disque, pas à l'écran.
       On le relit par une route de lecture pure — surtout pas `/load`, qui écraserait
       le plateau en cours et déconnecterait l'antenne pour un simple téléchargement.
       Le dialogue reste ouvert : exporter ne change rien, on peut en exporter deux. */
    ul.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", async () => {
      let cfg;
      try { cfg = await apiSend("GET", `/api/configs/${encodeURIComponent(b.dataset.export)}/export`); }
      catch { toast("Export impossible", true); return; }
      downloadRost(cfg.state, cfg.slug);
      toast(`« ${cfg.name} » exportée`);
    }));
    ul.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!await confirmDialog(`Supprimer « ${b.dataset.del} » ?`, { okLabel: "Supprimer", danger: true })) return;
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

  /* ---------- Sauvegarde complète du boîtier ----------
     L'export .rost ne couvre que le plateau. Ici : plateau + réglages + réseau + antenne
     + configurations + mot de passe, dans une archive CHIFFRÉE (elle contient le mot de
     passe Wi-Fi en clair). Le fichier transite en base64 dans du JSON : la protection
     CSRF et le traitement d'erreur du reste de l'API s'appliquent sans cas particulier. */
  const backupDialog = document.getElementById("backup-dialog");
  let backupPayloadB64 = null;      // archive examinée, en attente de confirmation

  function bkError(msg) {
    const p = document.getElementById("bk-error");
    p.textContent = msg || "";
    p.hidden = !msg;
  }
  function bkResetInspection() {
    backupPayloadB64 = null;
    document.getElementById("bk-summary").hidden = true;
    document.getElementById("bk-restore").hidden = true;
    bkError("");
  }

  document.getElementById("backup-btn").addEventListener("click", () => {
    document.getElementById("bk-pass").value = "";
    document.getElementById("bk-restore-pass").value = "";
    document.getElementById("bk-file").value = "";
    bkResetInspection();
    backupDialog.showModal();
  });

  document.getElementById("bk-create").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const passphrase = document.getElementById("bk-pass").value;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Chiffrement…";
    try {
      // L'archive est bâtie à partir du brouillon CÔTÉ SERVEUR : sans vider d'abord la
      // file d'enregistrement, une sauvegarde faite juste après une modification aurait
      // omis cette modification — en silence, et on ne s'en apercevrait qu'en restaurant.
      // Même garde que la publication (cf. publish()).
      if (savePending || saveTimer) await saveDraft();
      const res = await apiSend("POST", "/api/backup", { passphrase });
      // Base64 → octets → fichier. `atob` suffit : le contenu est de l'ASCII (JSON).
      const bytes = Uint8Array.from(atob(res.content), (c) => c.charCodeAt(0));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
      a.download = res.filename;
      document.body.append(a); a.click(); a.remove();
      URL.revokeObjectURL(a.href);
      toast("Sauvegarde téléchargée — conservez la phrase de passe avec le fichier");
    } catch (e) {
      toast(e.payload?.error || "Sauvegarde impossible", true);
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });

  // Changer de fichier ou de phrase invalide l'examen : « Restaurer » ne doit jamais
  // appliquer un contenu autre que celui qui vient d'être annoncé à l'écran.
  document.getElementById("bk-file").addEventListener("change", bkResetInspection);
  document.getElementById("bk-restore-pass").addEventListener("input", bkResetInspection);

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.onerror = () => reject(new Error("lecture impossible"));
      reader.readAsDataURL(file);        // rend « data:...;base64,XXXX »
    });
  }

  document.getElementById("bk-inspect").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const file = document.getElementById("bk-file").files?.[0];
    if (!file) { bkError("Choisissez d'abord un fichier de sauvegarde."); return; }
    const passphrase = document.getElementById("bk-restore-pass").value;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Lecture…";
    bkError("");
    try {
      const content = await readFileAsBase64(file);
      const s = await apiSend("POST", "/api/backup/inspect", { passphrase, content });
      backupPayloadB64 = content;
      const box = document.getElementById("bk-summary");
      box.innerHTML = [
        `<li><b>${s.groups}</b> groupe${s.groups > 1 ? "s" : ""}, <b>${s.people}</b> beltpack${s.people > 1 ? "s" : ""}</li>`,
        `<li><b>${s.configs}</b> configuration${s.configs > 1 ? "s" : ""} enregistrée${s.configs > 1 ? "s" : ""}</li>`,
        s.has_network ? `<li>Configuration réseau (${esc(s.network_link || "?")}) — <b>remplacera celle du ComRoster</b></li>` : "<li>Aucune configuration réseau</li>",
        s.has_antenna ? "<li>Identifiants du réseau intercom</li>" : "<li>Aucun identifiant intercom</li>",
        s.has_password ? "<li><b>Mot de passe d'administration</b> — remplacera celui du ComRoster</li>" : "<li>Aucun mot de passe</li>",
      ].join("");
      box.hidden = false;
      document.getElementById("bk-restore").hidden = false;
    } catch (e) {
      bkResetInspection();
      bkError(e.payload?.error || "Lecture impossible.");
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });

  document.getElementById("bk-restore").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    if (!backupPayloadB64) return;
    if (!await confirmDialog(
      "Le plateau, le réseau, les identifiants intercom et le mot de passe du ComRoster "
      + "seront remplacés par ceux de la sauvegarde. Action irréversible.",
      { title: "Restaurer la sauvegarde", okLabel: "Restaurer", danger: true })) return;
    const passphrase = document.getElementById("bk-restore-pass").value;
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Restauration…";
    try {
      const res = await apiSend("POST", "/api/backup/restore",
                                { passphrase, content: backupPayloadB64 });
      backupDialog.close();
      await load();
      refreshStatus();
      refreshAntennaBadge();
      reloadPreview();
      toast(res.password_changed
        ? "Sauvegarde restaurée — la prochaine connexion utilisera le mot de passe de l'archive"
        : "Sauvegarde restaurée");
    } catch (e) {
      bkError(e.payload?.error || "Restauration impossible.");
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  });

  /* ---------- Mot de passe d'administration ----------
     Le code de récupération n'est PAS consommé ici : c'est toute la différence avec
     « mot de passe oublié ». Un boîtier prêté d'une production à l'autre doit pouvoir
     tourner sa clé sans rediffuser un nouveau code à toute l'équipe. */
  const passwordDialog = document.getElementById("password-dialog");
  document.getElementById("password-btn").addEventListener("click", () => {
    document.getElementById("password-form").reset();
    document.getElementById("pw-error").hidden = true;
    passwordDialog.showModal();
  });
  document.getElementById("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("pw-error");
    const current = document.getElementById("pw-current").value;
    const nouveau = document.getElementById("pw-new").value;
    const confirme = document.getElementById("pw-confirm").value;
    err.hidden = true;
    // Vérifié ICI plutôt que côté serveur : la confirmation ne regarde que le
    // navigateur, et une faute de frappe ne mérite pas un aller-retour réseau.
    if (nouveau !== confirme) {
      err.textContent = "Les deux nouveaux mots de passe ne correspondent pas.";
      err.hidden = false; return;
    }
    try {
      await apiSend("POST", "/admin/password", { current, new: nouveau });
      passwordDialog.close();
      toast("Mot de passe changé — votre code de récupération reste valable");
    } catch (ex) {
      err.textContent = ex.payload?.error || "Changement impossible.";
      err.hidden = false;
    }
  });

  /* ---------- Découverte des antennes ----------
     Elle PROPOSE : cliquer un résultat remplit le champ d'adresse, sans jamais connecter
     ni remplacer la saisie manuelle — qui reste le seul chemin qui marche sur un réseau
     segmenté, un VLAN dédié ou une antenne hors sous-réseau. */
  const antListEl = document.getElementById("ant-list");
  function antState(html) { antListEl.innerHTML = `<li class="wifi-note">${html}</li>`; }
  function renderAntennas(antennas) {
    if (!antennas.length) {
      antState("Aucune antenne détectée. Saisissez l'adresse IP ci-dessous.");
      return;
    }
    antListEl.innerHTML = "";
    antennas.forEach((a) => {
      const li = document.createElement("li");
      li.className = "ant-row";
      li.tabIndex = 0;
      li.setAttribute("role", "button");
      const nom = document.createElement("span");
      nom.className = "ant-name";
      nom.textContent = a.name || "Antenne Bolero";   // nom non fiable : textContent
      const ip = document.createElement("span");
      ip.className = "ant-ip";
      ip.textContent = a.ip;
      const bp = document.createElement("span");
      bp.className = "ant-bp";
      bp.textContent = a.beltpacks
        ? `${a.beltpacks} beltpack${a.beltpacks > 1 ? "s" : ""}` : "";
      li.append(nom, ip, bp);
      const pick = () => {
        document.getElementById("wiz-ip").value = a.ip;
        antListEl.querySelectorAll(".ant-row").forEach((r) => r.classList.remove("selected"));
        li.classList.add("selected");
        document.getElementById("wiz-password").focus();
      };
      li.addEventListener("click", pick);
      li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      antListEl.append(li);
    });
  }
  async function scanAntennas() {
    const btn = document.getElementById("ant-scan-btn");
    btn.disabled = true;
    antState("Recherche sur le réseau…");
    try {
      const res = await apiSend("POST", "/api/antenna/discover");
      if (!res.available) antState(esc(res.error || "Recherche indisponible — saisissez l'adresse IP."));
      else renderAntennas(res.antennas || []);
    } catch { antState("Recherche impossible — saisissez l'adresse IP ci-dessous."); }
    finally { btn.disabled = false; }
  }
  document.getElementById("ant-scan-btn").addEventListener("click", scanAntennas);

  /* ---------- Synchro admin (auto-sync / autre poste) ---------- */
  // Si l'auto-sync (ou un autre poste) publie une nouvelle version, on recharge le
  // brouillon — mais SEULEMENT sans édits locaux en attente, pour ne pas écraser
  // un travail en cours dans cet onglet.
  function subscribeAdmin() {
    try {
      // `?role=admin` : ce flux occupe un thread serveur comme celui d'un écran, mais il
      // n'affiche rien en salle. Sans ce marqueur, ouvrir l'admin faisait afficher
      // « 1 afficheur » — ici comme sur la page Santé — sans le moindre écran branché.
      const es = new EventSource("/events?role=admin");
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
      // Nombre d'écrans de régie, poussé par le serveur à chaque branchement/débranchement.
      // Sans cette annonce, la barre d'état restait figée sur le compte du chargement :
      // brancher un écran ne se voyait qu'à la publication suivante.
      es.addEventListener("displays", (e) => {
        try { renderStatusBar(JSON.parse(e.data).displays); } catch { /* ignore */ }
      });
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
    // Calcul de l'écart et accord des pluriels : purs, donc testés sans navigateur
    // (Board.isDraftAhead / Board.pendingLabel).
    const unpublished = Board.isDraftAhead(state.data, publishedSummary, state.unpublished);
    pend.textContent = unpublished ? Board.pendingLabel(dg, dp) : "";

    // Chip d'en-tête « N en attente » (maquette) : même vérité que le pied de page, en
    // résumé. Les états transitoires (enregistrement en cours, erreur) restent
    // prioritaires — on ne les écrase pas.
    const chipState = el.syncStatus?.dataset.state;
    if (chipState === "syncing" || chipState === "error" || chipState === "updated") return;
    if (!unpublished) { setStatus("À jour", "idle"); return; }
    const n = Math.abs(dg) + Math.abs(dp);
    // Libellé COURT (« 5 en attente »), comme prévu à la maquette : le détail vit déjà
    // dans la barre d'état (« +1 groupe, +2 beltpacks non publiés »), et la version
    // longue faisait à elle seule 85 px de largeur figée dans l'en-tête.
    setStatus(n ? `${n} en attente` : "Modifications en attente", "pending");
  }

  async function refreshStatus() {
    let res;
    try { res = await apiSend("GET", "/api/status"); } catch { return; }
    publishedSummary = res.published || null;
    renderStatusBar(res.displays);
  }

  /* ---------- Onglets ----------
     Les CINQ sections de l'admin — Affectations, Écran, Journal, Santé, Impression —
     sont des panneaux d'un même document : l'en-tête, la latérale et la barre d'état
     ne bougent jamais. Leurs points d'entrée, eux, vivent là où leur fonction les a
     rangés (onglet de l'en-tête, item du menu « Réglages », rangée de la latérale) :
     ce code ne connaît que l'attribut `data-tab`, jamais l'endroit où il est posé.
     Antenne et réseau, eux, ne sont pas des panneaux — ils ouvrent un dialogue. */
  const TAB_KEY = "comroster.admin.tab";
  const tabEntries = () => document.querySelectorAll("[data-tab]");
  function selectTab(name) {
    tabEntries().forEach((el) => {
      const actif = el.dataset.tab === name;
      // Un onglet se DÉSIGNE (`aria-selected`) ; une rangée de menu ou de latérale
      // indique où l'on se trouve (`aria-current`). Deux registres, deux attributs.
      if (el.classList.contains("tab")) el.setAttribute("aria-selected", String(actif));
      else el.setAttribute("aria-current", actif ? "page" : "false");
    });
    // Une entrée nichée dans un menu allume l'onglet qui PORTE ce menu : sans ça, sur
    // Journal ou Santé, rien dans l'en-tête ne dirait où l'on est. La relation est lue
    // dans le DOM (l'entrée est-elle dans ce `.tab-menu` ?), jamais déclarée à côté.
    document.querySelectorAll(".tab-menu").forEach((menu) => {
      const dedans = !!menu.querySelector(`[data-tab="${CSS.escape(name)}"]`);
      menu.querySelector(".tab")?.toggleAttribute("data-active", dedans);
    });
    let montre = null;
    const partants = [];
    document.querySelectorAll(".tab-panel").forEach((p) => {
      const etaitVisible = !p.hidden;
      p.hidden = p.dataset.panel !== name;
      if (!p.hidden) montre = p;
      else if (etaitVisible) partants.push(p);
    });
    try { localStorage.setItem(TAB_KEY, name); } catch { /* mode privé */ }
    // Un panneau caché n'est ni mesurable ni à jour : l'aperçu du brouillon a besoin de
    // sa largeur, la feuille d'impression d'être refaite, le journal et la santé d'une
    // relève. UN seul signal pour les quatre — chacun s'y branche sans qu'on ait à
    // rallonger ici une liste de cas particuliers.
    // Symétrique de « panneau-affiche » : ce qu'un panneau allume en arrivant, il doit
    // pouvoir l'éteindre en partant — sans quoi la restauration se réécrirait ici sous
    // forme de cas particuliers, ce que ce signal existe précisément pour éviter.
    partants.forEach((p) => p.dispatchEvent(new CustomEvent("panneau-cache")));
    montre?.dispatchEvent(new CustomEvent("panneau-affiche"));
  }
  tabEntries().forEach((el) =>
    el.addEventListener("click", () => selectTab(el.dataset.tab)));

  // L'aperçu du brouillon n'est mesurable qu'une fois son panneau affiché (il est rendu
  // à 1920×1080 puis mis à l'échelle sur la largeur réelle).
  const panneauEcran = document.querySelector('.tab-panel[data-panel="screen"]');
  panneauEcran?.addEventListener("panneau-affiche", () => {
    reloadScreenPreview();
    replierTemoin(true);
  });
  panneauEcran?.addEventListener("panneau-cache", () => replierTemoin(false));

  /* ---------- Panneau Impression ----------
     La feuille reste SON propre document, chargé en trame : c'est lui qui porte les
     règles `@page`, les six réglages mémorisés et le rendu papier verrouillé par les
     tests — le recopier dans l'admin le remettrait en jeu pour rien. `embed=1` retire
     seulement son lien de retour, qui n'a pas de sens dans une trame.
     Rechargée à CHAQUE affichage : la feuille est rendue par le serveur, donc figée à
     l'instant du chargement. Imprimer une conduite périmée est précisément l'accident
     contre lequel cette feuille existe. La source choisie (publié / brouillon) est
     relue dans l'URL de la trame pour survivre à l'aller-retour. */
  const printPanel = document.querySelector('.tab-panel[data-panel="print"]');
  const printFrame = document.getElementById("print-frame");
  if (printPanel && printFrame) {
    let printQuery = "?embed=1";
    printFrame.addEventListener("load", () => {
      try {
        const s = printFrame.contentWindow.location.search;
        if (s.includes("embed=1")) printQuery = s;
      } catch { /* trame non lisible : on garde la dernière adresse connue */ }
    });
    printPanel.addEventListener("panneau-affiche", () => {
      printFrame.src = printFrame.dataset.src + printQuery;
    });
  }

  // Onglet restauré au rechargement : rafraîchir la page depuis « Écran » ramenait sur
  // « Affectations » (signalé à l'usage). Même politique que la bascule Blocs/Table.
  // `?panneau=` PRIME sur la mémoire : c'est une destination demandée à l'instant (les
  // anciennes adresses /admin/journal et /admin/health y redirigent). Elle est effacée
  // de la barre d'adresse aussitôt appliquée, sinon l'URL mentirait dès le clic suivant.
  // Les deux valeurs sont confrontées aux panneaux EXISTANTS, jamais réinjectées telles
  // quelles dans un sélecteur.
  // ⚠️ Cette restauration vient APRÈS tous les branchements sur « panneau-affiche » :
  // elle en émet un, et un panneau rétabli au chargement doit être servi comme un
  // panneau ouvert à la main (journal.js et health.js sont chargés avant admin.js
  // pour la même raison).
  try {
    const panels = [...document.querySelectorAll(".tab-panel")].map((p) => p.dataset.panel);
    const demande = new URLSearchParams(location.search).get("panneau");
    if (demande && panels.includes(demande)) {
      selectTab(demande);
      const url = new URL(location.href);
      url.searchParams.delete("panneau");
      history.replaceState(null, "", url);
    } else {
      const saved = localStorage.getItem(TAB_KEY);
      if (saved && saved !== "board" && panels.includes(saved)) selectTab(saved);
    }
  } catch { /* mode privé */ }

  /* ---------- Barre d'outils du plateau ---------- */
  // Recherche grep : estompe en direct les cartes hors correspondance (combiné aux vues).
  const boardFilter = document.getElementById("board-filter");
  boardFilter?.addEventListener("input", () => { state.boardQuery = boardFilter.value; applyView(); });

  // Bascule Blocs / Table — persistée : un rafraîchissement ne ramène pas aux Blocs.
  // Sélecteur BORNÉ à la barre du plateau : le panneau Journal porte lui aussi des
  // `.tb-seg .seg-btn` (Événements / Technique). À portée document, ce code les lierait
  // et un clic sur « Technique » appellerait setViewMode(undefined) — les deux vues du
  // plateau disparaîtraient d'un coup, depuis un autre panneau.
  const VIEWMODE_KEY = "comroster.admin.viewmode";
  const boardSegs = () => document.querySelectorAll(".board-toolbar .tb-seg .seg-btn");
  function setViewMode(mode) {
    boardSegs().forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.viewMode === mode)));
    document.getElementById("blocks-container").hidden = mode !== "blocs";
    const table = document.getElementById("blocks-table");
    table.hidden = mode !== "table";
    if (mode === "table") renderTable();
    try { localStorage.setItem(VIEWMODE_KEY, mode); } catch { /* mode privé */ }
  }
  boardSegs().forEach((b) =>
    b.addEventListener("click", () => setViewMode(b.dataset.viewMode)));
  try { if (localStorage.getItem(VIEWMODE_KEY) === "table") setViewMode("table"); } catch { /* mode privé */ }

  // Ajout de beltpack : UN seul bouton, au pied de la réserve (il arrive non affecté).
  document.getElementById("add-beltpack-pool")?.addEventListener("click", () => openPersonDialog(null, null));

  /* ---------- Raccourcis affichés : suivent la plateforme ----------
     ⌘ ne parle qu'aux Mac ; ailleurs on affiche Ctrl. Les handlers acceptent les
     deux (e.ctrlKey || e.metaKey), seul l'AFFICHAGE change. */
  if (!/Mac|iPhone|iPad/.test(navigator.platform || "")) {
    const pk = document.querySelector("#publish-btn kbd");
    if (pk) pk.textContent = "Ctrl+↵";
    const kk = document.querySelector(".pool-find kbd");
    if (kk) kk.textContent = "Ctrl+K";
  }

  /* ---------- Horloge de l'en-tête ---------- */
  const clockEl = document.getElementById("admin-clock");
  function tickClock() {
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString("fr-FR");
  }
  tickClock();
  setInterval(tickClock, 1000);

  /* ---------- Init ---------- */
  resetUndo();                // référence de départ : rien à annuler avant la 1re édition
  render();
  updateSelectionBar();
  refreshAntennaBadge();
  refreshStatus();            // résumé publié + afficheurs connectés (barre d'état)
  pollLive();                 // état initial ; les MAJ arrivent en push via le SSE `live`
  subscribeAdmin();
  renderStatusBar();          // chip d'état initiale (« À jour » / « N en attente »)
  lockHeaderWidths();         // largeurs figées (bouton + chip), re-mesurées polices prêtes
  if (document.fonts?.ready) document.fonts.ready.then(lockHeaderWidths);
})();
