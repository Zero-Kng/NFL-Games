/* ============================================================
   NFL GAMES — rascunho da nova Home
   Dados de exemplo apenas para visualizar o layout.
   ============================================================ */
(function () {
  'use strict';

  // ---------- dados de exemplo ----------
  const TEAMS = {
    DAL: { nick: 'Cowboys', color: '#041E42' }, TB: { nick: 'Buccaneers', color: '#D50A0A' },
    PHI: { nick: 'Eagles', color: '#004C54' }, ATL: { nick: 'Falcons', color: '#A71930' },
    PIT: { nick: 'Steelers', color: '#101820' }, BUF: { nick: 'Bills', color: '#00338D' },
    NYJ: { nick: 'Jets', color: '#125740' }, CAR: { nick: 'Panthers', color: '#0085CA' },
    MIN: { nick: 'Vikings', color: '#4F2683' }, CIN: { nick: 'Bengals', color: '#FB4F14' },
    SF: { nick: '49ers', color: '#AA0000' }, DET: { nick: 'Lions', color: '#0076B6' },
    KC: { nick: 'Chiefs', color: '#E31837' }, CLE: { nick: 'Browns', color: '#311D00' },
    GB: { nick: 'Packers', color: '#203731' }, NO: { nick: 'Saints', color: '#101820' },
  };

  const SEASONS = [2021, 2020, 2019, 2018];
  const WEEKS = 18;

  const GAMES = [
    ['DAL', 29, 'TB', 28, 'QUI 09/09'], ['PHI', 29, 'ATL', 6, 'DOM 12/09'],
    ['PIT', 23, 'BUF', 16, 'DOM 12/09'], ['NYJ', 14, 'CAR', 19, 'DOM 12/09'],
    ['MIN', 24, 'CIN', 27, 'DOM 12/09'], ['SF', 41, 'DET', 33, 'DOM 12/09'],
    ['CLE', 29, 'KC', 33, 'DOM 12/09'], ['GB', 3, 'NO', 38, 'DOM 12/09'],
  ];

  const NEWS = [
    { tone: 'red', tag: 'Jogo da semana', big: '29', title: 'Cowboys e Bucs abrem a temporada com virada no último drive',
      text: 'Decisão por um ponto em Tampa com field goal nos segundos finais.' },
    { tone: 'blue', tag: 'Defesa', big: '4', title: 'Eagles pressionam e somam 4 sacks contra Atlanta',
      text: 'Linha defensiva dominou o confronto e segurou o ataque em 6 pontos.' },
    { tone: 'dark', tag: 'Destaque', big: '41', title: '49ers passam dos 40 pontos em Detroit',
      text: 'Ataque aéreo eficiente garantiu a vitória fora de casa.' },
    { tone: 'red', tag: 'Tracking', big: '21', title: 'Recebedor atinge 21 mph na jogada mais rápida da rodada',
      text: 'Dados de tracking revelam a arrancada que abriu o placar.' },
  ];

  const PLAYERS = [
    ['Aaron Donald', 'DT · LA', 99], ['T.J. Watt', 'OLB · PIT', 97], ['Tom Brady', 'QB · TB', 96],
    ['Trent Williams', 'T · SF', 95], ['Myles Garrett', 'DE · CLE', 94], ['Patrick Mahomes', 'QB · KC', 93],
    ['Travis Kelce', 'TE · KC', 92], ['Micah Parsons', 'OLB · DAL', 91],
  ];

  // ---------- helpers ----------
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const badge = (abbr) => `<span class="badge" style="background:${TEAMS[abbr].color}">${abbr}</span>`;

  const state = { season: 2021, week: 1, slide: 0 };

  // ---------- filtros ----------
  function renderChips() {
    $('#seasonChips').innerHTML = SEASONS.map((s) =>
      `<button class="chip ${s === state.season ? 'active' : ''}" data-season="${s}" role="tab" aria-selected="${s === state.season}">${s}</button>`
    ).join('');
    $('#weekChips').innerHTML = Array.from({ length: WEEKS }, (_, i) => i + 1).map((w) =>
      `<button class="chip week ${w === state.week ? 'active' : ''}" data-week="${w}" role="tab" aria-selected="${w === state.week}">Sem ${w}</button>`
    ).join('');
  }

  // ---------- carrossel de notícias ----------
  function renderHero() {
    $('#heroTrack').innerHTML = NEWS.map((n) => `
      <article class="slide ${n.tone}" data-big="${esc(n.big)}">
        <span class="tag">${esc(n.tag)}</span>
        <h3>${esc(n.title)}</h3>
        <p>${esc(n.text)}</p>
      </article>`).join('');
    $('#heroDots').innerHTML = NEWS.map((_, i) =>
      `<button aria-label="Notícia ${i + 1}" data-slide="${i}" class="${i === 0 ? 'active' : ''}"></button>`
    ).join('');
  }

  function goToSlide(i) {
    const track = $('#heroTrack');
    state.slide = (i + NEWS.length) % NEWS.length;
    track.scrollTo({ left: track.clientWidth * state.slide, behavior: 'smooth' });
  }

  function syncDots() {
    const track = $('#heroTrack');
    const i = Math.round(track.scrollLeft / track.clientWidth);
    state.slide = i;
    $$('#heroDots button').forEach((b, k) => b.classList.toggle('active', k === i));
  }

  // ---------- partidas ----------
  function renderGames() {
    // gira a lista conforme a semana só para o rascunho não parecer estático
    const off = (state.week - 1) % GAMES.length;
    const list = GAMES.slice(off).concat(GAMES.slice(0, off));
    $('#gamesCount').textContent = `${list.length} jogos · semana ${state.week}`;
    $('#tileGames').textContent = list.length;
    $('#gamesList').innerHTML = list.map(([a, sa, b, sb, when]) => `
      <button class="match">
        <div class="team ${sa > sb ? 'win' : ''}">${badge(a)}${TEAMS[a].nick}</div>
        <div>
          <div class="score"><span class="${sa < sb ? 'lose' : ''}">${sa}</span><span class="sep">–</span><span class="${sb < sa ? 'lose' : ''}">${sb}</span></div>
          <div class="when">${when}</div>
        </div>
        <div class="team ${sb > sa ? 'win' : ''}">${badge(b)}${TEAMS[b].nick}</div>
      </button>`).join('');
  }

  // ---------- jogadores / notícias ----------
  function renderPlayers() {
    $('#playersList').innerHTML = PLAYERS.map(([name, pos, r], i) => `
      <div class="row-card">
        <span class="rank">${i + 1}</span>
        <div class="grow"><b>${esc(name)}</b><small>${esc(pos)}</small></div>
        <span class="rating">${r}</span>
      </div>`).join('');
  }

  function renderNews() {
    $('#newsList').innerHTML = NEWS.map((n) => `
      <article class="news-item">
        <div class="news-thumb ${n.tone}">${esc(n.big)}</div>
        <div>
          <div class="kicker">${esc(n.tag)}</div>
          <h4>${esc(n.title)}</h4>
          <p>${esc(n.text)}</p>
        </div>
      </article>`).join('');
  }

  // ---------- navegação ----------
  const TITLES = { home: 'Home', players: 'Jogadores', news: 'Notícias' };

  function go(view) {
    if (view === 'games') {
      go('home');
      $('#gamesBlock').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    $$('.screen').forEach((s) => s.classList.toggle('active', s.id === view));
    $$('.nav-item, .side-item[data-go]').forEach((b) => b.classList.toggle('active', b.dataset.go === view));
    $('#pageTitle').textContent = TITLES[view];
    window.scrollTo({ top: 0 });
  }

  // ---------- sidebar ----------
  function setMenu(open) {
    $('#sidebar').classList.toggle('open', open);
    $('#sidebar').setAttribute('aria-hidden', String(!open));
    $('#scrim').hidden = !open;
    $('#btnMenu').setAttribute('aria-expanded', String(open));
  }

  // ---------- pesquisa ----------
  function setSearch(open) {
    $('#searchbar').hidden = !open;
    $('#btnSearch').setAttribute('aria-expanded', String(open));
    if (open) {
      $('#searchInput').focus();
    } else {
      $('#searchInput').value = '';
      $('#searchResults').hidden = true;
    }
  }

  function runSearch(q) {
    const box = $('#searchResults');
    q = q.trim().toLowerCase();
    if (!q) { box.hidden = true; return; }
    const teams = Object.entries(TEAMS).filter(([k, t]) => k.toLowerCase().includes(q) || t.nick.toLowerCase().includes(q));
    const players = PLAYERS.filter(([n, p]) => n.toLowerCase().includes(q) || p.toLowerCase().includes(q));
    const news = NEWS.filter((n) => n.title.toLowerCase().includes(q));
    let html = '';
    if (teams.length) html += '<div class="sr-group">Times</div>' + teams.map(([k, t]) => `<button class="sr-item">${badge(k)}<div>${esc(t.nick)}<small>${k}</small></div></button>`).join('');
    if (players.length) html += '<div class="sr-group">Jogadores</div>' + players.map(([n, p, r]) => `<button class="sr-item"><span class="rating">${r}</span><div>${esc(n)}<small>${esc(p)}</small></div></button>`).join('');
    if (news.length) html += '<div class="sr-group">Notícias</div>' + news.map((n) => `<button class="sr-item" data-go="news"><div>${esc(n.title)}<small>${esc(n.tag)}</small></div></button>`).join('');
    box.innerHTML = html || `<div class="sr-empty">Nada encontrado para “${esc(q)}”.</div>`;
    box.hidden = false;
  }

  // ---------- eventos ----------
  document.addEventListener('click', (e) => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.season) { state.season = +t.dataset.season; renderChips(); }
    if (t.dataset.week) { state.week = +t.dataset.week; renderChips(); renderGames(); }
    if (t.dataset.slide) goToSlide(+t.dataset.slide);
    if (t.dataset.go) { go(t.dataset.go); setMenu(false); setSearch(false); }
  });

  $('#btnMenu').addEventListener('click', () => setMenu(true));
  $('#scrim').addEventListener('click', () => setMenu(false));
  $('#btnSearch').addEventListener('click', () => setSearch(true));
  $('#btnSearchClose').addEventListener('click', () => setSearch(false));
  $('#searchInput').addEventListener('input', (e) => runSearch(e.target.value));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { setMenu(false); setSearch(false); }
  });
  $('#heroTrack').addEventListener('scroll', () => requestAnimationFrame(syncDots), { passive: true });

  // avança o carrossel sozinho (pausa com o mouse em cima)
  let timer = setInterval(() => goToSlide(state.slide + 1), 5000);
  $('#hero').addEventListener('mouseenter', () => clearInterval(timer));
  $('#hero').addEventListener('mouseleave', () => { timer = setInterval(() => goToSlide(state.slide + 1), 5000); });

  // ---------- início ----------
  renderChips();
  renderHero();
  renderGames();
  renderPlayers();
  renderNews();
})();
