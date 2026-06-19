const board = document.getElementById('display-board');
const live = document.getElementById('live');
const stats = document.getElementById('stats');

const SCROLL = { initialDelay: 4000, edgePause: 2500, speed: 35 }; // px/s

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

function personRow(p) {
  // Le beltpack porte le rôle : on met en avant « n° → rôle », puis le nom.
  const role = p.role ? `<span class="d-role">${esc(p.role)}</span>` : '';
  return `<div class="d-person">` +
    `<span class="d-bp">${esc(p.beltpack)}</span>` +
    `<span class="d-info">${role}<span class="d-name">${esc(p.name)}</span></span>` +
    `</div>`;
}

function render(state) {
  board.innerHTML = '';
  const grouped = [...state.groups].sort((a, b) => a.order - b.order);
  for (const g of grouped) {
    const members = state.people.filter((p) => p.group_id === g.id);
    const card = document.createElement('section');
    card.className = 'glass-card';
    card.style.setProperty('--card-color', g.color);
    const body = members.length
      ? members.map(personRow).join('')
      : `<div class="empty">—</div>`;
    card.innerHTML = `<h2>${esc(g.name)}</h2>${body}`;
    board.appendChild(card);
  }
  stats.textContent = `${state.groups.length} groupes · ${state.people.length} personnes`;
}

function setLive(on) {
  live.classList.toggle('off', !on);
  live.classList.toggle('on', on);
  live.textContent = on ? '● En direct' : '● Reconnexion…';
}

function connect() {
  const es = new EventSource('/events');
  es.addEventListener('snapshot', (e) => { render(JSON.parse(e.data)); setLive(true); });
  es.addEventListener('published', (e) => { render(JSON.parse(e.data)); setLive(true); });
  es.onopen = () => setLive(true);
  es.onerror = () => setLive(false); // EventSource reconnecte seul ; le prochain snapshot resync (D8)
}

function tickClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('fr-FR');
}
setInterval(tickClock, 1000);
tickClock();

document.getElementById('theme').onclick = () => {
  const b = document.body;
  b.dataset.theme = b.dataset.theme === 'night' ? 'day' : 'night';
};

// Auto-scroll vertical doux avec pauses en haut/bas
function autoScroll() {
  let dir = 1, paused = true;
  setTimeout(() => (paused = false), SCROLL.initialDelay);
  let last = performance.now();
  function step(now) {
    const dt = (now - last) / 1000;
    last = now;
    if (!paused) {
      const max = document.body.scrollHeight - window.innerHeight;
      if (max > 0) {
        window.scrollBy(0, dir * SCROLL.speed * dt);
        const y = window.scrollY;
        if (y >= max - 1 && dir === 1) { dir = -1; paused = true; setTimeout(() => (paused = false), SCROLL.edgePause); }
        if (y <= 1 && dir === -1) { dir = 1; paused = true; setTimeout(() => (paused = false), SCROLL.edgePause); }
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

connect();
autoScroll();
