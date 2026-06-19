const CSRF = document.querySelector('meta[name="csrf-token"]').content;
let state = { groups: [], people: [], beltpack_roles: {} };

async function api(method, url, body) {
  const opts = { method, headers: { 'X-CSRFToken': CSRF } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(url, opts);
  const isJson = resp.headers.get('content-type')?.includes('json');
  const data = isJson ? await resp.json() : null;
  if (!resp.ok) {
    toast(data?.error || `Erreur ${resp.status}`, true);
    throw new Error(data?.code || resp.status);
  }
  return data;
}

function toast(msg, error) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.toggle('error', !!error);
  t.hidden = false;
  setTimeout(() => (t.hidden = true), 3000);
}

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

async function load() { state = await api('GET', '/api/state'); render(); }

function personLi(p) {
  const li = document.createElement('li');
  li.className = 'person';
  li.dataset.id = p.id;
  li.innerHTML = `<span class="name">${esc(p.name)}</span>` +
    `<span class="role">${esc(p.role)}</span>` +
    `<span class="bp">#${esc(p.beltpack)}</span>`;
  li.addEventListener('contextmenu', (e) => { e.preventDefault(); personMenu(p); });
  return li;
}

function render() {
  const groupsEl = document.getElementById('groups');
  const poolEl = document.getElementById('pool');
  groupsEl.innerHTML = '';
  poolEl.innerHTML = '';
  for (const p of state.people.filter((x) => !x.group_id)) poolEl.appendChild(personLi(p));
  for (const g of [...state.groups].sort((a, b) => a.order - b.order)) {
    const sec = document.createElement('section');
    sec.className = 'group';
    sec.style.borderTopColor = g.color;
    sec.innerHTML = `<h2 style="background:${g.color}">${esc(g.name)}` +
      `<span class="g-actions"><button data-edit="${g.id}">✎</button>` +
      `<button data-del="${g.id}">🗑</button></span></h2>`;
    const ul = document.createElement('ul');
    ul.className = 'people-list';
    ul.dataset.group = g.id;
    for (const p of state.people.filter((x) => x.group_id === g.id)) ul.appendChild(personLi(p));
    sec.appendChild(ul);
    groupsEl.appendChild(sec);
    makeSortable(ul);
  }
  makeSortable(poolEl);
  groupsEl.querySelectorAll('[data-del]').forEach((b) => (b.onclick = () => delGroup(b.dataset.del)));
  groupsEl.querySelectorAll('[data-edit]').forEach((b) => (b.onclick = () => editGroup(b.dataset.edit)));
}

function makeSortable(ul) {
  Sortable.create(ul, {
    group: 'people',
    animation: 150,
    onAdd: async (evt) => {
      const pid = evt.item.dataset.id;
      const gid = evt.to.dataset.group || null;
      try { await api('PATCH', `/api/people/${pid}`, { group_id: gid }); }
      finally { load(); }
    },
  });
}

async function delGroup(id) { await api('DELETE', `/api/groups/${id}`); load(); }

async function editGroup(id) {
  const g = state.groups.find((x) => x.id === id);
  const name = prompt('Nom du groupe', g.name);
  if (name === null) return;
  const color = prompt('Couleur (hex)', g.color);
  if (color === null) return;
  await api('PATCH', `/api/groups/${id}`, { name, color });
  load();
}

// Menu contextuel : changer le beltpack (et hériter du rôle mémorisé si connu)
function personMenu(p) {
  const bp = prompt(`Beltpack de ${p.name}`, p.beltpack);
  if (bp === null) return;
  const known = state.beltpack_roles[bp.trim()];
  const role = prompt(`Rôle pour le beltpack ${bp.trim()}`, known || p.role || '');
  if (role === null) return;
  api('PATCH', `/api/people/${p.id}`, { beltpack: bp, role }).then(load);
}

document.getElementById('add-group').onclick = async () => {
  const name = prompt('Nom du groupe');
  if (!name) return;
  const color = prompt('Couleur (hex)', '#00A8E8') || '#00A8E8';
  await api('POST', '/api/groups', { name, color });
  load();
};

document.getElementById('add-person').onclick = async () => {
  const name = prompt('Nom');
  if (!name) return;
  const beltpack = prompt('Numéro de beltpack');
  if (!beltpack) return;
  // Le rôle suit le beltpack : on propose celui déjà connu pour ce numéro.
  const known = state.beltpack_roles[beltpack.trim()];
  const role = prompt(`Rôle pour le beltpack ${beltpack.trim()} (Régie, Lumière…)`, known || '') || '';
  try {
    await api('POST', '/api/people', { name, role, beltpack });
    load();
  } catch (err) {
    if (String(err.message).includes('beltpack')) toast('Beltpack déjà attribué', true);
  }
};

document.getElementById('publish').onclick = async () => {
  await api('POST', '/api/publish');
  toast('Publié ✓');
};

document.getElementById('export').onclick = () => { window.location = '/api/export'; };

document.getElementById('import').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const data = JSON.parse(await file.text());
  await api('POST', '/api/import', data);
  load();
};

// Historique : consultation et restauration
document.getElementById('history-btn').onclick = async () => {
  const items = await api('GET', '/api/history');
  const ul = document.getElementById('history-list');
  ul.innerHTML = items.map((i) =>
    `<li>${esc(i.datetime)} <button data-restore="${i.timestamp}">Restaurer</button></li>`
  ).join('') || '<li>Aucune publication.</li>';
  ul.querySelectorAll('[data-restore]').forEach((b) => (b.onclick = async () => {
    await api('POST', `/api/history/${b.dataset.restore}/restore`);
    document.getElementById('history-dialog').close();
    toast('Snapshot restauré dans le brouillon');
    load();
  }));
  document.getElementById('history-dialog').showModal();
};
document.getElementById('history-close').onclick = () =>
  document.getElementById('history-dialog').close();

load();
