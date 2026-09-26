/* ==========================================================================
   Tela Jogadores (spec novo-visual, tarefa 6): o antigo Olheiro, mais os
   "Jogadores a observar" da partida selecionada. scoutList, scoutDetail,
   radarBlock, radarSVG, fillComparePicker e showCompare vieram do app.js com
   a mesma lógica e o mesmo "só o último vence"; mudam o HTML e as classes.
   ========================================================================== */
import { api, ultimo } from '../api.js';
import { $, esc, isNum, pct, nm, badge, rateChip, spin, oops, none, into, icone } from '../ui.js';
import { S, ir, sincronizarUrl } from '../main.js';

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

const F = { pos: '', q: '' };     // filtros da lista (ficam ao voltar do perfil)
let roles = [];                    // funções do jogador aberto (para a comparação)

const teamOf = (a) => (S.meta && S.meta.teams[a]) || { abbr: a, primary: '#013369', name: a };

/* ------------------------------- render -------------------------------- */
export function render(el) {
  ligar(el);
  el.innerHTML =
    '<section class="block" id="observarBlock" hidden>' +
      '<div class="block-head"><h2>A observar</h2><button class="link-btn" id="observarJogo"></button></div>' +
      '<div class="watch-scroll" id="observarLista"></div>' +
    '</section>' +
    '<section class="block" id="jogadoresBlock">' +
      '<div class="block-head"><h2 id="jogadoresTitulo">Jogadores</h2><span class="muted">Temporada ' + S.season + '</span></div>' +
      '<div id="scoutControles">' +
        '<label class="campo">' + icone('lupa') +
          '<input type="search" id="scoutSearch" maxlength="100" autocomplete="off" spellcheck="false" ' +
          'placeholder="Buscar jogador pelo nome" aria-label="Buscar jogador pelo nome" /></label>' +
        '<div class="chips pos-chips" id="scoutFilters" role="group" aria-label="Posição"></div>' +
      '</div>' +
      '<div id="scoutBody"></div>' +
    '</section>';
  $('scoutSearch').value = F.q;
  renderFiltros();
  renderObservar();
  if (S.playerId) scoutDetail(); else scoutList();
}

/** Abre o perfil de um jogador (a busca geral e a prancheta usam). */
export function abrirJogador(id) {
  S.playerId = String(id);
  if (S.tela === 'jogadores') { mostrarPerfil(); return; }
  ir('jogadores');
}

function mostrarPerfil() {
  sincronizarUrl();
  scoutDetail();
  window.scrollTo({ top: 0 });
}

function renderFiltros() {
  $('scoutFilters').innerHTML = POS_GROUPS.map((g) =>
    '<button class="chip" data-pos="' + esc(g.k) + '" aria-pressed="' + (g.k === F.pos) + '">' + esc(g.l) + '</button>').join('');
}

// Eventos da tela, ligados uma vez no container.
function ligar(el) {
  if (el.dataset.ligado) return;
  el.dataset.ligado = '1';
  el.addEventListener('click', (e) => {
    const t = e.target;
    const pl = t.closest('[data-player]');
    if (pl) { abrirJogador(pl.dataset.player); return; }
    const pos = t.closest('[data-pos]');
    if (pos) { F.pos = pos.dataset.pos; renderFiltros(); scoutList(); return; }
    if (t.closest('#backList')) { S.playerId = null; sincronizarUrl(); scoutList(); return; }
    if (t.closest('#observarJogo') && $('observarJogo').dataset.jogo) {
      S.gameId = Number($('observarJogo').dataset.jogo);
      ir('jogo');
    }
  });
  let timer = null;
  el.addEventListener('input', (e) => {
    if (e.target.id !== 'scoutSearch') return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      F.q = e.target.value.slice(0, 100).trim();
      S.playerId = null;
      scoutList();
    }, 280);
  });
  el.addEventListener('change', (e) => {
    if (e.target.id === 'cmpPick' && e.target.value) showCompare(e.target.value);
  });
}

