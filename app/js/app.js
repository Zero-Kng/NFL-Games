/* ==========================================================================
   NFL GAMES — dados do nflverse (2021 em diante), pela API local
   (server/serve.py). Placar ao vivo e matéria do jogo vêm da ESPN, direto
   do navegador. Nenhum dado é inventado aqui.
   ========================================================================== */
(function () {
  'use strict';

  /* ------------------------------- API ---------------------------------- */
  // Cache de respostas da sessão (deduplica pedidos iguais, inclusive em voo).
  // LRU com teto, para não crescer sem fim numa sessão longa de navegação.
  const cache = new Map();
  const CACHE_MAX = 150;
  function get(path) {
    if (cache.has(path)) {
      const hit = cache.get(path);
      cache.delete(path);
      cache.set(path, hit); // vira o mais recente
      return hit;
    }
    while (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value);
    const p = fetch(path, { headers: { Accept: 'application/json' } })
      .then(async (res) => {
        if (!res.ok) {
          let msg = 'HTTP ' + res.status;
          try { const b = await res.json(); if (b.error) msg = b.error; } catch (e) {}
          throw new Error(msg);
        }
        return res.json();
      });
    cache.set(path, p);
    p.catch(() => { if (cache.get(path) === p) cache.delete(path); });
    return p;
  }
  function qs(o) {
    const sp = new URLSearchParams();
    Object.keys(o).forEach((k) => {
      if (o[k] !== undefined && o[k] !== null && o[k] !== '') sp.set(k, o[k]);
    });
    const s = sp.toString();
    return s ? '?' + s : '';
  }
  const api = {
    meta: () => get('/api/meta'),
    // A lista de jogos não entra no cache da sessão: o status muda com o relógio.
    games: (p) => { const u = '/api/games' + qs(p || {}); cache.delete(u); return get(u); },
    game: (g) => get('/api/games/' + g),
    plays: (g) => get('/api/games/' + g + '/plays'),
    tracking: (g, p) => get('/api/games/' + g + '/plays/' + p + '/tracking'),
    broadcast: (g) => get('/api/games/' + g + '/broadcast'),
    players: (p) => get('/api/players' + qs(Object.assign({ season: S.season }, p || {}))),
    player: (id) => get('/api/players/' + encodeURIComponent(id) + qs({ season: S.season })),
    compare: (a, b) => get('/api/compare' + qs({ season: S.season, a: a, b: b })),
  };

  /* ---------------------------- formatação ------------------------------ */
  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const isNum = (v) => v !== null && v !== undefined && !isNaN(v);
  const pct = (v, d) => (isNum(v) ? (v * 100).toFixed(d === undefined ? 0 : d) + '%' : '—');
  const nm = (v, d) => (isNum(v) ? Number(v).toFixed(d === undefined ? 0 : d) : '—');
  const secs = (v) => (isNum(v) ? Number(v).toFixed(1) + 's' : '—');
  const signed = (v) => (isNum(v) ? (v > 0 ? '+' + v : '' + v) : '—');
  function ordDown(d, y) {
    if (!isNum(d)) return '—';
    return (['', '1ª', '2ª', '3ª', '4ª'][d] || d + 'ª') + ' e ' + y;
  }
  // Datas do calendário vêm como AAAA-MM-DD; o horário do jogo, em UTC (kickoffUtc).
  function brDate(s) {
    if (!s) return '';
    const a = String(s).slice(0, 10).split('-');
    return a[2] + '/' + a[1];
  }
  function weekday(s) {
    if (!s) return '';
    const d = new Date(String(s).slice(0, 10) + 'T12:00:00');
    return ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB'][d.getDay()];
  }
  function inicioLocal(g) {
    if (!g.kickoffUtc) return weekday(g.date) + ' ' + brDate(g.date);
    const d = new Date(g.kickoffUtc);
    const dia = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB'][d.getDay()];
    return dia + ' ' + String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') +
      ' · ' + String(d.getHours()).padStart(2, '0') + 'h' + String(d.getMinutes()).padStart(2, '0');
  }
  function dataHora(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  function badge(t, size) {
    t = t || {};
    return '<span class="tbadge ' + (size || '') + '" style="background:' + esc(t.primary || '#013369') +
      '" title="' + esc(t.name || t.abbr || '') + '">' + esc(t.abbr || '?') + '</span>';
  }
  function rateCls(r) {
    if (!isNum(r)) return 'na';
    return r >= 88 ? 'elite' : r >= 75 ? 'good' : r >= 60 ? 'avg' : 'low';
  }
  function rateChip(r) {
    return '<span class="rate ' + rateCls(r) + '">' + (isNum(r) ? r : 'n/d') + '</span>';
  }
  function delta(v, lg, lowerBetter, asPct) {
    if (!isNum(v) || !isNum(lg)) return '';
    const d = v - lg;
    const good = lowerBetter ? d < 0 : d > 0;
    const flat = Math.abs(d) < (asPct ? 0.005 : 0.05);
    const cls = flat ? 'flat' : good ? 'up' : 'down';
    const txt = asPct ? (Math.abs(d) * 100).toFixed(0) + 'pp' : Math.abs(d).toFixed(1);
    return '<span class="delta ' + cls + '">' + (d > 0 ? '+' : d < 0 ? '−' : '') + txt + ' vs liga</span>';
  }
  const spin = (m) => '<div class="state"><span class="ic">🏈</span>' + esc(m || 'Carregando...') + '</div>';
  const oops = (m) => '<div class="state error"><span class="ic">⚠️</span>' + esc(m) + '</div>';
  const none = (m) => '<div class="state"><span class="ic">📭</span>' + esc(m) + '</div>';
  const $ = (id) => document.getElementById(id);

  /**
   * Renderiza em um container com estados de carregando/erro.
   * `atual`, se informado, diz se este pedido ainda é o mais recente: uma
   * resposta que chega atrasada (o usuário já pediu outra coisa) é descartada.
   * Devolve true se o resultado foi desenhado.
   */
  async function into(id, fn, msg, atual) {
    const el = $(id);
    if (!el) return false;
    el.innerHTML = spin(msg);
    let html;
    try { html = (await fn()) || ''; }
    catch (e) {
      if (atual && !atual()) return false;
      console.error(e);
      el.innerHTML = oops('Falha ao carregar: ' + e.message);
      return false;
    }
    if (atual && !atual()) return false;
    el.innerHTML = html;
    return true;
  }

  // "Só o último vence": cada fluxo que pode ser disparado de novo antes de a
  // resposta anterior chegar tem um contador. Quem volta com contador velho descarta.
  const seq = { play: 0, scout: 0, materia: 0 };

  /* ------------------------------ estado -------------------------------- */
  const S = {
    meta: null, season: null, week: null, games: [], gameId: null, game: null,
    live: {}, liveFalha: false,
    plays: [], playId: null, coachTab: 'lineup',
    scoutPos: '', scoutQuery: '', playerId: null, compareId: null,
    bc: null, bcIndex: 0, bcTimer: null,
  };
  const teamOf = (a) => (S.meta && S.meta.teams[a]) || { abbr: a, primary: '#013369', name: a };
  const league = () => (S.meta ? S.meta.league : {});
  const temporadaMeta = () => (S.meta ? S.meta.seasons.find((t) => t.season === S.season) : null);
  const semanaMeta = () => { const t = temporadaMeta(); return t ? t.weeks.find((w) => w.week === S.week) : null; };
  const rotuloSemana = (w) => (w && w.gameType && w.gameType !== 'REG' ? w.rodada : 'Semana ' + (w ? w.week : ''));
  function subtituloHome() {
    const t = temporadaMeta();
    return t ? 'Temporada ' + t.season + ' · ' + t.counts.played + ' jogos · ' +
      t.counts.plays.toLocaleString('pt-BR') + ' jogadas' : '';
  }

  /* ============================ NAVEGAÇÃO ============================== */
  const TITLES = {
    home: ['NFL GAMES', null],
    coach: ['TREINADOR', 'Prancheta tática'],
    scout: ['OLHEIRO', 'Central de scouting'],
    commentator: ['COMENTARISTA', 'Replay narrado'],
  };

  function go(screen) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    const el = $(screen);
    if (!el) return;
    el.classList.add('active');
    el.scrollTop = 0;

    const t = TITLES[screen];
    $('hdrTitle').textContent = t[0];
    if (screen === 'home') {
      $('hdrSub').textContent = subtituloHome();
    } else {
      $('hdrSub').textContent = S.game
        ? S.game.away.abbr + ' @ ' + S.game.home.abbr + ' · ' + S.game.season + ' · ' +
          (S.game.gameType === 'REG' ? 'semana ' + S.game.week : S.game.rodada)
        : t[1];
    }
    $('backBtn').style.display = screen === 'home' ? 'none' : 'block';
    document.querySelectorAll('.nav-item').forEach((n) =>
      n.classList.toggle('active', n.dataset.go === screen));

    if (screen === 'coach') renderCoach();
    if (screen === 'scout') renderScout();
    if (screen === 'commentator') renderBroadcast();
    if (screen !== 'commentator') stopBc();
  }

  /* ============================== HOME ================================= */
  function renderSeasons() {
    $('seasonPick').innerHTML = S.meta.seasons.map((t) =>
      '<option value="' + t.season + '"' + (t.season === S.season ? ' selected' : '') + '>' +
      t.season + (t.season === S.meta.season ? ' (atual)' : '') + '</option>').join('');
  }

  function semanaPadrao(season) {
    const t = S.meta.seasons.find((x) => x.season === season);
    if (!t) return null;
    const cw = t.currentWeek;
    return t.weeks.some((w) => w.week === cw) ? cw : t.weeks[0].week;
  }

  function renderWeeks() {
    const t = temporadaMeta();
    // Semanas da temporada regular como "SEM n"; playoffs com o nome da rodada (1.2).
    $('weekChips').innerHTML = (t ? t.weeks : []).map((w) =>
      '<button class="week-chip' + (w.week === S.week ? ' active' : '') + '" data-week="' + w.week + '"' +
      ' data-game-type="' + esc(w.gameType) + '">' +
      esc(w.gameType === 'REG' ? 'SEM ' + w.week : w.rodada) + '<small>' + w.games + ' jogos</small></button>').join('');
    const ativo = document.querySelector('.week-chip.active');
    if (ativo && ativo.scrollIntoView) ativo.scrollIntoView({ block: 'nearest', inline: 'center' });
  }

  async function renderGames() {
    aoVivo.parar();
    S.live = {};
    S.liveFalha = false;
    const pedido = { season: S.season, week: S.week };
    await into('gamesList', async () => {
      S.games = await api.games(pedido);
      if (!S.games.length) return none('Nenhum jogo nesta semana.');
      $('gamesCount').textContent = S.games.length + ' jogos · ' + rotuloSemana(semanaMeta());
      return S.games.map(gameCard).join('');
    }, 'Carregando as partidas...', () => pedido.season === S.season && pedido.week === S.week);
    posicionarMateria();
    aoVivo.avaliar();
  }

  function repintarJogos() {
    if (S.games.length) $('gamesList').innerHTML = S.games.map(gameCard).join('');
    posicionarMateria();
  }

  // A matéria fica logo abaixo da partida selecionada (o elemento é o mesmo;
  // só muda de lugar, inclusive depois que o placar ao vivo redesenha os cartões).
  const MATERIA = document.getElementById('materia');
  function posicionarMateria() {
    const sel = document.querySelector('#gamesList .match.selected');
    if (sel) sel.after(MATERIA);
    else $('gamesList').after(MATERIA);
  }

  // Estado exibido de um jogo: o placar oficial do nflverse vale sempre que ele
  // existir (10.6); sem ele, o placar ao vivo da ESPN, quando houver.
  function estadoDoJogo(g) {
    if (g.status === 'encerrado') return { tipo: 'final', home: g.home.score, away: g.away.score };
    const ao = S.live[g.espnId];
    if (ao && ao.state === 'in') return Object.assign({ tipo: 'aovivo' }, ao);
    if (ao && ao.state === 'post') return Object.assign({ tipo: 'final-espn' }, ao);
    return { tipo: g.status };    // 'agendado' ou 'sem_resultado'
  }

  function gameCard(g) {
    const e = estadoDoJogo(g);
    const temPlacar = e.tipo === 'final' || e.tipo === 'aovivo' || e.tipo === 'final-espn';
    const hw = temPlacar && isNum(e.home) && isNum(e.away) && e.home > e.away;
    const aw = temPlacar && isNum(e.home) && isNum(e.away) && e.away > e.home;
    let centro, status;
    if (temPlacar) {
      centro = '<div class="score">' +
        '<span style="' + (aw || e.tipo === 'aovivo' ? '' : 'opacity:.55') + '">' + nm(e.away) + '</span>' +
        '<span class="sep">–</span>' +
        '<span style="' + (hw || e.tipo === 'aovivo' ? '' : 'opacity:.55') + '">' + nm(e.home) + '</span></div>';
      if (e.tipo === 'aovivo') {
        status = '<span class="badge-live">AO VIVO</span> ' + esc(relogioAoVivo(e)) +
          (S.liveFalha ? '<div class="live-falha">atualização ao vivo indisponível</div>' : '');
      } else {
        status = 'FINAL' + (g.overtime ? ' <span class="badge-ot">PRORROG.</span>' : '') + ' · ' + inicioLocal(g);
      }
    } else if (e.tipo === 'agendado') {
      centro = '<div class="pending">A JOGAR</div>';
      status = inicioLocal(g);
    } else {
      centro = '<div class="sem-resultado">resultado ainda não disponível</div>';
      status = inicioLocal(g) +
        (S.liveFalha ? '<div class="live-falha">atualização ao vivo indisponível</div>' : '');
    }
    const meta = isNum(g.plays) && g.plays > 0
      ? g.plays + ' jogadas' + (isNum(g.sacks) ? ' · ' + g.sacks + (g.sacks === 1 ? ' sack' : ' sacks') : '') : '';
    return '<div class="match' + (g.gameId === S.gameId ? ' selected' : '') + '" data-game="' + g.gameId + '" ' +
      'data-estado="' + e.tipo + '" role="button" tabindex="0" aria-label="' + esc(g.away.abbr + ' contra ' + g.home.abbr) + '">' +
      '<div class="team">' + badge(g.away) + '<span class="name">' + esc(g.away.nick || g.away.abbr) + '</span></div>' +
      '<div class="center">' + centro +
      '<div class="status">' + status + '</div>' +
      (meta ? '<div class="meta-line">' + meta + '</div>' : '') +
      '</div>' +
      '<div class="team">' + badge(g.home) + '<span class="name">' + esc(g.home.nick || g.home.abbr) + '</span></div>' +
      '</div>';
  }

  function relogioAoVivo(e) {
    if (e.name === 'STATUS_HALFTIME') return 'Intervalo';
    const q = e.period > 4 ? 'PRORROG.' : 'Q' + e.period;
    return q + ' · ' + (e.clock || '');
  }

  /* --------------------------- placar ao vivo --------------------------- */
  // ESPN direto do navegador (ela recusa chamadas de servidor). A cada 30 s,
  // só enquanto a semana exibida tiver jogo já começado e ainda sem o placar
  // final (10.2 a 10.4). O nflverse, quando traz o jogo, prevalece (10.6).
  const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl';
  const AO_VIVO_MS = 30000;
  const SEMANA_ESPN = { WC: 1, DIV: 2, CON: 3, SB: 5 };
  const aoVivo = {
    timer: null,
    parar() { clearTimeout(this.timer); this.timer = null; },
    // Jogos que pedem consulta: começaram, não têm o placar oficial e a ESPN ainda não encerrou.
    pendentes() {
      const agora = Date.now();
      return S.games.filter((g) => g.status !== 'encerrado' && g.espnId && g.kickoffUtc &&
        Date.parse(g.kickoffUtc) <= agora && !(S.live[g.espnId] && S.live[g.espnId].state === 'post'));
    },
    avaliar() {
      this.parar();
      if (this.pendentes().length) { this.consultar(); return; }
      // Nenhum em andamento: dorme até o próximo início da semana (se houver).
      const agora = Date.now();
      const futuros = S.games.filter((g) => g.status === 'agendado' && g.kickoffUtc)
        .map((g) => Date.parse(g.kickoffUtc)).filter((t) => t > agora);
      if (futuros.length) {
        const espera = Math.min(Math.min.apply(null, futuros) - agora + 1000, 2147483647);
        this.timer = setTimeout(() => this.avaliar(), espera);
      }
    },
    async consultar() {
      const pedido = { season: S.season, week: S.week };
      const w = semanaMeta();
      const tipo = w && w.gameType !== 'REG' ? 3 : 2;
      const semana = tipo === 3 ? (SEMANA_ESPN[w.gameType] || 1) : S.week;
      try {
        const r = await fetch(ESPN + '/scoreboard?dates=' + S.season + '&seasontype=' + tipo + '&week=' + semana);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const d = await r.json();
        if (pedido.season !== S.season || pedido.week !== S.week) return;     // trocaram de semana
        (d.events || []).forEach((ev) => {
          const c = (ev.competitions || [])[0] || {};
          const st = (c.status || ev.status || {});
          const lado = (h) => ((c.competitors || []).find((x) => x.homeAway === h) || {}).score;
          S.live[ev.id] = {
            state: st.type && st.type.state, name: st.type && st.type.name,
            period: st.period, clock: st.displayClock,
            home: isNum(lado('home')) ? Number(lado('home')) : null,
            away: isNum(lado('away')) ? Number(lado('away')) : null,
          };
        });
        S.liveFalha = false;
      } catch (e) {
        if (pedido.season !== S.season || pedido.week !== S.week) return;
        console.warn('placar ao vivo indisponível:', e.message);
        S.liveFalha = true;       // mantém o último placar conhecido (10.5)
      }
      repintarJogos();
      if (this.pendentes().length) this.timer = setTimeout(() => this.consultar(), AO_VIVO_MS);
      else this.avaliar();
    },
  };

  async function selectGame(gameId) {
    S.gameId = Number(gameId);
    S.playId = null;
    S.plays = [];
    S.bc = null;
    S.bcIndex = 0;
    document.querySelectorAll('.match').forEach((m) =>
      m.classList.toggle('selected', Number(m.dataset.game) === S.gameId));
    posicionarMateria();
    renderMateria();
    await loadGameDetail();
  }

  async function loadGameDetail() {
    const lead = $('personaLead');
    lead.textContent = 'Carregando o jogo...';
    try {
      S.game = await api.game(S.gameId);
    } catch (e) {
      lead.textContent = 'Falha ao carregar o jogo.';
      return;
    }
    lead.innerHTML = 'Analisando <b>' + esc(S.game.away.abbr) + ' @ ' + esc(S.game.home.abbr) +
      '</b> · escolha seu modo';
    renderInsights();
    renderWatch();
    renderNotes();
  }

  /* --------------------------- matéria do jogo --------------------------- */
  // Só links https de *.espn.com (S.4); http vira https.
  function linkEspn(href) {
    try {
      const u = new URL(href);
      if (u.protocol === 'http:') u.protocol = 'https:';
      const h = u.hostname.toLowerCase();
      if (u.protocol !== 'https:' || !(h === 'espn.com' || h.endsWith('.espn.com'))) return null;
      return u.href;
    } catch (e) { return null; }
  }

  async function renderMateria() {
    const my = ++seq.materia;
    const box = MATERIA;
    box.hidden = true;
    box.innerHTML = '';
    const g = S.games.find((x) => x.gameId === S.gameId);
    if (!g || !g.espnId || estadoDoJogo(g).tipo === 'agendado') return;
    try {
      const r = await fetch(ESPN + '/summary?event=' + encodeURIComponent(g.espnId));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (my !== seq.materia) return;
      conferirPlacar(g, d);
      const a = d.article;
      if (!a || !a.headline) return;          // sem matéria: o bloco fica oculto (6.3)
      const link = linkEspn(a.links && a.links.web && a.links.web.href);
      const fonte = (a.source ? a.source + ' · ' : '') + 'ESPN';
      box.innerHTML = '<div class="materia">' +
        '<div class="fonte">Matéria do jogo · ' + esc(fonte) + '</div>' +
        '<h4>' + esc(a.headline) + '</h4>' +
        (a.description ? '<p>' + esc(a.description) + '</p>' : '') +
        '<div class="rodape"><span>' + esc(dataHora(a.published)) + '</span>' +
        (link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener noreferrer">Ler na ESPN ›</a>' : '') +
        '</div></div>';
      box.hidden = false;
    } catch (e) {
      if (my === seq.materia) console.warn('matéria indisponível:', e.message);
    }
  }

  // 2.4: se a ESPN e o nflverse divergirem no placar final, vale o nflverse (o que já é exibido).
  function conferirPlacar(g, d) {
    try {
      const c = d.header.competitions[0];
      if (g.status !== 'encerrado' || !(c.status.type.state === 'post')) return;
      const lado = (h) => Number((c.competitors.find((x) => x.homeAway === h) || {}).score);
      if (lado('home') !== g.home.score || lado('away') !== g.away.score) {
        console.warn('placar da ESPN diverge do nflverse no jogo ' + g.gameId + ': ESPN ' + lado('away') + '–' +
          lado('home') + ', nflverse ' + g.away.score + '–' + g.home.score + ' (vale o nflverse)');
      }
    } catch (e) { /* sem cabeçalho: nada a conferir */ }
  }

  function mostrarSecao(id, visivel) { $(id).hidden = !visivel; }

  function renderInsights() {
    const list = (S.game && S.game.insights) || [];
    mostrarSecao('insightsSec', list.length > 0);    // sem fonte hoje: oculto (8.3)
    $('insightsList').innerHTML = list.map((c) =>
          '<div class="tip-card ' + esc(c.tone) + '" data-go="coach">' +
          '<div class="tip-ic ' + esc(c.tone) + '">' + esc(c.icon) + '</div>' +
          '<div class="tip-body">' +
            '<div class="tip-title"><span class="tip-team" style="background:' +
              esc(teamOf(c.team).primary) + '">' + esc(c.team) + '</span>' + esc(c.title) + '</div>' +
            '<div class="tip-text">' + esc(c.text) + '</div>' +
          '</div>' +
          (c.metric ? '<div class="tip-metric"><div class="v">' + esc(c.metric.value) +
            '</div><div class="k">' + esc(c.metric.label) + '</div></div>' : '') +
          '</div>').join('');
  }

  function renderWatch() {
    const list = (S.game && S.game.watch) || [];
    mostrarSecao('watchSec', list.length > 0);
    $('watchList').innerHTML = list.length
      ? '<div class="watch-scroll">' + list.map((p) =>
          '<div class="watch-card" data-player="' + esc(p.nflId) + '" role="button" tabindex="0">' +
          '<div class="watch-avatar" style="background:' + esc(teamOf(p.team).primary) + '">' +
            esc((p.position || '').slice(0, 3)) + '</div>' +
          '<div class="watch-name">' + esc(shortName(p.name)) + '</div>' +
          '<div class="watch-pos">' + esc(p.position || '') + ' · ' + esc(p.team || '') + '</div>' +
          '<div class="watch-pos muted" style="font-size:10px">' + esc(p.roleLabel) + '</div>' +
          '<span class="watch-rating">' + (isNum(p.rating) ? p.rating : 'n/d') + '</span>' +
          '</div>').join('') + '</div>'
      : '';
  }

  function renderNotes() {
    const list = (S.game && S.game.notes) || [];
    mostrarSecao('notesSec', list.length > 0);
    $('notesList').innerHTML = list.map((n) =>
          '<div class="news-card"><div class="news-ic">' + esc(n.icon) + '</div>' +
          '<div class="news-body"><div class="news-title">' + esc(n.title) + '</div>' +
          '<div class="news-text">' + esc(n.text) + '</div></div></div>').join('');
  }

  function shortName(n) {
    if (!n) return '';
    const p = n.split(' ');
    return p.length > 1 ? p[0][0] + '. ' + p.slice(1).join(' ') : n;
  }

  // "Sobre os dados": fontes com o crédito de cada licença (9.1) e a última atualização (7.4).
  function renderSobre() {
    const m = S.meta;
    const anos = m.seasons.map((t) => t.season);
    $('sobreDados').innerHTML = '<div class="sobre"><h5>Sobre os dados</h5>' +
      'Temporadas ' + Math.min.apply(null, anos) + ' a ' + Math.max.apply(null, anos) +
      ', temporada regular e playoffs, com todas as jogadas.' +
      '<ul>' + (m.fontes || []).map((f) =>
        '<li><b>' + esc(f.nome) + '</b> — ' + esc(f.credito) + '. Usado para: ' + esc(f.usadoPara) + '.</li>').join('') + '</ul>' +
      '<div class="atualizado">Última atualização: ' +
        (m.ultimaAtualizacao ? esc(dataHora(m.ultimaAtualizacao)) : 'sem registro') + '</div>' +
      '<div>A prancheta mostra posições-modelo da formação (ilustrativas); os ratings são percentis ' +
      'de estatísticas públicas dentro de cada grupo de posição e temporada.</div></div>';
  }

  /* ============================= TREINADOR ============================== */
  function renderCoach() {
    if (!S.gameId) { $('coachBody').innerHTML = none('Escolha uma partida na aba Jogos.'); return; }
    $('coachSub').textContent = S.game
      ? S.game.away.abbr + ' @ ' + S.game.home.abbr + (isNum(S.game.plays) ? ' · ' + S.game.plays + ' jogadas' : '')
      : '';
    document.querySelectorAll('#coachTabs .subtab').forEach((b) =>
      b.classList.toggle('active', b.dataset.tab === S.coachTab));

    if (S.coachTab === 'lineup') return coachLineup();
    seq.play++; // uma prancheta ainda carregando não pode desenhar sobre outra aba
    if (S.coachTab === 'plays') return coachPlays();
    if (S.coachTab === 'stats') return coachStats();
    return coachBook();
  }

  async function ensurePlays() {
    if (!S.plays.length) S.plays = await api.plays(S.gameId);
    if (!S.playId) {
      const first = S.plays.filter((p) => p.hasFormation)[0] || S.plays[0];
      S.playId = first ? first.playId : null;
    }
    return S.plays;
  }

  async function coachLineup() {
    const my = ++seq.play;
    const body = $('coachBody');
    body.innerHTML = spin('Carregando a prancheta...');
    try {
      await ensurePlays();
      if (my !== seq.play) return; // o usuário já escolheu outra jogada
      if (!S.playId) { body.innerHTML = none('Este jogo ainda não tem jogadas na fonte.'); return; }

      body.innerHTML =
        '<div class="card">' +
          '<h4>Prancheta tática<span class="sec-sub" id="fieldSub"></span></h4>' +
          '<div class="field-legend">' +
            '<span><i class="sw" style="background:#fff;border-radius:50%"></i>Ataque (círculo)</span>' +
            '<span><i class="sw" style="background:#fff"></i>Defesa (quadrado)</span>' +
            '<span><i class="sw" style="background:#3B82F6"></i>Linha de scrimmage</span>' +
            '<span><i class="sw" style="background:#FACC15"></i>1ª descida</span>' +
          '</div>' +
          '<div class="field-wrap" id="fieldWrap"><div class="field" id="field"></div></div>' +
          '<div id="avisoField"></div>' +
          '<div id="animCtrl">' +
            '<div class="field-ctrl">' +
              '<button id="btnPlay" aria-label="Reproduzir jogada">▶</button>' +
              '<input type="range" id="frameRange" min="0" max="10" value="0" aria-label="Quadro da jogada" />' +
              '<span class="tcode" id="frameClock">0.0s</span>' +
            '</div>' +
            '<div class="field-ctrl" style="padding-top:2px">' +
              '<div class="speed-pick" id="speedPick">' +
                '<button data-sp="0.25">0.25×</button><button data-sp="0.5">0.5×</button>' +
                '<button data-sp="1" class="active">1×</button><button data-sp="2">2×</button>' +
              '</div>' +
              '<span class="spacer"></span>' +
              '<span class="muted" style="font-size:11px">Toque num jogador</span>' +
            '</div>' +
            '<div class="ev-strip" id="evStrip"></div>' +
          '</div>' +
          '<div id="dotInfo" style="margin-top:10px"></div>' +
        '</div>' +
        '<div class="card tight"><h4>Jogada</h4><div id="playMeta"></div></div>' +
        '<div class="card tight">' +
          '<h4>Trocar jogada<span class="sec-sub">' + S.plays.length + ' jogadas no jogo</span></h4>' +
          '<div class="cmp-pick"><select id="playPick" aria-label="Escolher jogada"></select></div>' +
          '<div class="row"><button class="ev-chip" id="prevPlay">‹ anterior</button>' +
          '<button class="ev-chip" id="nextPlay">próxima ›</button></div>' +
        '</div>';

      $('playPick').innerHTML = S.plays.map((p) =>
        '<option value="' + p.playId + '"' + (p.playId === S.playId ? ' selected' : '') + '>' +
        'Q' + p.quarter + ' ' + esc(p.clock || '') + ' · ' + esc(p.offense || '') + ' · ' +
        (isNum(p.down) ? ordDown(p.down, p.yardsToGo) : esc(p.passResultLabel)) +
        (isNum(p.result) ? ' · ' + signed(p.result) + 'jd' : '') +
        (p.hasFormation ? '' : ' · sem formação') + '</option>').join('');

      await loadFieldPlay(my);
    } catch (e) {
      if (my !== seq.play) return; // erro de um pedido que já não importa
      console.error(e);
      body.innerHTML = oops('Falha ao montar a prancheta: ' + e.message);
    }
  }

  let FV = null;

  async function loadFieldPlay(my) {
    const gameId = S.gameId, playId = S.playId;
    const card = S.plays.find((q) => q.playId === playId) || {};
    if (FV) FV.pause(); // a animação anterior não pode seguir mexendo nos controles novos
    if (!card.hasFormation) {
      // 4.5: sem nenhum dado de formação, a mensagem no lugar da prancheta.
      FV = null;
      $('fieldWrap').innerHTML = '<div class="formacao-indisponivel">Formação indisponível para esta jogada.</div>';
      $('animCtrl').hidden = true;
      $('avisoField').innerHTML = '';
      $('fieldSub').textContent = '';
      $('dotInfo').innerHTML = '';
      $('playMeta').innerHTML = playMetaHTML(card);
      return;
    }
    const tr = await api.tracking(gameId, playId);
    if (my !== seq.play) return; // resposta atrasada: outra jogada já foi pedida
    const p = tr.play;
    $('fieldWrap').innerHTML = '<div class="field" id="field"></div>';
    FV = new Field($('field'), tr);
    FV.onFrame = (i) => {
      $('frameRange').value = i;
      $('frameClock').textContent = (FV.clockAt(i) >= 0 ? '+' : '') + FV.clockAt(i).toFixed(1) + 's';
    };
    FV.onState = (playing) => { $('btnPlay').textContent = playing ? '❚❚' : '▶'; };
    FV.onSelect = (pl) => { $('dotInfo').innerHTML = pl ? dotCard(pl) : ''; };

    // Um quadro só (o esquema): sem controles de animação (7.4).
    const animado = tr.frameCount > 1;
    $('animCtrl').hidden = !animado;
    $('frameRange').max = Math.max(0, tr.frameCount - 1);
    $('fieldSub').textContent = animado ? tr.frameCount + ' quadros · ataque joga para cima' : 'ataque joga para cima';
    $('avisoField').innerHTML = tr.ilustrativo
      ? '<div class="aviso-ilustrativo"><b>Esquema ilustrativo:</b> posições-modelo da formação, não o alinhamento real da jogada.' +
        (tr.generico ? ' A fonte ainda não publicou os jogadores desta jogada: posições genéricas, sem nomes.' : '') +
        '</div>'
      : '';
    FV.setFrame(tr.snapIndex || 0);

    $('evStrip').innerHTML = (tr.events || []).map((e) =>
      '<button class="ev-chip" data-frame="' + e.frame + '">' + esc(evLabel(e.name)) + '</button>').join('');

    $('playMeta').innerHTML = playMetaHTML(p, tr.formacao);
    prefetchVizinhas(gameId, playId);
  }

  /**
   * Antecipa as jogadas anterior e seguinte, depois que a atual já está
   * desenhada (a escolhida nunca disputa conexão com a antecipação). Falha
   * aqui é silenciosa: o get() esquece o pedido e a jogada é buscada de novo
   * se o usuário a escolher.
   */
  function prefetchVizinhas(gameId, playId) {
    const lista = S.plays.filter((q) => q.hasFormation);
    const i = lista.findIndex((q) => q.playId === playId);
    if (i < 0) return;
    [lista[i + 1], lista[i - 1]].forEach((q) => {
      if (q) api.tracking(gameId, q.playId).catch(() => {});
    });
  }

  const EV_PT = {
    ball_snap: 'snap', autoevent_ballsnap: 'snap (auto)', pass_forward: 'lançamento',
    autoevent_passforward: 'lançamento (auto)', qb_sack: 'sack', play_action: 'play action',
    line_set: 'linha pronta', man_in_motion: 'jogador em movimento', pass_arrived: 'bola chega',
    pass_outcome_caught: 'recepção', pass_outcome_incomplete: 'incompleto', run: 'corrida',
    fumble: 'fumble', autoevent_passinterrupted: 'passe interrompido',
    fumble_offense_recovered: 'fumble recuperado', pass_tipped: 'bola desviada',
    qb_strip_sack: 'strip sack', pass_shovel: 'passe de bandeja', handoff: 'entrega',
  };
  const evLabel = (n) => EV_PT[n] || String(n || '').replace(/_/g, ' ');

  // Só as linhas com dado: o que a fonte não tem fica fora (8.3).
  function playMetaHTML(p, f) {
    f = f || {};
    const rows = [
      ['Situação', isNum(p.down) ? ordDown(p.down, p.yardsToGo) + ' na ' + esc(p.yardline) : null],
      ['Momento', 'Q' + p.quarter + ' · ' + esc(p.clock || '')],
      ['Resultado', (isNum(p.result) ? signed(p.result) + ' jd · ' : '') + esc(p.passResultLabel || '')],
      ['Formação', p.formation ? esc(p.formation) + (p.playAction ? ' + play action' : '') : null],
      ['Pessoal (ataque)', p.personnelO ? esc(p.personnelO) : null],
      ['Pessoal (defesa)', p.personnelD ? esc(p.personnelD) : null],
      ['Defensores no box', isNum(p.defendersInBox) ? p.defendersInBox : isNum(f.box) ? f.box : null],
      ['Rushers', isNum(p.rushers) ? p.rushers + (p.blitz ? ' · blitz' : '') : isNum(f.rushers) ? f.rushers : null],
      ['Cobertura', p.coverage ? esc(p.coverage) + (p.coverageType ? ' (' + esc(p.coverageType) + ')' : '') : null],
      ['Tempo p/ lançar', isNum(p.timeToThrow) ? secs(p.timeToThrow) + ' ' + delta(p.timeToThrow, league().timeToThrow, true) : null],
      ['Pressão', p.pressured === true ? 'sim' : p.pressured === false ? 'não' : null],
      ['EPA', isNum(p.epa) ? nm(p.epa, 2) : null],
    ].filter((r) => r[1] !== null && r[1] !== '');
    return '<div class="play-desc" style="margin-bottom:10px">' + esc(p.description) + '</div>' +
      (p.semFormacao ? '<div class="chips" style="margin-bottom:8px"><span class="chip">SEM DADOS DE FORMAÇÃO</span></div>' : '') +
      rows.map((r) => '<div class="stat-row"><span class="k">' + r[0] +
        '</span><span class="v" style="font-size:13px">' + r[1] + '</span></div>').join('') +
      (p.tags && p.tags.length ? '<div class="chips">' + p.tags.map((t) =>
        '<span class="chip ' + tagCls(t) + '">' + esc(t) + '</span>').join('') + '</div>' : '');
  }

  function tagCls(t) {
    if (t === 'TOUCHDOWN') return 'red';
    if (t === 'SACK') return 'purple';
    if (t === 'INTERCEPTAÇÃO' || t === 'FUMBLE') return 'amber';
    if (t === 'JOGADA EXPLOSIVA') return 'green';
    if (t === 'BLITZ') return 'red';
    return 'blue';
  }

  function dotCard(p) {
    return '<div class="p-row"' + (p.name ? ' data-player="' + esc(p.nflId) + '" role="button" tabindex="0"' : '') + '>' +
      badge(teamOf(p.team), 'sm') +
      '<div class="nm"><b>' + esc(p.name || 'Posição genérica') + '</b><span>' +
        (isNum(p.jersey) ? '#' + p.jersey + ' · ' : '') + esc(p.position || '') +
        ' · ' + (p.side === 'defense' ? 'defesa' : 'ataque') + '</span></div>' +
      (p.name ? rateChip(p.rating) : '') + '</div>';
  }

  async function coachPlays() {
    await into('coachBody', async () => {
      await ensurePlays();
      if (!S.plays.length) return none('Sem jogadas neste jogo.');
      const byQ = {};
      S.plays.forEach((p) => { (byQ[p.quarter] = byQ[p.quarter] || []).push(p); });
      return Object.keys(byQ).sort().map((q) =>
        '<div class="sec-title">' + (q > 4 ? 'Prorrogação' : q + 'º quarto') +
        '<span class="sec-sub">' + byQ[q].length + ' jogadas</span></div>' +
        byQ[q].map(playRow).join('')).join('');
    }, 'Carregando as jogadas...');
  }

  function playRow(p) {
    let tone = '';
    if (p.tags.indexOf('TOUCHDOWN') >= 0) tone = 'td';
    else if (p.passResult === 'S') tone = 'sack';
    else if (p.passResult === 'IN' || p.tags.indexOf('FUMBLE') >= 0) tone = 'turnover';
    else if (p.result >= 20) tone = 'big';
    const gain = p.result > 0 ? 'pos' : p.result < 0 ? 'neg' : 'zero';
    return '<div class="play-row ' + tone + (p.playId === S.playId ? ' active' : '') + '" ' +
      'data-play="' + p.playId + '" role="button" tabindex="0">' +
      '<div class="play-head">' + badge(teamOf(p.offense), 'sm') +
        '<span class="sit">' + (isNum(p.down) ? ordDown(p.down, p.yardsToGo) : esc(p.passResultLabel)) + '</span>' +
        '<span class="clk">Q' + p.quarter + ' ' + esc(p.clock || '') + '</span>' +
        '<span class="spacer"></span>' +
        '<span class="gain ' + gain + '">' + signed(p.result) + '</span></div>' +
      '<div class="play-desc">' + esc(p.description) + '</div>' +
      '<div class="chips">' +
        (p.semFormacao ? '<span class="chip">SEM DADOS DE FORMAÇÃO</span>' : '') +
        (p.coverage ? '<span class="chip blue">' + esc(p.coverage) + '</span>' : '') +
        (p.formation ? '<span class="chip">' + esc(p.formation) + '</span>' : '') +
        (isNum(p.timeToThrow) ? '<span class="chip">' + secs(p.timeToThrow) + ' pocket</span>' : '') +
        (p.pressured ? '<span class="chip red">PRESSIONADO</span>' : '') +
        p.tags.map((t) => '<span class="chip ' + tagCls(t) + '">' + esc(t) + '</span>').join('') +
      '</div></div>';
  }

  function coachStats() {
    const g = S.game;
    if (!g) { $('coachBody').innerHTML = none('Escolha uma partida.'); return; }
    const A = g.away, H = g.home;
    const ao = g.teams.away.offense, ho = g.teams.home.offense;
    const ad = g.teams.away.defense, hd = g.teams.home.defense;
    if (!Object.keys(ao).length && !Object.keys(ho).length) {
      $('coachBody').innerHTML = none('Este jogo ainda não tem jogadas na fonte.');
      return;
    }

    // Linha só quando algum dos lados tem o dado (8.3).
    const cmp = (label, l, r, fmtFn, lowerBetter) => {
      if (!isNum(l) && !isNum(r)) return '';
      const lv = isNum(l) ? l : 0, rv = isNum(r) ? r : 0;
      const tot = Math.abs(lv) + Math.abs(rv);
      let lw = tot ? (Math.abs(lv) / tot) * 100 : 50;
      if (lowerBetter) lw = 100 - lw;
      return '<div class="cmp"><div class="cmp-label">' +
        '<span class="l">' + fmtFn(l) + '</span><span class="mid">' + label + '</span>' +
        '<span class="r">' + fmtFn(r) + '</span></div>' +
        '<div class="bar"><div class="fill-l" style="width:' + lw.toFixed(1) + '%"></div>' +
        '<div class="fill-r" style="width:' + (100 - lw).toFixed(1) + '%"></div></div></div>';
    };
    const terceira = (o) => (isNum(o.thirdDownAtt) ? o.thirdDownConv + '/' + o.thirdDownAtt : '—');
    const card = (titulo, linhas) => (linhas.join('') ? '<div class="card"><h4>' + titulo + '</h4>' + linhas.join('') + '</div>' : '');
    const pocket = [
      isNum(ao.timeToThrow) ? statRow('Tempo p/ lançar · ' + A.abbr, secs(ao.timeToThrow), delta(ao.timeToThrow, league().timeToThrow, true)) : '',
      isNum(ho.timeToThrow) ? statRow('Tempo p/ lançar · ' + H.abbr, secs(ho.timeToThrow), delta(ho.timeToThrow, league().timeToThrow, true)) : '',
      isNum(ao.pressureRateAllowed) ? statRow('Pressionado · ' + A.abbr, pct(ao.pressureRateAllowed), delta(ao.pressureRateAllowed, league().pressureRate, true, true)) : '',
      isNum(ho.pressureRateAllowed) ? statRow('Pressionado · ' + H.abbr, pct(ho.pressureRateAllowed), delta(ho.pressureRateAllowed, league().pressureRate, true, true)) : '',
    ];

    $('coachBody').innerHTML =
      card(esc(A.abbr) + ' vs ' + esc(H.abbr) + '<span class="sec-sub">ataque: passes e corridas</span>', [
        cmp('Jogadas', ao.plays, ho.plays, (v) => nm(v)),
        cmp('Jardas totais', ao.netYards, ho.netYards, (v) => nm(v)),
        cmp('Jardas de passe', ao.passYards, ho.passYards, (v) => nm(v)),
        cmp('Jardas correndo', ao.rushYards, ho.rushYards, (v) => nm(v)),
        cmp('Passes completos', ao.completions, ho.completions, (v) => nm(v)),
        cmp('Aproveitamento', ao.completionRate, ho.completionRate, (v) => pct(v)),
        cmp('Jd por jogada', ao.yardsPerPlay, ho.yardsPerPlay, (v) => nm(v, 1)),
        '<div class="cmp"><div class="cmp-label"><span class="l">' + terceira(ao) + '</span><span class="mid">3ª descida</span>' +
          '<span class="r">' + terceira(ho) + '</span></div></div>',
        cmp('Touchdowns', ao.touchdowns, ho.touchdowns, (v) => nm(v)),
        cmp('Jogadas explosivas', ao.explosive, ho.explosive, (v) => nm(v)),
        cmp('Turnovers', (ao.interceptions || 0) + (ao.fumblesLost || 0), (ho.interceptions || 0) + (ho.fumblesLost || 0), (v) => nm(v), true),
      ]) +
      card('Pressão e proteção', [
        cmp('Sacks aplicados', ad.sacks, hd.sacks, (v) => nm(v)),
        cmp('Pressões geradas', ad.pressures, hd.pressures, (v) => nm(v)),
        cmp('Taxa de pressão', ad.pressureRate, hd.pressureRate, (v) => pct(v)),
        cmp('Taxa de blitz', ad.blitzRate, hd.blitzRate, (v) => pct(v)),
        cmp('Interceptações', ad.interceptions, hd.interceptions, (v) => nm(v)),
      ]) +
      card('Relógio do pocket', pocket);
  }

  function statRow(k, v, extra) {
    return '<div class="stat-row"><span class="k">' + esc(k) + '</span>' +
      '<span class="v vs-league">' + v + (extra ? ' ' + extra : '') + '</span></div>';
  }

  function coachBook() {
    const g = S.game;
    if (!g) { $('coachBody').innerHTML = none('Escolha uma partida.'); return; }
    // Bloco sem dado nenhum fica fora (8.3): 2026 ainda não tem pessoal nem cobertura.
    const block = (title, sub, items, def) => (!items || !items.length ? '' :
      '<div class="card"><h4>' + esc(title) + '<span class="sec-sub">' + esc(sub) + '</span></h4>' +
      items.slice(0, 6).map((d) =>
        '<div class="tend"><div class="tend-top">' +
          '<span class="l">' + esc(d.label) + '</span>' +
          '<span class="r">' + pct(d.share) + ' · ' + d.plays + ' jogadas · ' +
            nm(d.yardsPerPlay, 1) + ' jd' +
            (isNum(d.completionRate) ? ' · ' + pct(d.completionRate) + ' comp' : '') + '</span>' +
        '</div><div class="tend-bar' + (def ? ' def' : '') + '"><span style="width:' +
          (d.share * 100).toFixed(1) + '%"></span></div></div>').join('') + '</div>');

    const t = g.tendencies;
    const html =
      block('Formações · ' + g.home.abbr, 'ataque', t.home.formations) +
      block('Coberturas · ' + g.home.abbr, 'defesa', t.home.coverages, true) +
      block('Formações · ' + g.away.abbr, 'ataque', t.away.formations) +
      block('Coberturas · ' + g.away.abbr, 'defesa', t.away.coverages, true) +
      block('Pessoal · ' + g.home.abbr, 'ataque', t.home.personnel) +
      block('Pessoal · ' + g.away.abbr, 'ataque', t.away.personnel);
    $('coachBody').innerHTML = html || none('Sem dados de formação neste jogo.');
  }

  /* =============================== CAMPO ================================ */
  const FIELD_W = 53.3;

  /**
   * Desenha e anima o tracking real. x do dataset (0–120) vai no eixo
   * vertical e y (0–53.3) no horizontal; quando playDirection é 'left' os
   * eixos são espelhados para o ataque sempre jogar para cima.
   */
  function Field(root, data) {
    this.root = root;
    this.data = data;
    this.flip = data.playDirection === 'left';
    this.frame = 0;
    this.speed = 1;
    this.timer = null;
    this.selected = null;
    this._viewport();
    this._marks();
    this._dots();
  }

  Field.prototype._viewport = function () {
    let min = Infinity, max = -Infinity;
    this.data.players.forEach((p) => p.t.forEach((f) => {
      if (!f) return;
      if (f[0] < min) min = f[0];
      if (f[0] > max) max = f[0];
    }));
    if (!isFinite(min)) { min = 20; max = 60; }
    const los = this.data.lineOfScrimmage;
    if (isNum(los)) { min = Math.min(min, los - 2); max = Math.max(max, los + 2); }
    min -= 2.5; max += 2.5;
    if (max - min < 26) { const c = (min + max) / 2; min = c - 13; max = c + 13; }
    this.xMin = Math.max(0, min);
    this.xMax = Math.min(120, max);
  };

  Field.prototype.pos = function (x, y) {
    const span = this.xMax - this.xMin || 1;
    const t = (x - this.xMin) / span;
    return {
      left: ((this.flip ? FIELD_W - y : y) / FIELD_W) * 100,
      top: (this.flip ? t : 1 - t) * 100,
    };
  };

  Field.prototype._marks = function () {
    const L = [];
    for (let x = Math.ceil(this.xMin / 5) * 5; x <= this.xMax; x += 5) {
      const top = this.pos(x, 0).top;
      const ten = (x - 10) % 10 === 0;
      const goal = x === 10 || x === 110;
      const yard = x - 10;
      L.push('<line x1="0" y1="' + top + '%" x2="100%" y2="' + top + '%" stroke="rgba(255,255,255,' +
        (goal ? 0.95 : ten ? 0.5 : 0.22) + ')" stroke-width="' + (goal ? 2.5 : ten ? 1.5 : 1) + '"/>');
      if (ten && yard > 0 && yard < 100) {
        const lbl = yard <= 50 ? yard : 100 - yard;
        L.push('<text x="6" y="' + top + '%" dy="-4" font-size="11" font-weight="700" ' +
          'fill="rgba(255,255,255,.6)" font-family="Barlow Condensed,sans-serif">' + lbl + '</text>');
        L.push('<text x="94%" y="' + top + '%" dy="-4" font-size="11" font-weight="700" ' +
          'fill="rgba(255,255,255,.6)" font-family="Barlow Condensed,sans-serif">' + lbl + '</text>');
      }
    }
    const los = this.data.lineOfScrimmage;
    if (isNum(los)) {
      L.push('<line x1="0" y1="' + this.pos(los, 0).top + '%" x2="100%" y2="' +
        this.pos(los, 0).top + '%" stroke="#3B82F6" stroke-width="2.5"/>');
      const ytg = this.data.yardsToGo;
      if (isNum(ytg)) {
        const fd = this.flip ? los - ytg : los + ytg;
        if (fd > this.xMin && fd < this.xMax) {
          L.push('<line x1="0" y1="' + this.pos(fd, 0).top + '%" x2="100%" y2="' +
            this.pos(fd, 0).top + '%" stroke="#FACC15" stroke-width="2" stroke-dasharray="7 5"/>');
        }
      }
    }
    this.root.innerHTML = '<svg class="marks" preserveAspectRatio="none" aria-hidden="true">' +
      L.join('') + '</svg>';
  };

  Field.prototype._dots = function () {
    this.dots = {};
    const self = this;
    this.data.players.forEach((p) => {
      const def = p.side === 'defense';
      const d = document.createElement('div');
      d.className = 'player-dot' + (p.role === 'Pass' ? ' qb' : '');
      d.style.background = teamOf(p.team).primary;
      if (def) d.style.borderRadius = '7px';
      d.setAttribute('role', 'button');
      d.setAttribute('tabindex', '0');
      d.title = (p.name || '') + ' · ' + (p.linedUp || p.position || '') + ' · #' + (p.jersey || '');
      d.setAttribute('aria-label', d.title);
      d.innerHTML = '<span class="num">' + (p.jersey || '') + '</span>';
      const pick = () => self.select(p.nflId);
      d.addEventListener('click', pick);
      d.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); }
      });
      self.root.appendChild(d);
      self.dots[p.nflId] = d;
    });
    this.ball = document.createElement('div');
    this.ball.className = 'player-dot ball';
    this.ball.setAttribute('aria-hidden', 'true');
    this.root.appendChild(this.ball);
  };

  Field.prototype.setFrame = function (i) {
    const d = this.data;
    this.frame = Math.max(0, Math.min(d.frameCount - 1, i));
    for (let k = 0; k < d.players.length; k++) {
      const p = d.players[k];
      const f = p.t[this.frame];
      const dot = this.dots[p.nflId];
      if (!dot) continue;
      if (!f) { dot.style.display = 'none'; continue; }
      dot.style.display = '';
      const q = this.pos(f[0], f[1]);
      dot.style.left = q.left + '%';
      dot.style.top = q.top + '%';
    }
    const b = d.ball[this.frame];
    if (b) {
      const q = this.pos(b[0], b[1]);
      this.ball.style.display = '';
      this.ball.style.left = q.left + '%';
      this.ball.style.top = q.top + '%';
    } else this.ball.style.display = 'none';
    if (this.onFrame) this.onFrame(this.frame);
  };

  Field.prototype.select = function (id) {
    this.selected = this.selected === id ? null : id;
    const sel = this.selected;
    Object.keys(this.dots).forEach((k) => {
      this.dots[k].classList.toggle('selected', Number(k) === sel);
      this.dots[k].classList.toggle('dim', sel !== null && Number(k) !== sel);
    });
    if (this.onSelect) {
      this.onSelect(sel === null ? null : this.data.players.filter((p) => p.nflId === sel)[0]);
    }
  };

  Field.prototype.play = function () {
    if (this.timer) return;
    if (this.frame >= this.data.frameCount - 1) this.setFrame(0);
    const self = this;
    this.timer = setInterval(() => {
      if (self.frame >= self.data.frameCount - 1) return self.pause();
      self.setFrame(self.frame + 1);
    }, 100 / this.speed);
    if (this.onState) this.onState(true);
  };

  Field.prototype.pause = function () {
    clearInterval(this.timer);
    this.timer = null;
    if (this.onState) this.onState(false);
  };

  Field.prototype.toggle = function () { this.timer ? this.pause() : this.play(); };
  Field.prototype.setSpeed = function (s) {
    this.speed = s;
    if (this.timer) { this.pause(); this.play(); }
  };
  Field.prototype.clockAt = function (i) {
    return ((i === undefined ? this.frame : i) - (this.data.snapIndex || 0)) / (this.data.fps || 10);
  };

  /* ============================== OLHEIRO =============================== */
  const POS_GROUPS = [
    { k: '', l: 'Todos' },
    { k: 'QB', l: 'QB' },
    { k: 'WR', l: 'WR' },
    { k: 'TE', l: 'TE' },
    { k: 'RB,FB', l: 'RB' },
    { k: 'T,G,C,OL', l: 'Linha of.' },
    { k: 'DE,OLB', l: 'Edge' },
    { k: 'DT,NT,DL', l: 'Linha def.' },
    { k: 'ILB,MLB,LB', l: 'LB' },
    { k: 'CB', l: 'CB' },
    { k: 'FS,SS,S,SAF,DB', l: 'Safety' },
  ];

  function renderScout() {
    $('scoutSub').textContent = 'Temporada ' + S.season + ' · estatísticas públicas (nflverse)';
    $('scoutFilters').innerHTML = POS_GROUPS.map((g) =>
      '<button class="filter' + (g.k === S.scoutPos ? ' active' : '') + '" data-pos="' +
      esc(g.k) + '">' + esc(g.l) + '</button>').join('');
    if (S.playerId) return scoutDetail();
    return scoutList();
  }

  async function scoutList() {
    const my = ++seq.scout;
    await into('scoutBody', async () => {
      const list = await api.players({ position: S.scoutPos, q: S.scoutQuery, limit: 60 });
      if (!list.length) return none('Nenhum jogador com amostra suficiente para esse filtro.');
      return '<div class="sec-title">' + list.length + ' jogadores' +
        '<span class="sec-sub">temporada ' + S.season + ' · ordenados por rating</span></div>' +
        '<div class="p-list">' + list.map((p) =>
          '<div class="p-row" data-player="' + esc(p.nflId) + '" role="button" tabindex="0">' +
          badge(teamOf(p.team), 'sm') +
          '<div class="nm"><b>' + esc(p.name) + '</b><span>' + esc(p.position) + ' · ' +
            esc(p.roleLabel) + ' · ' + nm(p.snaps) + ' snaps · ' + nm(p.games) + ' jogos</span></div>' +
          rateChip(p.rating) + '</div>').join('') + '</div>';
    }, 'Buscando jogadores...', () => my === seq.scout);
  }

  async function scoutDetail() {
    const my = ++seq.scout;
    const desenhou = await into('scoutBody', async () => {
      let p;
      try {
        p = await api.player(S.playerId);
      } catch (e) {
        return '<div class="row" style="padding:12px 16px 0"><button class="ev-chip" id="backList">‹ voltar à lista</button></div>' +
          none('Este jogador não tem dados na temporada ' + S.season + '.');
      }
      const r = p.roles[0];
      const t = teamOf(p.team);
      let html =
        '<div class="row" style="padding:12px 16px 0"><button class="ev-chip" id="backList">‹ voltar à lista</button></div>' +
        '<div class="card"><div class="scout-hero">' +
          '<div class="scout-avatar" style="background:' + esc(t.primary) + '">' +
            esc(p.position || '') + '</div>' +
          '<div class="info"><h3>' + esc(p.name) + '</h3>' +
            '<div class="meta">' + esc(p.position) + ' · ' + esc(t.name) + ' · ' + p.season +
              (isNum(p.age) ? ' · ' + p.age + ' anos' : '') + '</div>' +
            '<span class="rating-badge">' + (isNum(p.rating) ? p.rating : 'n/d') + '</span>' +
            ' <span class="muted" style="font-size:11px">' + esc(p.roleLabel) + '</span>' +
          '</div></div>' +
          '<div class="bio">' +
            bioBox('Altura', p.height) + bioBox('Peso', isNum(p.weight) ? p.weight + ' lb' : null) +
            bioBox('Faculdade', p.college) + bioBox('Jogos', isNum(p.games) ? String(p.games) : null) +
          '</div></div>';

      if (r) {
        html += '<div class="card"><h4>Radar de atributos' +
          '<span class="sec-sub">Percentil no grupo ' + esc(r.roleLabel) + ', temporada ' + p.season + '</span></h4>' +
          (r.baseReduzida ? '<div class="aviso-ilustrativo" style="margin-bottom:8px">O rating da linha ofensiva usa menos ' +
            'estatísticas que os demais grupos: 2 dos 4 eixos são do time, nos jogos em que ele atuou.</div>' : '') +
          '<div id="radarSlot">' + radarBlock(r) + '</div></div>';

        html += '<div class="card"><h4>Números da temporada</h4><div id="statSlot">' +
          r.stats.map((s) => '<div class="stat-row"><span class="k">' + esc(s.label) +
            '</span><span class="v">' + nm(s.value, s.value % 1 ? 1 : 0) +
            (s.unit ? ' <small>' + esc(s.unit) + '</small>' : '') + '</span></div>').join('') +
          '</div></div>';
      }

      if (p.positionsLinedUp && p.positionsLinedUp.length) {
        html += '<div class="card"><h4>Onde ele se alinha</h4>' +
          p.positionsLinedUp.map((x) => '<div class="tend"><div class="tend-top">' +
            '<span class="l">' + esc(x.position) + '</span><span class="r">' + x.snaps +
            ' snaps · ' + pct(x.share) + '</span></div>' +
            '<div class="tend-bar"><span style="width:' + (x.share * 100).toFixed(1) +
            '%"></span></div></div>').join('') + '</div>';
      }

      if (p.gameLog.length) {
        html += '<div class="card"><h4>Jogo a jogo<span class="sec-sub">temporada ' + p.season + '</span></h4>' +
          p.gameLog.map((g) => '<div class="stat-row"><span class="k">' +
            esc(g.rodada && g.rodada.indexOf('Semana') !== 0 ? g.rodada : 'Sem ' + g.week) +
            ' · vs ' + esc(g.opponent || '—') + '</span><span class="v" style="font-size:12px">' +
            (isNum(g.snaps) ? g.snaps + ' snaps' : '') +
            (g.stats || []).filter((s) => s.label.indexOf('Snaps') !== 0 && s.value).slice(0, 3)
              .map((s) => ' · ' + nm(s.value, s.value % 1 ? 1 : 0) + ' ' + esc(s.label.toLowerCase())).join('') +
            '</span></div>').join('') + '</div>';
      }

      html += '<div class="card"><h4>Comparar<span class="sec-sub">mesmo grupo e temporada</span></h4>' +
        '<div class="cmp-pick"><select id="cmpPick" aria-label="Comparar com"><option value="">Escolha um jogador...</option></select></div>' +
        '<div id="cmpSlot"></div></div>';

      if (my === seq.scout) S._roles = p.roles;
      return html;
    }, 'Carregando o perfil...', () => my === seq.scout);

    if (desenhou) fillComparePicker();
  }

  function bioBox(k, v) {
    return '<div><div class="k">' + esc(k) + '</div><div class="v">' + esc(v || '—') + '</div></div>';
  }

  function radarBlock(r) {
    if (!r.rated) {
      return '<div class="state">Rating n/d: abaixo do volume mínimo do grupo nesta temporada' +
        (isNum(r.volume) && isNum(r.minimo) ? ' (' + r.volume + ' de ' + r.minimo + ')' : '') + '.</div>';
    }
    const comDado = r.radar.filter((a) => isNum(a.percentile));
    const semDado = r.radar.filter((a) => !isNum(a.percentile));
    return '<div class="radar-wrap">' + radarSVG(comDado) + '</div>' +
      '<div class="attr-list">' + comDado.map((a) =>
        '<div class="attr"><span class="name">' + esc(a.label) + (a.lowerIsBetter ? ' ↓' : '') + '</span>' +
        '<span class="track"><span class="val-fill" style="width:' +
          Math.max(2, a.percentile || 0) + '%"></span></span>' +
        '<span class="val">' + nm(a.value, a.value % 1 ? (a.unit === '%' || a.unit === 'pp' ? 1 : 2) : 0) +
          (a.unit === '%' ? '%' : a.unit === 'pp' ? ' pp' : '') + '</span>' +
        '<span class="pctl">p' + nm(a.percentile) + '</span></div>').join('') + '</div>' +
      // 5.5: o eixo sem estatística na temporada fica fora do radar e da média, com o motivo.
      semDado.map((a) => '<div class="motivo">' + esc(a.label) + ': ' + esc(a.motivo || 'sem dado') + '</div>').join('') +
      '<div class="muted" style="font-size:10.5px;margin-top:6px">' +
      'A barra mostra o percentil; o número é o valor real do jogador. ↓ = menor é melhor.</div>';
  }

  function radarSVG(axes) {
    const n = axes.length;
    if (!n) return '';
    const size = 208, cx = size / 2, cy = size / 2 + 2, R = size * 0.36;
    const pt = (i, rr) => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2;
      return [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr];
    };
    const ring = (f) => axes.map((_, i) => pt(i, R * f).map((v) => v.toFixed(1)).join(',')).join(' ');
    let s = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size +
      '" role="img" aria-label="Radar de atributos">';
    [1, 0.66, 0.33].forEach((f) => {
      s += '<polygon points="' + ring(f) + '" fill="none" stroke="#E4E7EC"/>';
    });
    axes.forEach((_, i) => {
      const q = pt(i, R);
      s += '<line x1="' + cx + '" y1="' + cy + '" x2="' + q[0].toFixed(1) + '" y2="' +
        q[1].toFixed(1) + '" stroke="#E4E7EC"/>';
    });
    const data = axes.map((a, i) =>
      pt(i, R * (Math.max(6, Math.min(100, a.percentile || 0)) / 100)).map((v) => v.toFixed(1)).join(',')
    ).join(' ');
    s += '<polygon points="' + data + '" fill="rgba(213,10,10,.22)" stroke="#D50A0A" stroke-width="2"/>';
    axes.forEach((a, i) => {
      const q = pt(i, R * (Math.max(6, Math.min(100, a.percentile || 0)) / 100));
      s += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="2.6" fill="#D50A0A"/>';
      const lp = pt(i, R + 16);
      const anchor = lp[0] < cx - 6 ? 'end' : lp[0] > cx + 6 ? 'start' : 'middle';
      s += '<text x="' + lp[0].toFixed(1) + '" y="' + (lp[1] + 3).toFixed(1) + '" font-size="9.5" ' +
        'text-anchor="' + anchor + '" fill="#667085">' + esc(a.label) + '</text>';
    });
    return s + '</svg>';
  }

  async function fillComparePicker() {
    const sel = $('cmpPick');
    if (!sel || !S._roles || !S._roles.length) return;
    try {
      const role = S._roles[0].role;
      const peers = await api.players({ role: role, limit: 60 });
      sel.innerHTML = '<option value="">Escolha um jogador...</option>' +
        peers.filter((p) => p.nflId !== S.playerId).map((p) =>
          '<option value="' + esc(p.nflId) + '">' + esc(p.name) + ' · ' + esc(p.team) +
          ' · ' + (isNum(p.rating) ? p.rating : 'n/d') + '</option>').join('');
    } catch (e) { /* comparacao e opcional */ }
  }

  async function showCompare(otherId) {
    const slot = $('cmpSlot');
    slot.innerHTML = spin('Comparando...');
    try {
      const c = await api.compare(S.playerId, otherId);
      if (!c.rows.length) { slot.innerHTML = none('Funções diferentes: não há métricas comuns.'); return; }
      slot.innerHTML =
        '<div class="row" style="justify-content:space-between;margin-bottom:10px">' +
          '<b style="font-size:12px;color:var(--nfl-blue)">' + esc(c.left.name) + '</b>' +
          '<span class="muted" style="font-size:11px">' + esc(c.roleLabel || '') + '</span>' +
          '<b style="font-size:12px;color:var(--nfl-red)">' + esc(c.right.name) + '</b></div>' +
        c.rows.map((r) => {
          const l = isNum(r.left) ? r.left : 0, rr = isNum(r.right) ? r.right : 0;
          const tot = Math.abs(l) + Math.abs(rr);
          const lw = tot ? (Math.abs(l) / tot) * 100 : 50;
          return '<div class="cmp"><div class="cmp-label">' +
            '<span class="l">' + nm(r.left, r.left % 1 ? 1 : 0) + '</span>' +
            '<span class="mid">' + esc(r.label) + (r.unit ? ' (' + esc(r.unit) + ')' : '') + '</span>' +
            '<span class="r">' + nm(r.right, r.right % 1 ? 1 : 0) + '</span></div>' +
            '<div class="bar"><div class="fill-l" style="width:' + lw.toFixed(1) + '%"></div>' +
            '<div class="fill-r" style="width:' + (100 - lw).toFixed(1) + '%"></div></div></div>';
        }).join('');
    } catch (e) { slot.innerHTML = oops(e.message); }
  }

  /* ============================ COMENTARISTA ============================ */
  async function renderBroadcast() {
    if (!S.gameId) { $('bcBody').innerHTML = none('Escolha uma partida na aba Jogos.'); return; }
    const body = $('bcBody');
    body.innerHTML = spin('Montando a transmissão...');
    try {
      try {
        S.bc = await api.broadcast(S.gameId);
      } catch (e) {
        body.innerHTML = none('Este jogo ainda não tem jogadas na fonte.');
        return;
      }
      $('bcSub').textContent = S.bc.away.abbr + ' @ ' + S.bc.home.abbr + ' · ' +
        S.bc.feed.length + ' jogadas';
      body.innerHTML =
        '<div id="bcScore"></div>' +
        '<div class="bc-bar">' +
          '<button id="bcPlay" aria-label="Reproduzir narração">▶</button>' +
          '<input type="range" id="bcRange" min="0" max="' + (S.bc.feed.length - 1) + '" value="0" aria-label="Posição no jogo" />' +
          '<span class="pos" id="bcPos">1/' + S.bc.feed.length + '</span>' +
        '</div>' +
        '<div class="sec-title">Narração <span class="sec-sub">jogada a jogada</span></div>' +
        '<div class="timeline" id="bcFeed"></div>' +
        '<div class="card"><h4>Painel acumulado<span class="sec-sub">até a jogada atual</span></h4>' +
          '<div id="bcPanel"></div></div>';
      S.bcIndex = 0;
      paintBc();
    } catch (e) {
      body.innerHTML = oops('Falha na transmissão: ' + e.message);
    }
  }

  function paintBc() {
    const bc = S.bc;
    const i = S.bcIndex;
    const p = bc.feed[i];
    const hs = p.score.home, as = p.score.away;

    $('bcScore').innerHTML =
      '<div class="live-score">' +
        '<div>' + badge(bc.away, 'lg') + '<div class="big' + (as > hs ? ' lead' : '') + '">' +
          nm(as) + '</div><div class="nm">' + esc(bc.away.nick || bc.away.abbr) + '</div></div>' +
        '<div><div class="qtr">' + (p.quarter > 4 ? 'PRORROG.' : 'Q' + p.quarter) + ' · ' + esc(p.clock || '') + '</div>' +
          '<div class="situ">' + esc(p.offense || '') + ' com a bola<br>' +
            (isNum(p.down) ? ordDown(p.down, p.yardsToGo) : esc(p.passResultLabel || '')) + '</div></div>' +
        '<div>' + badge(bc.home, 'lg') + '<div class="big' + (hs > as ? ' lead' : '') + '">' +
          nm(hs) + '</div><div class="nm">' + esc(bc.home.nick || bc.home.abbr) + '</div></div>' +
      '</div>';

    $('bcPos').textContent = (i + 1) + '/' + bc.feed.length;
    $('bcRange').value = i;

    // Mostra as ultimas jogadas, a atual no topo.
    const from = Math.max(0, i - 11);
    $('bcFeed').innerHTML = bc.feed.slice(from, i + 1).reverse().map((q, k) =>
      '<div class="tl-item ' + esc(q.narration.tone) + (k === 0 ? ' now' : '') + '">' +
        '<span class="time">' + esc(q.clock || '') + '</span>' +
        '<span class="ev"><b>' + esc(q.narration.icon) + ' ' + esc(q.narration.headline) + '</b>' +
        esc(q.narration.detail) +
        (q.narration.context ? '<span class="ctx">' + esc(q.narration.context) + '</span>' : '') +
        '</span></div>').join('');

    const ch = p.cumulative.home, ca = p.cumulative.away;
    const bar = (label, l, r, f) => {
      const lv = isNum(l) ? l : 0, rv = isNum(r) ? r : 0;
      const tot = Math.abs(lv) + Math.abs(rv);
      const lw = tot ? (Math.abs(lv) / tot) * 100 : 50;
      return '<div class="cmp"><div class="cmp-label"><span class="l">' + f(l) +
        '</span><span class="mid">' + label + '</span><span class="r">' + f(r) + '</span></div>' +
        '<div class="bar"><div class="fill-l" style="width:' + lw.toFixed(1) + '%"></div>' +
        '<div class="fill-r" style="width:' + (100 - lw).toFixed(1) + '%"></div></div></div>';
    };
    $('bcPanel').innerHTML =
      '<div class="row" style="justify-content:space-between;margin-bottom:8px">' +
        '<b style="font-size:12px;color:var(--nfl-blue)">' + esc(bc.away.abbr) + '</b>' +
        '<b style="font-size:12px;color:var(--nfl-red)">' + esc(bc.home.abbr) + '</b></div>' +
      bar('Jogadas', ca.plays, ch.plays, (v) => nm(v)) +
      bar('Jardas', ca.yards, ch.yards, (v) => nm(v)) +
      bar('Passes completos', ca.completions, ch.completions, (v) => nm(v)) +
      bar('Touchdowns', ca.touchdowns, ch.touchdowns, (v) => nm(v)) +
      bar('Sacks sofridos', ca.sacksTaken, ch.sacksTaken, (v) => nm(v)) +
      // Pressões só existem onde a fonte traz (participação até 2025).
      (ca.pressures || ch.pressures ? bar('Pressões da defesa', ca.pressures, ch.pressures, (v) => nm(v)) : '');
  }

  function bcStep(n) {
    if (!S.bc) return;
    S.bcIndex = Math.max(0, Math.min(S.bc.feed.length - 1, n));
    paintBc();
    if (S.bcIndex >= S.bc.feed.length - 1) stopBc();
  }

  function toggleBc() {
    if (S.bcTimer) return stopBc();
    if (S.bcIndex >= S.bc.feed.length - 1) S.bcIndex = 0;
    S.bcTimer = setInterval(() => bcStep(S.bcIndex + 1), 1400);
    $('bcPlay').textContent = '❚❚';
  }

  function stopBc() {
    clearInterval(S.bcTimer);
    S.bcTimer = null;
    const b = $('bcPlay');
    if (b) b.textContent = '▶';
  }

  /* ============================== EVENTOS =============================== */
  document.addEventListener('click', async (e) => {
    const t = e.target;

    const nav = t.closest('[data-go]');
    if (nav) { go(nav.dataset.go); return; }

    const wk = t.closest('[data-week]');
    if (wk) {
      S.week = Number(wk.dataset.week);
      await mudarSemana();
      return;
    }

    const gm = t.closest('[data-game]');
    if (gm) { await selectGame(gm.dataset.game); return; }

    const tab = t.closest('#coachTabs .subtab');
    if (tab) { S.coachTab = tab.dataset.tab; renderCoach(); return; }

    const pr = t.closest('[data-play]');
    if (pr) {
      S.playId = Number(pr.dataset.play);
      S.coachTab = 'lineup';
      go('coach');
      return;
    }

    if (t.closest('#btnPlay')) { FV && FV.toggle(); return; }
    const sp = t.closest('[data-sp]');
    if (sp) {
      document.querySelectorAll('#speedPick button').forEach((b) => b.classList.remove('active'));
      sp.classList.add('active');
      FV && FV.setSpeed(Number(sp.dataset.sp));
      return;
    }
    const ev = t.closest('[data-frame]');
    if (ev) {
      document.querySelectorAll('#evStrip .ev-chip').forEach((b) => b.classList.remove('active'));
      ev.classList.add('active');
      FV && (FV.pause(), FV.setFrame(Number(ev.dataset.frame)));
      return;
    }
    if (t.closest('#prevPlay') || t.closest('#nextPlay')) {
      // Anterior/próxima andam entre as jogadas com formação (os chutes ficam no seletor).
      const list = S.plays.filter((p) => p.hasFormation || p.playId === S.playId);
      let idx = list.findIndex((p) => p.playId === S.playId);
      idx += t.closest('#nextPlay') ? 1 : -1;
      if (idx >= 0 && idx < list.length) { S.playId = list[idx].playId; coachLineup(); }
      return;
    }

    const pl = t.closest('[data-player]');
    if (pl) {
      S.playerId = pl.dataset.player;    // id gsis em texto (00-0033077)
      go('scout');
      return;
    }
    if (t.closest('#backList')) { S.playerId = null; renderScout(); return; }

    const pos = t.closest('[data-pos]');
    if (pos) { S.scoutPos = pos.dataset.pos; S.playerId = null; renderScout(); return; }

    const rt = t.closest('[data-role]');
    if (rt) {
      document.querySelectorAll('.role-tab').forEach((b) => b.classList.remove('active'));
      rt.classList.add('active');
      const r = S._roles[Number(rt.dataset.role)];
      $('radarSlot').innerHTML = radarBlock(r);
      $('statSlot').innerHTML = r.stats.map((s) => '<div class="stat-row"><span class="k">' +
        esc(s.label) + '</span><span class="v">' + nm(s.value, s.value % 1 ? 1 : 0) +
        (s.unit ? ' <small>' + esc(s.unit) + '</small>' : '') + '</span></div>').join('');
      return;
    }

    if (t.closest('#bcPlay')) { toggleBc(); return; }
    if (t.closest('#backBtn')) { go('home'); return; }
    if (t.closest('#btnInfo')) {
      go('home');
      $('sobreDados').scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
  });

  // Enter/espaco nos elementos com role=button
  document.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.getAttribute('role') === 'button'
        && !e.target.classList.contains('player-dot')) {
      e.preventDefault();
      e.target.click();
    }
  });

  document.addEventListener('input', (e) => {
    if (e.target.id === 'frameRange') { FV && (FV.pause(), FV.setFrame(Number(e.target.value))); }
    if (e.target.id === 'bcRange') { stopBc(); bcStep(Number(e.target.value)); }
  });

  async function mudarSemana() {
    renderWeeks();
    S.gameId = null;
    S.game = null;
    renderMateria();
    await renderGames();
    if (S.games.length) await selectGame(S.games[0].gameId);
  }

  document.addEventListener('change', async (e) => {
    if (e.target.id === 'playPick') { S.playId = Number(e.target.value); coachLineup(); }
    if (e.target.id === 'cmpPick' && e.target.value) { showCompare(e.target.value); }
    if (e.target.id === 'seasonPick') {
      S.season = Number(e.target.value);
      S.week = semanaPadrao(S.season);
      S.playerId = null;
      $('hdrSub').textContent = subtituloHome();
      await mudarSemana();
    }
  });

  let searchTimer = null;
  document.addEventListener('keyup', (e) => {
    if (e.target.id !== 'scoutSearch') return;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      S.scoutQuery = e.target.value.trim();
      S.playerId = null;
      scoutList();
    }, 280);
  });

  /* =============================== BOOT ================================= */
  (async function boot() {
    const u = new URLSearchParams(location.search);
    try {
      S.meta = await api.meta();
    } catch (e) {
      document.querySelector('.app').insertAdjacentHTML('afterbegin',
        '<div class="disclaimer" style="border-color:var(--nfl-red)"><b>API indisponível.</b><br>' +
        'Rode <code>python server/serve.py</code> (ou o RODAR.bat) e abra http://127.0.0.1:8000 — ' +
        'a página precisa do servidor para ler os dados.<br>Detalhe: ' + esc(e.message) + '</div>');
      $('hdrSub').textContent = 'Sem conexão com a API';
      return;
    }
    // Deep link opcional: ?season=2021&week=3&game=2021092300&screen=coach
    const wantSeason = Number(u.get('season'));
    const wantWeek = Number(u.get('week'));
    const wantGame = Number(u.get('game'));
    const wantScreen = u.get('screen');

    S.season = S.meta.seasons.some((t) => t.season === wantSeason) ? wantSeason : S.meta.season;
    S.week = temporadaMeta().weeks.some((w) => w.week === wantWeek) ? wantWeek : semanaPadrao(S.season);
    renderSobre();
    renderSeasons();
    renderWeeks();
    $('hdrSub').textContent = subtituloHome();
    await renderGames();

    const pick = S.games.some((g) => g.gameId === wantGame) ? wantGame
      : S.games.length ? S.games[0].gameId : null;
    if (pick) await selectGame(pick);
    if (wantScreen && TITLES[wantScreen]) go(wantScreen);
  })();
})();
