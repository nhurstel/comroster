/* Page Santé : contrôle avant show, pas tableau de mesures.
   La page répond D'ABORD à la seule question qu'on se pose devant un boîtier de régie —
   « est-ce que je peux lancer ? » — puis produit ses preuves. L'ancienne version alignait
   six cartes équivalentes où « Cœurs : 8 » pesait autant que « carte SD pleine à 90 % »,
   seule ligne capable de faire tomber le show.
   Tout reste tolérant à l'absence (champ null hors Pi) : l'indisponible n'occupe plus une
   carte vide, il est relégué à une ligne de pied. */
(() => {
  "use strict";

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // — formatage —
  // Virgule décimale : `toFixed` produit « 408.1 », qui n'est pas du français.
  const num = (v, digits) => v.toLocaleString("fr-FR",
    { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const bytes = (n) => {
    if (n == null) return "—";
    const u = ["o", "Ko", "Mo", "Go", "To"];
    let i = 0, v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return `${num(v, i >= 2 ? 1 : 0)} ${u[i]}`;
  };
  const duration = (s) => {
    if (s == null) return "—";
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d) return `${d} j ${h} h`;
    if (h) return `${h} h ${m} min`;
    return `${m} min`;
  };
  // Temps RELATIF : devant un boîtier, « il y a 3 min » se lit sans calcul mental,
  // « 27/07 19:05 » oblige à comparer avec l'horloge.
  const ago = (iso) => {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "—";
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
    return `il y a ${Math.round(s / 86400)} j`;
  };
  const DAY = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" });
  const onDay = (iso) => {
    const t = Date.parse(iso);
    return Number.isNaN(t) ? "—" : DAY.format(new Date(t));
  };
  const pct = (used, total) => (total ? Math.round(used / total * 100) : 0);

  /* Gravité : 2 = attention (le show est menacé), 1 = à surveiller, 0 = rien à signaler.
     Un seul barème sert À LA FOIS au verdict et à l'ordre du relevé — deux échelles
     séparées finiraient par se contredire. */
  const ALERT = 2, WATCH = 1, FINE = 0;

  function build(d) {
    const meters = [];     // mesures à SEUIL (une réglette a du sens)
    const facts = [];      // valeurs sans seuil (une réglette n'aurait rien à montrer)
    const missing = [];    // ce que cette machine ne sait pas mesurer
    const flags = [];      // {level, why} → alimente le verdict

    const disk = d.disk;
    if (disk) {
      const p = pct(disk.used, disk.total);
      const level = p >= 90 ? ALERT : p >= 80 ? WATCH : FINE;
      meters.push({ level, label: "stockage", value: `${bytes(disk.used)} / ${bytes(disk.total)}`, p });
      if (level) flags.push({ level, why: `la carte SD est pleine à ${p} %` });
    } else { missing.push("stockage"); }

    const mem = d.memory;
    if (mem) {
      const p = pct(mem.used, mem.total);
      const level = p >= 90 ? ALERT : p >= 75 ? WATCH : FINE;
      meters.push({ level, label: "mémoire", value: `${bytes(mem.used)} / ${bytes(mem.total)}`, p });
      if (level) flags.push({ level, why: `la mémoire est occupée à ${p} %` });
    } else { missing.push("mémoire"); }

    const cpu = d.cpu || {};
    if (cpu.temp_c != null) {
      const t = cpu.temp_c;
      const level = t >= 80 ? ALERT : t >= 70 ? WATCH : FINE;
      // 85 °C = seuil de bridage du Pi : la réglette se lit par rapport à LUI, pas à 100.
      meters.push({ level, label: "température", value: `${t} °C`, p: Math.min(100, Math.round(t / 85 * 100)) });
      if (level) flags.push({ level, why: `le processeur chauffe (${t} °C)` });
    } else { missing.push("température"); }

    const th = cpu.throttled;
    if (th) {
      if (th.undervoltage_now) flags.push({ level: ALERT, why: "l'alimentation ne suit pas (sous-tension)" });
      if (th.throttled_now) flags.push({ level: ALERT, why: "le processeur est bridé" });
      if (th.temp_limit_now) flags.push({ level: ALERT, why: "la limite thermique est atteinte" });
      const past = [th.undervoltage_past && "sous-tension", th.throttled_past && "bridage",
                    th.temp_limit_past && "limite thermique"].filter(Boolean);
      if (past.length && !th.undervoltage_now && !th.throttled_now && !th.temp_limit_now) {
        flags.push({ level: WATCH, why: `depuis l'allumage : ${past.join(", ")}` });
      }
    } else { missing.push("bridage processeur"); }

    /* Diffusion : c'est le cœur du métier. Publier sans écran connecté, c'est ne rien
       afficher en salle — ça vaut une alerte, pas une ligne de plus dans une carte. */
    const screens = d.displays ?? 0;
    const pub = d.published;
    if (pub && screens === 0) flags.push({ level: ALERT, why: "aucun écran n'est connecté" });
    if (!pub) flags.push({ level: WATCH, why: "rien n'a encore été publié" });
    facts.push({ heading: "diffusion" });
    facts.push({ label: "écrans connectés", value: String(screens), tone: screens > 0 ? "ok" : "bad" });
    facts.push({
      label: "dernière publication",
      value: pub ? ago(pub.updated_at) : "jamais",
      hint: pub ? `${pub.groups} groupe${pub.groups > 1 ? "s" : ""} · ${pub.people} beltpack${pub.people > 1 ? "s" : ""}` : "",
    });

    const a = d.antenna;
    if (a && a.ip && !a.connected) flags.push({ level: WATCH, why: "le réseau intercom est hors ligne" });
    facts.push({
      label: "réseau intercom",
      value: !a || !a.ip ? "non configuré" : a.connected ? "connecté" : "hors ligne",
      hint: a && a.ip ? a.ip : "",
      tone: a && a.connected ? "ok" : a && a.ip ? "warn" : "",
    });

    /* Charge : « 3.00 4.64 5.12 » ne dit rien à qui n'a pas grandi sous Unix. Ces
       nombres comptent les tâches qui attendent le processeur, et ne se lisent qu'en
       RAPPORT AU NOMBRE DE CŒURS — 4 sur 4 cœurs = saturé, 4 sur 8 = à moitié. On
       affiche donc un pourcentage de capacité, le détail brut en légende. */
    const cores = cpu.cores || 0;
    if (cpu.load && cores) {
      const p = Math.round(cpu.load[0] / cores * 100);
      const level = p >= 100 ? ALERT : p >= 70 ? WATCH : FINE;
      meters.push({
        level, label: "charge processeur", value: `${p} % de la capacité`,
        p: Math.min(100, p),
        hint: `${num(cpu.load[0], 2)} tâche${cpu.load[0] >= 2 ? "s" : ""} en attente `
              + `pour ${cores} cœur${cores > 1 ? "s" : ""} · moyenne sur 5 min `
              + `${num(cpu.load[1], 2)}, sur 15 min ${num(cpu.load[2], 2)}`,
      });
      if (level) flags.push({ level, why: `le processeur est chargé à ${p} % de sa capacité` });
    }

    /* Carte d'identité du logiciel. Elle précède les durées : « quel code tourne ici ? »
       vient avant « depuis combien de temps ». C'est le SEUL endroit qui montre le
       commit et l'éventuelle péremption — le pied de l'écran de régie, lui, est vu par
       le client. */
    const ver = d.version || {};
    facts.push({ heading: "version du logiciel" });
    if (ver.known) {
      facts.push({
        label: "version",
        value: ver.label,
        tone: ver.stale ? "warn" : "",
        hint: ver.stale
          ? `${ver.commit} · ${ver.date} — incertaine : le dépôt a changé depuis le déploiement`
          : `${ver.commit} · ${ver.date}`,
      });
    } else {
      // « known » vaut faux aussi bien quand le fichier est ABSENT (boîtier non
      // déployé par deploy/setup-pi.sh) que quand il est PRÉSENT mais vide, tronqué ou
      // corrompu (carte SD, coupure de courant) : services/version.py ne distingue pas
      // ces cas. Affirmer une cause précise ici serait affirmer plus que ce qu'on sait.
      facts.push({
        label: "version", value: "inconnue",
        hint: "fichier de version absent, vide ou mal formé",
      });
    }

    /* Temps : trois horizons distincts, et c'est la distinction qui porte l'information
       — depuis le dernier allumage, depuis le dernier démarrage de l'application, et
       depuis la toute première mise en service. */
    const up = d.uptime || {};
    const life = d.lifetime || {};
    facts.push({ heading: "temps de fonctionnement" });
    if (up.system_s != null) {
      facts.push({ label: "allumé depuis", value: duration(up.system_s),
                   hint: "dernière mise sous tension" });
    }
    if (up.app_s != null) {
      facts.push({ label: "session en cours", value: duration(up.app_s),
                   hint: "depuis le dernier démarrage de l'application" });
    }
    if (life.total_runtime_s != null) {
      facts.push({ label: "fonctionnement cumulé", value: duration(life.total_runtime_s),
                   hint: "toutes sessions confondues" });
    }
    if (life.installed_at) {
      facts.push({ label: "en service depuis", value: onDay(life.installed_at),
                   hint: ago(life.installed_at) });
    }
    if (life.starts) {
      facts.push({ label: "démarrages", value: String(life.starts),
                   hint: "depuis la mise en service" });
    }

    // Le plus grave en premier : c'est ce qu'on doit lire sans avoir à chercher.
    meters.sort((x, y) => y.level - x.level || y.p - x.p);
    flags.sort((x, y) => y.level - x.level);
    return { meters, facts, missing, flags };
  }

  const VERDICTS = {
    2: { state: "alert", word: "Attention" },
    1: { state: "watch", word: "À surveiller" },
    0: { state: "ok", word: "Prêt" },
  };

  function render(d) {
    const { meters, facts, missing, flags } = build(d);
    const level = flags.length ? flags[0].level : FINE;
    const v = VERDICTS[level];

    /* Le verdict est l'unique endroit où la page hausse la voix. Tout le reste est tenu
       au même registre discret : si tout crie, plus rien ne ressort. */
    const why = flags.length
      ? flags.filter((f) => f.level === level).map((f) => f.why).join(" · ")
      : "rien à signaler avant le show";
    const others = flags.filter((f) => f.level < level);

    const head = `<section class="verdict" data-state="${v.state}">
        <p class="verdict-word">${esc(v.word)}</p>
        <p class="verdict-why">${esc(why)}</p>
        ${others.length ? `<p class="verdict-more">aussi : ${esc(others.map((f) => f.why).join(" · "))}</p>` : ""}
      </section>`;

    const tone = (lvl) => (lvl === ALERT ? "bad" : lvl === WATCH ? "warn" : "ok");
    const meterRows = meters.map((m) => `<div class="meter" data-tone="${tone(m.level)}">
        <span class="meter-label">${esc(m.label)}</span>
        <span class="meter-value">${esc(m.value)}</span>
        <span class="meter-track"><i data-pct="${m.p}"></i></span>
        <span class="meter-pct">${m.p} %</span>
        ${m.hint ? `<span class="meter-hint">${esc(m.hint)}</span>` : ""}
      </div>`).join("");

    // Un intertitre n'a ni valeur ni légende : c'est une rupture, pas une ligne.
    const factRows = facts.map((f) => (f.heading
      ? `<div class="readout-heading">${esc(f.heading)}</div>`
      : `<div class="fact">
        <span class="fact-label">${esc(f.label)}</span>
        <span class="fact-value${f.tone ? " " + f.tone : ""}">${esc(f.value)}</span>
        <span class="fact-hint">${esc(f.hint || "")}</span>
      </div>`)).join("");

    const foot = missing.length
      ? `<p class="unmeasured">non mesuré sur cette machine : ${esc(missing.join(", "))}</p>` : "";

    const host = document.getElementById("health-report");
    host.innerHTML = head + `<div class="readout">${meterRows}${factRows}</div>` + foot;
    // Largeur des réglettes en CSSOM : la CSP interdit l'attribut style="".
    host.querySelectorAll(".meter-track i[data-pct]").forEach((f) => { f.style.width = f.dataset.pct + "%"; });
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