/* --------------------------- a observar (6.2) --------------------------- */
// Da partida selecionada; sem partida escolhida, a 1ª da semana (como a página Jogo).
// Sem ninguém com amostra suficiente, a seção fica oculta (6.4).
async function renderObservar() {
  const atual = ultimo('observar');
  const bloco = $('observarBlock');
  try {
    let id = S.gameId;
    if (!id) {
      const jogos = await api.games(S.season, S.week);
      if (!atual()) return;
      if (!jogos.length) return;
      id = jogos[0].gameId;
    }
    const g = await api.game(id);
    if (!atual() || !$('observarBlock')) return;
    const lista = (g.watch || []).filter((p) => p.rated !== false);
    bloco.hidden = !lista.length;
    if (!lista.length) return;
    const b = $('observarJogo');
    b.textContent = g.away.abbr + ' @ ' + g.home.abbr;
    b.dataset.jogo = g.gameId;
    b.setAttribute('aria-label', 'Abrir a partida ' + g.away.abbr + ' contra ' + g.home.abbr);
    $('observarLista').innerHTML = lista.map((p) =>
      '<button class="watch-card" data-player="' + esc(p.nflId) + '">' +
        '<span class="watch-top">' + badge(teamOf(p.team), 'sm') + rateChip(p.rating) + '</span>' +
        '<span class="watch-nome">' + esc(p.name) + '</span>' +
        '<span class="watch-pos">' + esc(p.position || '') + ' · ' + esc(p.roleLabel || '') + '</span>' +
      '</button>').join('');
  } catch (e) {
    if (atual() && bloco) bloco.hidden = true;     // a lista principal segue
    console.warn('jogadores a observar indisponíveis:', e.message);
  }
}

/* -------------------------------- lista -------------------------------- */
async function scoutList() {
  $('scoutControles').hidden = false;
  $('jogadoresTitulo').textContent = 'Jogadores';
  const atual = ultimo('scout');
  await into('scoutBody', async () => {
    const list = await api.players(S.season, { position: F.pos, q: F.q, limit: 60 });
    if (!list.length) return none('Nenhum jogador com amostra suficiente para esse filtro.');
    return '<p class="muted lista-sub">' + list.length + ' jogadores · ordenados por rating</p>' +
      '<div class="list">' + list.map((p, i) =>
        '<button class="row-card" data-player="' + esc(p.nflId) + '">' +
          '<span class="rank">' + (i + 1) + '</span>' +
          '<span class="grow"><b>' + esc(p.name) + '</b><small>' + esc(p.position) + ' · ' + esc(p.team) + ' · ' +
            esc(p.roleLabel) + ' · ' + nm(p.snaps) + ' snaps · ' + nm(p.games) + ' jogos</small></span>' +
          rateChip(p.rating) +
        '</button>').join('') + '</div>';
  }, 'Buscando jogadores…', atual);
}

