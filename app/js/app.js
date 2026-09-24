/* ==========================================================================
   NFL GAMES — protótipo ligado ao dataset NFL Big Data Bowl 2023.
   Lê tudo da API local (server/serve.py). Nenhum dado é inventado aqui.
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
    games: (p) => get('/api/games' + qs(p || {})),
    game: (g) => get('/api/games/' + g),
    plays: (g) => get('/api/games/' + g + '/plays'),
    tracking: (g, p) => get('/api/games/' + g + '/plays/' + p + '/tracking'),
    broadcast: (g) => get('/api/games/' + g + '/broadcast'),
    players: (p) => get('/api/players' + qs(p || {})),
    player: (id) => get('/api/players/' + id),
    compare: (a, b) => get('/api/compare' + qs({ a: a, b: b })),
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
  function brDate(s) {
    if (!s) return '';
    const a = s.split('/');
    return a[1] + '/' + a[0];
  }
  function weekday(s) {
    if (!s) return '';
    const a = s.split('/');
    const d = new Date(a[2] + '-' + a[0] + '-' + a[1] + 'T12:00:00');
    return ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB'][d.getDay()];
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
  const seq = { play: 0, scout: 0 };

  /* ------------------------------ estado -------------------------------- */
  const S = {
    meta: null, week: null, games: [], gameId: null, game: null,
    plays: [], playId: null, coachTab: 'lineup',
    scoutPos: '', scoutQuery: '', playerId: null, compareId: null,
    bc: null, bcIndex: 0, bcTimer: null,
  };
  const teamOf = (a) => (S.meta && S.meta.teams[a]) || { abbr: a, primary: '#013369', name: a };
  const league = () => (S.meta ? S.meta.league : {});

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
      $('hdrSub').textContent = S.meta
        ? 'Temporada ' + S.meta.season + ' · semanas 1–8 · ' + S.meta.counts.plays.toLocaleString('pt-BR') + ' jogadas'
        : '';
    } else {
      $('hdrSub').textContent = S.game
        ? S.game.away.abbr + ' @ ' + S.game.home.abbr + ' · semana ' + S.game.week
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
  function renderWeeks() {
    $('weekChips').innerHTML = S.meta.weeks.map((w) =>
      '<button class="week-chip' + (w.week === S.week ? ' active' : '') + '" data-week="' + w.week + '">' +
      'SEM ' + w.week + '<small>' + w.games + ' jogos</small></button>').join('');
  }

  async function renderGames() {
    await into('gamesList', async () => {
      S.games = await api.games({ week: S.week });
      if (!S.games.length) return none('Nenhum jogo nesta semana.');
      $('gamesCount').textContent = S.games.length + ' jogos na semana ' + S.week;
      return S.games.map(gameCard).join('');
    }, 'Carregando partidas da semana ' + S.week + '...');
  }

  function gameCard(g) {
    const hw = isNum(g.home.score) && isNum(g.away.score) && g.home.score > g.away.score;
    const aw = isNum(g.home.score) && isNum(g.away.score) && g.away.score > g.home.score;
    return '<div class="match' + (g.gameId === S.gameId ? ' selected' : '') + '" data-game="' + g.gameId + '" ' +
      'role="button" tabindex="0" aria-label="' + esc(g.away.abbr + ' contra ' + g.home.abbr) + '">' +
      '<div class="team">' + badge(g.away) + '<span class="name">' + esc(g.away.nick || g.away.abbr) + '</span></div>' +
      '<div class="center"><div class="score">' +
        '<span style="' + (aw ? '' : 'opacity:.55') + '">' + nm(g.away.score) + '</span>' +
        '<span class="sep">–</span>' +
        '<span style="' + (hw ? '' : 'opacity:.55') + '">' + nm(g.home.score) + '</span>' +
      '</div>' +
      '<div class="status">' + weekday(g.date) + ' ' + brDate(g.date) +
        (g.overtime ? ' <span class="badge-ot">PRORROG.</span>' : '') + '</div>' +
      '<div class="meta-line">' + g.dropbacks + ' dropbacks · ' + g.sacks + ' sacks</div>' +
      '</div>' +
      '<div class="team">' + badge(g.home) + '<span class="name">' + esc(g.home.nick || g.home.abbr) + '</span></div>' +
      '</div>';
  }

  async function selectGame(gameId) {
    S.gameId = Number(gameId);
    S.playId = null;
    S.plays = [];
    S.bc = null;
    S.bcIndex = 0;
    document.querySelectorAll('.match').forEach((m) =>
      m.classList.toggle('selected', Number(m.dataset.game) === S.gameId));
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

  function renderInsights() {
    const list = (S.game && S.game.insights) || [];
    $('insightsList').innerHTML = list.length
      ? list.map((c) =>
          '<div class="tip-card ' + esc(c.tone) + '" data-go="coach">' +
          '<div class="tip-ic ' + esc(c.tone) + '">' + esc(c.icon) + '</div>' +
          '<div class="tip-body">' +
            '<div class="tip-title"><span class="tip-team" style="background:' +
              esc(teamOf(c.team).primary) + '">' + esc(c.team) + '</span>' + esc(c.title) + '</div>' +
            '<div class="tip-text">' + esc(c.text) + '</div>' +
          '</div>' +
          (c.metric ? '<div class="tip-metric"><div class="v">' + esc(c.metric.value) +
            '</div><div class="k">' + esc(c.metric.label) + '</div></div>' : '') +
          '</div>').join('')
      : none('Selecione uma partida para ver as leituras táticas.');
  }

  function renderWatch() {
    const list = (S.game && S.game.watch) || [];
    $('watchList').innerHTML = list.length
      ? '<div class="watch-scroll">' + list.map((p) =>
          '<div class="watch-card" data-player="' + p.nflId + '" role="button" tabindex="0">' +
          '<div class="watch-avatar" style="background:' + esc(teamOf(p.team).primary) + '">' +
            esc((p.position || '').slice(0, 3)) + '</div>' +
          '<div class="watch-name">' + esc(shortName(p.name)) + '</div>' +
          '<div class="watch-pos">' + esc(p.position || '') + ' · ' + esc(p.team || '') + '</div>' +
          '<div class="watch-pos muted" style="font-size:10px">' + esc(p.roleLabel) + '</div>' +
          '<span class="watch-rating">' + (isNum(p.rating) ? p.rating : '—') + '</span>' +
          '</div>').join('') + '</div>'
      : none('Sem destaques para esta partida.');
  }

  function renderNotes() {
    const list = (S.game && S.game.notes) || [];
    $('notesList').innerHTML = list.length
      ? list.map((n) =>
          '<div class="news-card"><div class="news-ic">' + esc(n.icon) + '</div>' +
          '<div class="news-body"><div class="news-title">' + esc(n.title) + '</div>' +
          '<div class="news-text">' + esc(n.text) + '</div></div></div>').join('')
      : none('Sem bastidores para esta partida.');
  }

  function shortName(n) {
    if (!n) return '';
    const p = n.split(' ');
    return p.length > 1 ? p[0][0] + '. ' + p.slice(1).join(' ') : n;
  }

  function renderDatasetNote() {
    const d = S.meta.dataset;
    $('datasetNote').innerHTML = '<b>' + esc(d.name) + '</b> — ' + esc(d.scope) +
      '<ul>' + d.caveats.map((c) => '<li>' + esc(c) + '</li>').join('') + '</ul>';
  }

  /* ============================= TREINADOR ============================== */
  function renderCoach() {
    if (!S.gameId) { $('coachBody').innerHTML = none('Escolha uma partida na aba Jogos.'); return; }
    $('coachSub').textContent = S.game
      ? S.game.away.abbr + ' @ ' + S.game.home.abbr + ' · ' + S.game.dropbacks + ' dropbacks'
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
      const first = S.plays.filter((p) => p.hasTracking)[0];
      S.playId = first ? first.playId : null;
    }
    return S.plays;
  }

  async function coachLineup() {
    const my = ++seq.play;
    const body = $('coachBody');
    body.innerHTML = spin('Carregando tracking da jogada...');
    try {
      await ensurePlays();
      if (my !== seq.play) return; // o usuário já escolheu outra jogada
      if (!S.playId) { body.innerHTML = none('Sem tracking disponível neste jogo.'); return; }

      body.innerHTML =
        '<div class="card">' +
          '<h4>Prancheta tática<span class="sec-sub" id="fieldSub"></span></h4>' +
          '<div class="field-legend">' +
            '<span><i class="sw" style="background:#fff;border-radius:50%"></i>Ataque (círculo)</span>' +
            '<span><i class="sw" style="background:#fff"></i>Defesa (quadrado)</span>' +
            '<span><i class="sw" style="background:#3B82F6"></i>Linha de scrimmage</span>' +
            '<span><i class="sw" style="background:#FACC15"></i>1ª descida</span>' +
          '</div>' +
          '<div class="field-wrap"><div class="field" id="field"></div></div>' +
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
          '<div id="dotInfo" style="margin-top:10px"></div>' +
        '</div>' +
        '<div class="card tight"><h4>Jogada</h4><div id="playMeta"></div></div>' +
        '<div class="card tight">' +
          '<h4>Trocar jogada<span class="sec-sub">' + S.plays.length + ' dropbacks no jogo</span></h4>' +
          '<div class="cmp-pick"><select id="playPick" aria-label="Escolher jogada"></select></div>' +
          '<div class="row"><button class="ev-chip" id="prevPlay">‹ anterior</button>' +
          '<button class="ev-chip" id="nextPlay">próxima ›</button></div>' +
        '</div>';

      $('playPick').innerHTML = S.plays.filter((p) => p.hasTracking).map((p) =>
        '<option value="' + p.playId + '"' + (p.playId === S.playId ? ' selected' : '') + '>' +
        'Q' + p.quarter + ' ' + p.clock + ' · ' + esc(p.offense) + ' · ' + ordDown(p.down, p.yardsToGo) +
        ' · ' + signed(p.result) + 'jd</option>').join('');

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
    const tr = await api.tracking(gameId, playId);
    if (my !== seq.play) return; // resposta atrasada: outra jogada já foi pedida
    const p = tr.play;
    if (FV) FV.pause(); // a animação anterior não pode seguir mexendo nos controles novos
    FV = new Field($('field'), tr);
    FV.onFrame = (i) => {
      $('frameRange').value = i;
      $('frameClock').textContent = (FV.clockAt(i) >= 0 ? '+' : '') + FV.clockAt(i).toFixed(1) + 's';
    };
    FV.onState = (playing) => { $('btnPlay').textContent = playing ? '❚❚' : '▶'; };
    FV.onSelect = (pl) => { $('dotInfo').innerHTML = pl ? dotCard(pl) : ''; };

    $('frameRange').max = tr.frameCount - 1;
    $('fieldSub').textContent = tr.frameCount + ' quadros a 10 fps · ataque joga para cima';
    FV.setFrame(tr.snapIndex || 0);

    $('evStrip').innerHTML = (tr.events || []).map((e) =>
      '<button class="ev-chip" data-frame="' + e.frame + '">' + esc(evLabel(e.name)) + '</button>').join('');

    $('playMeta').innerHTML = playMetaHTML(p);
    prefetchVizinhas(gameId, playId);
  }

  /**
   * Antecipa as jogadas anterior e seguinte, depois que a atual já está
   * desenhada (a escolhida nunca disputa conexão com a antecipação). Falha
   * aqui é silenciosa: o get() esquece o pedido e a jogada é buscada de novo
   * se o usuário a escolher.
   */
  function prefetchVizinhas(gameId, playId) {
    const lista = S.plays.filter((q) => q.hasTracking);
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

  function playMetaHTML(p) {
    const rows = [
      ['Situação', ordDown(p.down, p.yardsToGo) + ' na ' + esc(p.yardline)],
      ['Momento', 'Q' + p.quarter + ' · ' + p.clock],
      ['Resultado', signed(p.result) + ' jd · ' + esc(p.passResultLabel)],
      ['Formação', esc(p.formation || '—') + (p.playAction ? ' + play action' : '')],
      ['Personnel', esc(p.personnelO || '—')],
      ['Cobertura', esc(p.coverage || '—') + (p.coverageType ? ' (' + esc(p.coverageType) + ')' : '')],
      ['Rushers', (isNum(p.rushers) ? p.rushers : '—') + (p.blitz ? ' · blitz' : '')],
      ['Tempo p/ lançar', secs(p.timeToThrow) + ' ' + delta(p.timeToThrow, league().timeToThrow, true)],
      ['Pressão', p.pressured ? 'sim · 1ª pressão em ' + secs(p.timeToPressure) : 'não'],
    ];
    return '<div class="play-desc" style="margin-bottom:10px">' + esc(p.description) + '</div>' +
      rows.map((r) => '<div class="stat-row"><span class="k">' + r[0] +
        '</span><span class="v" style="font-size:13px">' + r[1] + '</span></div>').join('') +
      (p.tags && p.tags.length ? '<div class="chips">' + p.tags.map((t) =>
        '<span class="chip ' + tagCls(t) + '">' + esc(t) + '</span>').join('') + '</div>' : '');
  }

  function tagCls(t) {
    if (t === 'TOUCHDOWN') return 'red';
    if (t === 'SACK') return 'purple';
    if (t === 'INTERCEPTAÇÃO') return 'amber';
    if (t === 'JOGADA EXPLOSIVA') return 'green';
    if (t === 'BLITZ') return 'red';
    return 'blue';
  }

  function dotCard(p) {
    const bits = [];
    if (isNum(p.maxSpeed)) bits.push(['Pico', nm(p.maxSpeed, 1) + ' mph']);
    if (isNum(p.distance)) bits.push(['Distância', nm(p.distance, 1) + ' jd']);
    if (isNum(p.depth)) bits.push(['Deslocamento', nm(p.depth, 1) + ' jd']);
    if (isNum(p.timeToQb)) bits.push(['Chegou ao QB', secs(p.timeToQb)]);
    const f = p.pff || {};
    const flags = [];
    if (f.sack) flags.push('SACK');
    if (f.hurry) flags.push('HURRY');
    if (f.hit) flags.push('HIT');
    if (f.sackAllowed) flags.push('SACK CEDIDO');
    if (f.hurryAllowed) flags.push('HURRY CEDIDO');
    if (f.beaten) flags.push('SUPERADO');
    if (f.blockType) flags.push('BLOCO ' + f.blockType);

    return '<div class="p-row" data-player="' + p.nflId + '" role="button" tabindex="0">' +
      badge(teamOf(p.team), 'sm') +
      '<div class="nm"><b>' + esc(p.name || '—') + '</b><span>#' + (p.jersey || '—') + ' · ' +
        esc(p.linedUp || p.position || '') + ' · ' + esc(p.roleLabel || p.role || '') + '</span></div>' +
      rateChip(p.rating) + '</div>' +
      (bits.length ? '<div class="bio">' + bits.map((b) =>
        '<div><div class="k">' + b[0] + '</div><div class="v">' + b[1] + '</div></div>').join('') + '</div>' : '') +
      (flags.length ? '<div class="chips" style="margin-top:8px">' + flags.map((x) =>
        '<span class="chip red">' + esc(x) + '</span>').join('') + '</div>' : '');
  }

  async function coachPlays() {
    await into('coachBody', async () => {
      await ensurePlays();
      if (!S.plays.length) return none('Sem jogadas neste jogo.');
      const byQ = {};
      S.plays.forEach((p) => { (byQ[p.quarter] = byQ[p.quarter] || []).push(p); });
      return Object.keys(byQ).sort().map((q) =>
        '<div class="sec-title">' + (q > 4 ? 'Prorrogação' : q + 'º quarto') +
        '<span class="sec-sub">' + byQ[q].length + ' dropbacks</span></div>' +
        byQ[q].map(playRow).join('')).join('');
    }, 'Carregando as jogadas...');
  }

  function playRow(p) {
    let tone = '';
    if (p.tags.indexOf('TOUCHDOWN') >= 0) tone = 'td';
    else if (p.passResult === 'S') tone = 'sack';
    else if (p.passResult === 'IN') tone = 'turnover';
    else if (p.result >= 20) tone = 'big';
    const gain = p.result > 0 ? 'pos' : p.result < 0 ? 'neg' : 'zero';
    return '<div class="play-row ' + tone + (p.playId === S.playId ? ' active' : '') + '" ' +
      'data-play="' + p.playId + '" role="button" tabindex="0">' +
      '<div class="play-head">' + badge(teamOf(p.offense), 'sm') +
        '<span class="sit">' + ordDown(p.down, p.yardsToGo) + '</span>' +
        '<span class="clk">Q' + p.quarter + ' ' + p.clock + '</span>' +
        '<span class="spacer"></span>' +
        '<span class="gain ' + gain + '">' + signed(p.result) + '</span></div>' +
      '<div class="play-desc">' + esc(p.description) + '</div>' +
      '<div class="chips">' +
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

    const cmp = (label, l, r, fmtFn, lowerBetter) => {
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

    $('coachBody').innerHTML =
      '<div class="card"><h4>' + esc(A.abbr) + ' vs ' + esc(H.abbr) +
        '<span class="sec-sub">Ataque: só dropbacks (o dataset não traz corridas)</span></h4>' +
        cmp('Dropbacks', ao.dropbacks, ho.dropbacks, (v) => nm(v)) +
        cmp('Jardas líquidas', ao.netYards, ho.netYards, (v) => nm(v)) +
        cmp('Passes completos', ao.completions, ho.completions, (v) => nm(v)) +
        cmp('Aproveitamento', ao.completionRate, ho.completionRate, (v) => pct(v)) +
        cmp('Jd por dropback', ao.yardsPerDropback, ho.yardsPerDropback, (v) => nm(v, 1)) +
        cmp('3ª descida', ao.thirdDownConv, ho.thirdDownConv,
          (v) => (v === ao.thirdDownConv ? ao.thirdDownConv + '/' + ao.thirdDownAtt
                                          : ho.thirdDownConv + '/' + ho.thirdDownAtt)) +
        cmp('Jogadas explosivas', ao.explosive, ho.explosive, (v) => nm(v)) +
      '</div>' +
      '<div class="card"><h4>Pressão e proteção</h4>' +
        cmp('Sacks aplicados', ad.sacks, hd.sacks, (v) => nm(v)) +
        cmp('Pressões geradas', ad.pressures, hd.pressures, (v) => nm(v)) +
        cmp('Taxa de pressão', ad.pressureRate, hd.pressureRate, (v) => pct(v)) +
        cmp('Taxa de blitz', ad.blitzRate, hd.blitzRate, (v) => pct(v)) +
        cmp('Interceptações', ad.interceptions, hd.interceptions, (v) => nm(v)) +
      '</div>' +
      '<div class="card"><h4>Relógio do pocket</h4>' +
        statRow('Tempo p/ lançar · ' + A.abbr, secs(ao.timeToThrow), delta(ao.timeToThrow, league().timeToThrow, true)) +
        statRow('Tempo p/ lançar · ' + H.abbr, secs(ho.timeToThrow), delta(ho.timeToThrow, league().timeToThrow, true)) +
        statRow('1ª pressão · defesa ' + A.abbr, secs(ad.timeToPressure), '') +
        statRow('1ª pressão · defesa ' + H.abbr, secs(hd.timeToPressure), '') +
        statRow('Pressionado · ' + A.abbr, pct(ao.pressureRateAllowed), delta(ao.pressureRateAllowed, league().pressureRate, true, true)) +
        statRow('Pressionado · ' + H.abbr, pct(ho.pressureRateAllowed), delta(ho.pressureRateAllowed, league().pressureRate, true, true)) +
      '</div>' +
      '<div class="card"><h4>Faltas nos dropbacks</h4>' +
        statRow(A.abbr, ao.penalties + ' faltas', nm(ao.penaltyYards) + ' jd') +
        statRow(H.abbr, ho.penalties + ' faltas', nm(ho.penaltyYards) + ' jd') +
      '</div>';
  }

  function statRow(k, v, extra) {
    return '<div class="stat-row"><span class="k">' + esc(k) + '</span>' +
      '<span class="v vs-league">' + v + (extra ? ' ' + extra : '') + '</span></div>';
  }

  function coachBook() {
    const g = S.game;
    if (!g) { $('coachBody').innerHTML = none('Escolha uma partida.'); return; }
    const block = (title, sub, items, def) =>
      '<div class="card"><h4>' + esc(title) + '<span class="sec-sub">' + esc(sub) + '</span></h4>' +
      (items && items.length ? items.slice(0, 6).map((d) =>
        '<div class="tend"><div class="tend-top">' +
          '<span class="l">' + esc(d.label) + '</span>' +
          '<span class="r">' + pct(d.share) + ' · ' + d.plays + ' jogadas · ' +
            nm(d.yardsPerPlay, 1) + ' jd' +
            (isNum(d.completionRate) ? ' · ' + pct(d.completionRate) + ' comp' : '') + '</span>' +
        '</div><div class="tend-bar' + (def ? ' def' : '') + '"><span style="width:' +
          (d.share * 100).toFixed(1) + '%"></span></div></div>').join('')
        : none('Sem dados.')) + '</div>';

    const t = g.tendencies;
    $('coachBody').innerHTML =
      block('Formações · ' + g.home.abbr, 'ataque', t.home.formations) +
      block('Coberturas · ' + g.home.abbr, 'defesa', t.home.coverages, true) +
      block('Formações · ' + g.away.abbr, 'ataque', t.away.formations) +
      block('Coberturas · ' + g.away.abbr, 'defesa', t.away.coverages, true) +
      block('Tipo de dropback · ' + g.home.abbr, 'ataque', t.home.dropbacks) +
      block('Tipo de dropback · ' + g.away.abbr, 'ataque', t.away.dropbacks);
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
    { k: 'T,G,C', l: 'Linha of.' },
    { k: 'DE,DT,NT', l: 'Linha def.' },
    { k: 'OLB,ILB,MLB,LB', l: 'LB' },
    { k: 'CB', l: 'CB' },
    { k: 'FS,SS,DB', l: 'Safety' },
  ];

  function renderScout() {
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
        '<span class="sec-sub">ordenados por rating</span></div>' +
        '<div class="p-list">' + list.map((p) =>
          '<div class="p-row" data-player="' + p.nflId + '" role="button" tabindex="0">' +
          badge(teamOf(p.team), 'sm') +
          '<div class="nm"><b>' + esc(p.name) + '</b><span>' + esc(p.position) + ' · ' +
            esc(p.roleLabel) + ' · ' + p.snaps + ' snaps' +
            (isNum(p.topSpeed) ? ' · ' + nm(p.topSpeed, 1) + ' mph' : '') + '</span></div>' +
          rateChip(p.rating) + '</div>').join('') + '</div>';
    }, 'Buscando jogadores...', () => my === seq.scout);
  }

  async function scoutDetail() {
    const my = ++seq.scout;
    const desenhou = await into('scoutBody', async () => {
      const p = await api.player(S.playerId);
      const r = p.roles[0];
      const t = teamOf(p.team);
      let html =
        '<div class="row" style="padding:12px 16px 0"><button class="ev-chip" id="backList">‹ voltar à lista</button></div>' +
        '<div class="card"><div class="scout-hero">' +
          '<div class="scout-avatar" style="background:' + esc(t.primary) + '">' +
            esc(p.position || '') + '</div>' +
          '<div class="info"><h3>' + esc(p.name) + '</h3>' +
            '<div class="meta">' + esc(p.position) + ' · ' + esc(t.name) +
              (isNum(p.age) ? ' · ' + p.age + ' anos' : '') + '</div>' +
            '<span class="rating-badge">' + (isNum(p.rating) ? p.rating : 'n/d') + '</span>' +
            ' <span class="muted" style="font-size:11px">' + esc(p.roleLabel) + '</span>' +
          '</div></div>' +
          '<div class="bio">' +
            bioBox('Altura', p.height) + bioBox('Peso', isNum(p.weight) ? p.weight + ' lb' : null) +
            bioBox('Faculdade', p.college) + bioBox('Pico', isNum(p.topSpeed) ? nm(p.topSpeed, 1) + ' mph' : null) +
          '</div></div>';

      if (r) {
        html += '<div class="card"><h4>Radar de atributos' +
          '<span class="sec-sub">Percentil entre ' + esc(r.roleLabel.toLowerCase()) +
          's com amostra suficiente</span></h4>' +
          (p.roles.length > 1 ? '<div class="role-tabs">' + p.roles.map((x, i) =>
            '<button class="role-tab' + (i === 0 ? ' active' : '') + '" data-role="' + i + '">' +
            esc(x.roleLabel) + ' (' + x.snaps + ')</button>').join('') + '</div>' : '') +
          '<div id="radarSlot">' + radarBlock(r) + '</div></div>';

        html += '<div class="card"><h4>Números da função</h4><div id="statSlot">' +
          r.stats.map((s) => '<div class="stat-row"><span class="k">' + esc(s.label) +
            '</span><span class="v">' + nm(s.value, s.value % 1 ? 1 : 0) +
            (s.unit ? ' <small>' + esc(s.unit) + '</small>' : '') + '</span></div>').join('') +
          '</div></div>';
      }

      if (p.positionsLinedUp.length) {
        html += '<div class="card"><h4>Onde ele se alinha</h4>' +
          p.positionsLinedUp.map((x) => '<div class="tend"><div class="tend-top">' +
            '<span class="l">' + esc(x.position) + '</span><span class="r">' + x.snaps +
            ' snaps · ' + pct(x.share) + '</span></div>' +
            '<div class="tend-bar"><span style="width:' + (x.share * 100).toFixed(1) +
            '%"></span></div></div>').join('') + '</div>';
      }

      if (p.gameLog.length) {
        html += '<div class="card"><h4>Jogo a jogo<span class="sec-sub">semanas 1–8 de 2021</span></h4>' +
          p.gameLog.map((g) => '<div class="stat-row"><span class="k">Sem ' + g.week +
            ' · vs ' + esc(g.opponent || '—') + '</span><span class="v" style="font-size:13px">' +
            g.snaps + ' snaps' + (isNum(g.topSpeed) ? ' · ' + nm(g.topSpeed, 1) + ' mph' : '') +
            (g.pressures ? ' · ' + g.pressures + ' press.' : '') +
            (g.pressuresAllowed ? ' · ' + g.pressuresAllowed + ' cedidas' : '') +
            '</span></div>').join('') + '</div>';
      }

      html += '<div class="card"><h4>Comparar</h4>' +
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
      return '<div class="state">Amostra insuficiente nesta função (' + r.snaps +
        ' snaps) para gerar percentis.</div>';
    }
    return '<div class="radar-wrap">' + radarSVG(r.radar) + '</div>' +
      '<div class="attr-list">' + r.radar.map((a) =>
        '<div class="attr"><span class="name">' + esc(a.label) + '</span>' +
        '<span class="track"><span class="val-fill" style="width:' +
          Math.max(2, a.percentile || 0) + '%"></span></span>' +
        '<span class="val">' + nm(a.value, a.value % 1 ? 1 : 0) + '</span>' +
        '<span class="pctl">p' + nm(a.percentile) + '</span></div>').join('') + '</div>' +
      '<div class="muted" style="font-size:10.5px;margin-top:6px">' +
      'A barra mostra o percentil; o número é o valor real do jogador.</div>';
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
          '<option value="' + p.nflId + '">' + esc(p.name) + ' · ' + esc(p.team) +
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
      S.bc = await api.broadcast(S.gameId);
      $('bcSub').textContent = S.bc.away.abbr + ' @ ' + S.bc.home.abbr + ' · ' +
        S.bc.feed.length + ' dropbacks';
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
        '<div><div class="qtr">' + (p.quarter > 4 ? 'PRORROG.' : 'Q' + p.quarter) + ' · ' + esc(p.clock) + '</div>' +
          '<div class="situ">' + esc(p.offense) + ' com a bola<br>' + ordDown(p.down, p.yardsToGo) + '</div></div>' +
        '<div>' + badge(bc.home, 'lg') + '<div class="big' + (hs > as ? ' lead' : '') + '">' +
          nm(hs) + '</div><div class="nm">' + esc(bc.home.nick || bc.home.abbr) + '</div></div>' +
      '</div>';

    $('bcPos').textContent = (i + 1) + '/' + bc.feed.length;
    $('bcRange').value = i;

    // Mostra as ultimas jogadas, a atual no topo.
    const from = Math.max(0, i - 11);
    $('bcFeed').innerHTML = bc.feed.slice(from, i + 1).reverse().map((q, k) =>
      '<div class="tl-item ' + esc(q.narration.tone) + (k === 0 ? ' now' : '') + '">' +
        '<span class="time">' + esc(q.clock) + '</span>' +
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
      bar('Dropbacks', ca.dropbacks, ch.dropbacks, (v) => nm(v)) +
      bar('Passes completos', ca.completions, ch.completions, (v) => nm(v)) +
      bar('Jardas', ca.yards, ch.yards, (v) => nm(v)) +
      bar('Sacks sofridos', ca.sacksTaken, ch.sacksTaken, (v) => nm(v)) +
      bar('Pressões da defesa', ca.pressures, ch.pressures, (v) => nm(v));
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
      renderWeeks();
      await renderGames();
      if (S.games.length) await selectGame(S.games[0].gameId);
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
      const list = S.plays.filter((p) => p.hasTracking);
      let idx = list.findIndex((p) => p.playId === S.playId);
      idx += t.closest('#nextPlay') ? 1 : -1;
      if (idx >= 0 && idx < list.length) { S.playId = list[idx].playId; coachLineup(); }
      return;
    }

    const pl = t.closest('[data-player]');
    if (pl) {
      S.playerId = Number(pl.dataset.player);
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
      $('datasetNote').scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  document.addEventListener('change', (e) => {
    if (e.target.id === 'playPick') { S.playId = Number(e.target.value); coachLineup(); }
    if (e.target.id === 'cmpPick' && e.target.value) { showCompare(Number(e.target.value)); }
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
    // As partidas da semana saem junto com o meta, e não depois dele: a semana
    // do deep link (ou a 1ª) é conhecida antes. O get() entrega a mesma
    // promessa quando renderGames() pedir a mesma URL.
    const semanaPedida = Number(new URLSearchParams(location.search).get('week')) || 1;
    api.games({ week: semanaPedida }).catch(() => {});
    try {
      S.meta = await api.meta();
    } catch (e) {
      document.querySelector('.app').insertAdjacentHTML('afterbegin',
        '<div class="disclaimer" style="border-color:var(--nfl-red)"><b>API indisponível.</b><br>' +
        'Rode <code>python server/serve.py</code> e abra http://127.0.0.1:8000 — ' +
        'a página precisa do servidor para ler o dataset.<br>Detalhe: ' + esc(e.message) + '</div>');
      $('hdrSub').textContent = 'Sem conexão com a API';
      return;
    }
    // Deep link opcional: ?week=3&game=2021092300&screen=coach
    const u = new URLSearchParams(location.search);
    const wantWeek = Number(u.get('week'));
    const wantGame = Number(u.get('game'));
    const wantScreen = u.get('screen');

    S.week = S.meta.weeks.some((w) => w.week === wantWeek) ? wantWeek : S.meta.weeks[0].week;
    renderDatasetNote();
    renderWeeks();
    $('hdrSub').textContent = 'Temporada ' + S.meta.season + ' · semanas 1–8 · ' +
      S.meta.counts.plays.toLocaleString('pt-BR') + ' jogadas';
    await renderGames();

    const pick = S.games.some((g) => g.gameId === wantGame) ? wantGame
      : S.games.length ? S.games[0].gameId : null;
    if (pick) await selectGame(pick);
    if (wantScreen && TITLES[wantScreen]) go(wantScreen);
  })();
})();