/* -------------------------------- perfil ------------------------------- */
async function scoutDetail() {
  $('scoutControles').hidden = true;
  $('jogadoresTitulo').textContent = 'Perfil';
  const atual = ultimo('scout');
  const voltar = '<button class="btn-sec voltar" id="backList">‹ Voltar à lista</button>';
  const desenhou = await into('scoutBody', async () => {
    let p;
    try {
      p = await api.player(S.playerId, S.season);
    } catch (e) {
      return voltar + none('Este jogador não tem dados na temporada ' + S.season + '.');
    }
    const r = p.roles[0];
    const t = teamOf(p.team);
    let html = voltar +
      '<div class="card perfil">' +
        '<div class="perfil-topo">' +
          '<span class="avatar" style="background:' + esc(t.primary) + '">' + esc(p.position || '') + '</span>' +
          '<span class="grow"><h3>' + esc(p.name) + '</h3>' +
            '<span class="perfil-meta">' + esc(p.position) + ' · ' + esc(t.name) + ' · ' + p.season +
            (isNum(p.age) ? ' · ' + p.age + ' anos' : '') + '</span>' +
            '<span class="perfil-meta">' + esc(p.roleLabel) + '</span></span>' +
          rateChip(p.rating) +
        '</div>' +
        '<div class="bio">' +
          bioBox('Altura', p.height) + bioBox('Peso', isNum(p.weight) ? p.weight + ' lb' : null) +
          bioBox('Faculdade', p.college) + bioBox('Jogos', isNum(p.games) ? String(p.games) : null) +
        '</div></div>';

    if (r) {
      html += '<div class="card"><div class="card-head"><h3>Radar de atributos</h3>' +
        '<span class="muted">percentil no grupo ' + esc(r.roleLabel) + ', ' + p.season + '</span></div>' +
        (r.baseReduzida ? '<p class="aviso">O rating da linha ofensiva usa menos ' +
          'estatísticas que os demais grupos: 2 dos 4 eixos são do time, nos jogos em que ele atuou.</p>' : '') +
        '<div id="radarSlot">' + radarBlock(r) + '</div></div>';

      html += '<div class="card"><div class="card-head"><h3>Números da temporada</h3></div><div id="statSlot">' +
        r.stats.map((s) => '<div class="stat-row"><span class="k">' + esc(s.label) +
          '</span><span class="v">' + nm(s.value, s.value % 1 ? 1 : 0) +
          (s.unit ? ' <small>' + esc(s.unit) + '</small>' : '') + '</span></div>').join('') +
        '</div></div>';
    }

    if (p.positionsLinedUp && p.positionsLinedUp.length) {
      html += '<div class="card"><div class="card-head"><h3>Onde ele se alinha</h3></div>' +
        p.positionsLinedUp.map((x) => '<div class="tend"><div class="tend-top">' +
          '<span class="l">' + esc(x.position) + '</span><span class="r">' + x.snaps +
          ' snaps · ' + pct(x.share) + '</span></div>' +
          '<div class="tend-bar"><span style="width:' + (x.share * 100).toFixed(1) +
          '%"></span></div></div>').join('') + '</div>';
    }

    if (p.gameLog.length) {
      html += '<div class="card"><div class="card-head"><h3>Jogo a jogo</h3><span class="muted">temporada ' + p.season + '</span></div>' +
        p.gameLog.map((g) => '<div class="stat-row"><span class="k">' +
          esc(g.rodada && g.rodada.indexOf('Semana') !== 0 ? g.rodada : 'Sem ' + g.week) +
          ' · vs ' + esc(g.opponent || '—') + '</span><span class="v">' +
          (isNum(g.snaps) ? g.snaps + ' snaps' : '') +
          (g.stats || []).filter((s) => s.label.indexOf('Snaps') !== 0 && s.value).slice(0, 3)
            .map((s) => ' · ' + nm(s.value, s.value % 1 ? 1 : 0) + ' ' + esc(s.label.toLowerCase())).join('') +
          '</span></div>').join('') + '</div>';
    }

    html += '<div class="card"><div class="card-head"><h3>Comparar</h3><span class="muted">mesmo grupo e temporada</span></div>' +
      '<select class="select" id="cmpPick" aria-label="Comparar com"><option value="">Escolha um jogador…</option></select>' +
      '<div id="cmpSlot"></div></div>';

    if (atual()) roles = p.roles;
    return html;
  }, 'Carregando o perfil…', atual);

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
    // O eixo sem estatística na temporada fica fora do radar e da média, com o motivo.
    semDado.map((a) => '<p class="motivo">' + esc(a.label) + ': ' + esc(a.motivo || 'sem dado') + '</p>').join('') +
    '<p class="muted radar-nota">A barra mostra o percentil; o número é o valor real do jogador. ↓ = menor é melhor.</p>';
}

function radarSVG(axes) {
  const n = axes.length;
  if (!n) return '';
  const size = 280, cx = size / 2, cy = size / 2 + 2, R = size * 0.3;
  const pt = (i, rr) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr];
  };
  const ring = (f) => axes.map((_, i) => pt(i, R * f).map((v) => v.toFixed(1)).join(',')).join(' ');
  // 50 px de cada lado para os rótulos dos eixos laterais caberem sem cortar
  let s = '<svg class="radar" width="' + (size + 100) + '" height="' + size + '" viewBox="-50 0 ' + (size + 100) + ' ' + size +
    '" role="img" aria-label="Radar de atributos">';
  [1, 0.66, 0.33].forEach((f) => {
    s += '<polygon points="' + ring(f) + '" fill="none" stroke="rgba(255,255,255,.14)"/>';
  });
  axes.forEach((_, i) => {
    const q = pt(i, R);
    s += '<line x1="' + cx + '" y1="' + cy + '" x2="' + q[0].toFixed(1) + '" y2="' +
      q[1].toFixed(1) + '" stroke="rgba(255,255,255,.14)"/>';
  });
  const data = axes.map((a, i) =>
    pt(i, R * (Math.max(6, Math.min(100, a.percentile || 0)) / 100)).map((v) => v.toFixed(1)).join(',')
  ).join(' ');
  s += '<polygon points="' + data + '" fill="rgba(229,32,46,.28)" stroke="#e5202e" stroke-width="2"/>';
  axes.forEach((a, i) => {
    const q = pt(i, R * (Math.max(6, Math.min(100, a.percentile || 0)) / 100));
    s += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="3" fill="#e5202e"/>';
    const lp = pt(i, R + 16);
    const anchor = lp[0] < cx - 6 ? 'end' : lp[0] > cx + 6 ? 'start' : 'middle';
    const linhas = quebrar(a.label);
    const y0 = lp[1] + 4 - (linhas.length - 1) * 8;
    s += '<text x="' + lp[0].toFixed(1) + '" y="' + y0.toFixed(1) + '" font-size="13" ' +
      'text-anchor="' + anchor + '" fill="#a7b3c6">' + linhas.map((l, k) =>
        '<tspan x="' + lp[0].toFixed(1) + '"' + (k ? ' dy="16"' : '') + '>' + esc(l) + '</tspan>').join('') + '</text>';
  });
  return s + '</svg>';
}

// Rótulo longo do eixo vai em duas linhas, quebrado no espaço mais perto do meio.
function quebrar(t) {
  t = String(t || '');
  if (t.length <= 12 || t.indexOf(' ') < 0) return [t];
  let melhor = -1;
  for (let i = 0; i < t.length; i++) {
    if (t[i] === ' ' && (melhor < 0 || Math.abs(i - t.length / 2) < Math.abs(melhor - t.length / 2))) melhor = i;
  }
  return [t.slice(0, melhor), t.slice(melhor + 1)];
}

async function fillComparePicker() {
  const sel = $('cmpPick');
  if (!sel || !roles.length) return;
  try {
    const role = roles[0].role;
    const peers = await api.players(S.season, { role: role, limit: 60 });
    sel.innerHTML = '<option value="">Escolha um jogador…</option>' +
      peers.filter((p) => p.nflId !== S.playerId).map((p) =>
        '<option value="' + esc(p.nflId) + '">' + esc(p.name) + ' · ' + esc(p.team) +
        ' · ' + (isNum(p.rating) ? p.rating : 'n/d') + '</option>').join('');
  } catch (e) { /* a comparação é opcional */ }
}

async function showCompare(otherId) {
  const slot = $('cmpSlot');
  const atual = ultimo('comparar');
  slot.innerHTML = spin('Comparando…');
  try {
    const c = await api.compare(S.playerId, otherId, S.season);
    if (!atual()) return;
    if (!c.rows.length) { slot.innerHTML = none('Funções diferentes: não há métricas comuns.'); return; }
    slot.innerHTML =
      '<div class="cmp-nomes"><b class="l">' + esc(c.left.name) + '</b>' +
        '<span class="muted">' + esc(c.roleLabel || '') + '</span>' +
        '<b class="r">' + esc(c.right.name) + '</b></div>' +
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
  } catch (e) { if (atual()) slot.innerHTML = oops(e.message); }
}
