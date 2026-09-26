/* ==========================================================================
   Página Jogo (spec novo-visual, tarefa 4): o antigo Treinador e o antigo
   Comentarista numa página só, com o placar, a matéria da ESPN e 5 abas.
   As funções vieram do app.js (coachLineup, loadFieldPlay, prefetchVizinhas,
   ensurePlays, playRow, coachPlays, coachStats, coachBook, renderBroadcast,
   paintBc, renderMateria, linkEspn, conferirPlacar) com a mesma lógica e os
   mesmos contadores seq; mudam o HTML e as classes.
   ========================================================================== */
import { api, ultimo } from '../api.js';
import {
  $, esc, isNum, pct, nm, secs, signed, ordDown, inicioLocal, dataHora, badge, rateChip, delta,
  spin, oops, none, into,
} from '../ui.js';
import { ler as lerConfig, aoMudar } from '../config.js';
import { Field, coresDosLados } from '../prancheta.js';
import { S, ir, sincronizarUrl } from '../main.js';
import { estadoDoJogo } from './inicio.js';

export const ABAS = [
  ['prancheta', 'Prancheta'], ['jogadas', 'Jogadas'], ['replay', 'Replay'],
  ['estatisticas', 'Estatísticas'], ['playbook', 'Playbook'],
];

// "Só o último vence": cada fluxo que pode ser disparado de novo antes de a
// resposta anterior chegar tem um contador. Quem volta com contador velho descarta.
const seq = { play: 0, materia: 0 };

// O que já foi carregado da partida aberta (some ao trocar de partida).
let J = { gameId: null, game: null, plays: [], bc: null, bcIndex: 0, bcTimer: null };
let FV = null;

const teamOf = (a) => (S.meta && S.meta.teams[a]) || { abbr: a, primary: '#013369', name: a };
const league = () => (S.meta ? S.meta.league : {});
const corpo = () => $('jogoCorpo');

/* ------------------------------- render -------------------------------- */
export async function render(el) {
  ligar(el);
  pararReplay();
  const atual = ultimo('jogo');

  // 5.7: sem partida escolhida, a 1ª da semana selecionada.
  if (!S.gameId) {
    el.innerHTML = '<section class="block">' + spin('Abrindo a primeira partida da semana…') + '</section>';
    try {
      const jogos = await api.games(S.season, S.week);
      if (!atual()) return;
      if (!jogos.length) { el.innerHTML = '<section class="block">' + none('Nenhuma partida nesta semana.') + '</section>'; return; }
      S.gameId = jogos[0].gameId;
      S.playId = null;
      sincronizarUrl();
    } catch (e) {
      if (atual()) el.innerHTML = '<section class="block">' + oops('Falha ao carregar as partidas: ' + e.message) + '</section>';
      return;
    }
  }
  if (J.gameId !== S.gameId) J = { gameId: S.gameId, game: null, plays: [], bc: null, bcIndex: 0, bcTimer: null };

  el.innerHTML =
    '<section class="block" id="jogoCabBlock"><div id="jogoCab">' + spin('Carregando a partida…') + '</div></section>' +
    '<section class="block" id="materia" hidden></section>' +
    '<section class="block">' +
      '<div class="tabs" id="jogoAbas" role="tablist" aria-label="Seções da partida">' +
        ABAS.map(([k, l]) => '<button class="tab" role="tab" id="aba-' + k + '" data-aba="' + k +
          '" aria-controls="jogoCorpo">' + l + '</button>').join('') +
      '</div>' +
    '</section>' +
    '<section class="block" id="jogoCorpo" role="tabpanel"></section>';
  renderAba();

  try {
    const g = await carregarJogo();
    if (!atual() || g.gameId !== S.gameId) return;
    $('jogoCab').innerHTML = cabecalhoHtml(g);
    renderMateria(g);
  } catch (e) {
    if (atual()) $('jogoCab').innerHTML = oops('Falha ao carregar a partida: ' + e.message);
  }
}

/** Sai da página Jogo: o replay para e uma prancheta ainda carregando não desenha mais. */
export function sair() {
  pararReplay();
  seq.play++;
  seq.materia++;
}

async function carregarJogo() {
  if (!J.game) {
    const id = J.gameId;
    const g = await api.game(id);
    if (J.gameId === id) J.game = g;
    return g;
  }
  return J.game;
}

// 5.1: placar, os dois times e a semana (ou rodada) da partida.
function cabecalhoHtml(g) {
  const e = estadoDoJogo(g);
  const temPlacar = e.tipo === 'final' || e.tipo === 'aovivo' || e.tipo === 'final-espn';
  const hw = temPlacar && e.home > e.away;
  const aw = temPlacar && e.away > e.home;
  let centro;
  if (temPlacar) {
    centro = '<span class="score big"><span class="' + (aw || e.tipo === 'aovivo' ? '' : 'lose') + '">' + nm(e.away) +
      '</span><span class="sep">–</span><span class="' + (hw || e.tipo === 'aovivo' ? '' : 'lose') + '">' + nm(e.home) + '</span></span>' +
      '<span class="when">' + (e.tipo === 'aovivo' ? '<span class="badge-live">AO VIVO</span>' : 'FINAL' +
        (g.overtime ? ' <span class="badge-ot">PRORROG.</span>' : '')) + '</span>';
  } else if (e.tipo === 'agendado') {
    centro = '<span class="pending">A JOGAR</span><span class="when">' + esc(inicioLocal(g)) + '</span>';
  } else {
    centro = '<span class="sem-resultado">resultado ainda não disponível</span>';
  }
  const lado = (t, venceu) => '<span class="team' + (venceu ? ' win' : '') + '">' + badge(t, 'lg') +
    '<span class="name">' + esc(t.nick || t.abbr) + '</span></span>';
  return '<div class="jogo-cab">' +
    '<p class="jogo-rodada">' + esc(g.rodada || 'Semana ' + g.week) + ' · ' + g.season +
      (g.stadium ? ' · ' + esc(g.stadium) : '') + '</p>' +
    '<div class="jogo-placar">' + lado(g.away, aw) + '<span class="center">' + centro + '</span>' + lado(g.home, hw) + '</div>' +
  '</div>';
}

/* -------------------------------- abas --------------------------------- */
function renderAba() {
  document.querySelectorAll('#jogoAbas .tab').forEach((b) => {
    const ativa = b.dataset.aba === S.jogoAba;
    b.setAttribute('aria-selected', String(ativa));
    b.tabIndex = ativa ? 0 : -1;
    if (ativa) b.parentElement.scrollLeft = b.offsetLeft - (b.parentElement.clientWidth - b.offsetWidth) / 2;
  });
  const painel = corpo();
  if (!painel) return;
  painel.setAttribute('aria-labelledby', 'aba-' + S.jogoAba);
  if (S.jogoAba !== 'replay') pararReplay();
  if (S.jogoAba === 'prancheta') return coachLineup();
  seq.play++; // uma prancheta ainda carregando não pode desenhar sobre outra aba
  if (S.jogoAba === 'jogadas') return coachPlays();
  if (S.jogoAba === 'replay') return renderBroadcast();
  if (S.jogoAba === 'estatisticas') return comJogo(coachStats);
  return comJogo(coachBook);
}

// 5.6: trocar de aba mantém a partida e a jogada.
function trocarAba(aba) {
  if (!ABAS.some(([k]) => k === aba)) return;
  S.jogoAba = aba;
  sincronizarUrl();
  renderAba();
}

// 5.5: tocar numa jogada (Jogadas ou Replay) abre a Prancheta com ela.
function abrirJogada(playId) {
  S.playId = Number(playId);
  trocarAba('prancheta');
  window.scrollTo({ top: $('jogoAbas').getBoundingClientRect().top + window.scrollY - 80 });
}

async function comJogo(fn) {
  const aba = S.jogoAba;
  const id = J.gameId;
  corpo().innerHTML = spin('Carregando…');
  try {
    await carregarJogo();
  } catch (e) {
    if (S.jogoAba === aba && J.gameId === id) corpo().innerHTML = oops('Falha ao carregar a partida: ' + e.message);
    return;
  }
  if (S.jogoAba === aba && J.gameId === id && S.tela === 'jogo') fn();
}

// Eventos da página, ligados uma vez no container da tela.
function ligar(el) {
  if (el.dataset.ligado) return;
  el.dataset.ligado = '1';
  el.addEventListener('click', (e) => {
    const t = e.target;
    const aba = t.closest('[data-aba]');
    if (aba) { trocarAba(aba.dataset.aba); return; }
    const jogada = t.closest('[data-play]');
    if (jogada) { abrirJogada(jogada.dataset.play); return; }
    const jogador = t.closest('[data-player]');
    if (jogador) { S.playerId = jogador.dataset.player; ir('jogadores'); return; }
    if (t.closest('#prevPlay') || t.closest('#nextPlay')) {
      // Anterior/próxima andam entre as jogadas com formação (os chutes ficam no seletor).
      const list = J.plays.filter((p) => p.hasFormation || p.playId === S.playId);
      let idx = list.findIndex((p) => p.playId === S.playId);
      idx += t.closest('#nextPlay') ? 1 : -1;
      if (idx >= 0 && idx < list.length) { S.playId = list[idx].playId; sincronizarUrl(); coachLineup(); }
      return;
    }
    if (t.closest('#bcPlay')) toggleBc();
  });
  // setas entre as abas (padrão de tablist)
  el.addEventListener('keydown', (e) => {
    const tab = e.target.closest('#jogoAbas .tab');
    if (!tab || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    const i = ABAS.findIndex(([k]) => k === tab.dataset.aba) + (e.key === 'ArrowRight' ? 1 : -1);
    const k = ABAS[(i + ABAS.length) % ABAS.length][0];
    trocarAba(k);
    $('aba-' + k).focus();
  });
  el.addEventListener('change', (e) => {
    if (e.target.id === 'playPick') { S.playId = Number(e.target.value); sincronizarUrl(); coachLineup(); }
  });
  el.addEventListener('input', (e) => {
    if (e.target.id === 'bcRange') { stopBc(); bcStep(Number(e.target.value)); }
  });
}

/* --------------------------- matéria do jogo --------------------------- */
// Só links https de *.espn.com; http vira https.
const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl';
export function linkEspn(href) {
  try {
    const u = new URL(href);
    if (u.protocol === 'http:') u.protocol = 'https:';
    const h = u.hostname.toLowerCase();
    if (u.protocol !== 'https:' || !(h === 'espn.com' || h.endsWith('.espn.com'))) return null;
    return u.href;
  } catch (e) { return null; }
}

// 5.9: logo abaixo do placar; some se a matéria não existir ou falhar.
async function renderMateria(g) {
  const my = ++seq.materia;
  const box = $('materia');
  box.hidden = true;
  box.innerHTML = '';
  if (!g || !g.espnId || estadoDoJogo(g).tipo === 'agendado') return;
  try {
    const r = await fetch(ESPN + '/summary?event=' + encodeURIComponent(g.espnId));
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (my !== seq.materia) return;
    conferirPlacar(g, d);
    const a = d.article;
    if (!a || !a.headline) return;          // sem matéria: o bloco fica oculto
    const link = linkEspn(a.links && a.links.web && a.links.web.href);
    const fonte = (a.source ? a.source + ' · ' : '') + 'ESPN';
    box.innerHTML = '<article class="materia">' +
      '<h3>' + esc(a.headline) + '</h3>' +
      (a.description ? '<p>' + esc(a.description) + '</p>' : '') +
      '<div class="materia-rodape"><span>' + esc(dataHora(a.published)) + ' · ' + esc(fonte) + '</span>' +
      (link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener noreferrer">Ler na ESPN</a>' : '') +
      '</div></article>';
    box.hidden = false;
  } catch (e) {
    if (my === seq.materia) console.warn('matéria indisponível:', e.message);
  }
}

// Se a ESPN e o nflverse divergirem no placar final, vale o nflverse (o que já é exibido).
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

/* ------------------------------ prancheta ------------------------------ */
async function ensurePlays() {
  if (!J.plays.length) {
    const id = J.gameId;
    const plays = await api.plays(id);
    if (J.gameId === id) J.plays = plays;
  }
  if (!S.playId || !J.plays.some((p) => p.playId === S.playId)) {
    const first = J.plays.filter((p) => p.hasFormation)[0] || J.plays[0];
    S.playId = first ? first.playId : null;
  }
  return J.plays;
}

async function coachLineup() {
  const my = ++seq.play;
  const body = corpo();
  body.innerHTML = spin('Carregando a prancheta…');
  try {
    await ensurePlays();
    if (my !== seq.play) return; // o usuário já escolheu outra jogada
    if (!S.playId) { body.innerHTML = none('Este jogo ainda não tem jogadas na fonte.'); return; }
    sincronizarUrl();

    body.innerHTML =
      '<div class="card">' +
        '<div class="card-head"><h3>Prancheta</h3><span class="muted" id="fieldSub"></span></div>' +
        '<div class="field-legend" id="fieldLegend"></div>' +
        '<div class="field-wrap" id="fieldWrap"><div class="field" id="field"></div></div>' +
        '<div id="avisoField"></div>' +
        '<div id="dotInfo"></div>' +
      '</div>' +
      '<div class="card"><div class="card-head"><h3>Jogada</h3></div><div id="playMeta"></div></div>' +
      '<div class="card">' +
        '<div class="card-head"><h3>Trocar jogada</h3><span class="muted">' + J.plays.length + ' jogadas no jogo</span></div>' +
        '<select class="select" id="playPick" aria-label="Escolher jogada"></select>' +
        '<div class="btn-row"><button class="btn-sec" id="prevPlay">‹ Anterior</button>' +
        '<button class="btn-sec" id="nextPlay">Próxima ›</button></div>' +
      '</div>';

    $('playPick').innerHTML = J.plays.map((p) =>
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

async function loadFieldPlay(my) {
  const gameId = J.gameId, playId = S.playId;
  const card = J.plays.find((q) => q.playId === playId) || {};
  if (!card.hasFormation) {
    // 5.8: sem nenhum dado de formação, os dados da jogada e a mensagem no lugar da prancheta.
    FV = null;
    $('fieldWrap').innerHTML = '<div class="formacao-indisponivel">Formação indisponível para esta jogada.</div>';
    $('fieldLegend').innerHTML = '';
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
  FV = new Field($('field'), tr, teamOf);
  FV.onSelect = (pl) => { $('dotInfo').innerHTML = pl ? dotCard(pl) : ''; };

  $('fieldSub').textContent = 'ataque joga para cima';
  $('fieldLegend').innerHTML = legendaHtml(p, coresDosLados(p, teamOf));
  $('avisoField').innerHTML = tr.ilustrativo
    ? '<p class="aviso"><b>Esquema ilustrativo:</b> posições-modelo da formação, não o alinhamento real da jogada.' +
      (tr.generico ? ' A fonte ainda não publicou os jogadores desta jogada: posições genéricas, sem nomes.' : '') +
      '</p>'
    : '';
  FV.setFrame(tr.snapIndex || 0);

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
  const lista = J.plays.filter((q) => q.hasFormation);
  const i = lista.findIndex((q) => q.playId === playId);
  if (i < 0) return;
  [lista[i + 1], lista[i - 1]].forEach((q) => {
    if (q) api.tracking(gameId, q.playId).catch(() => {});
  });
}

// Quem ataca e quem defende, com a cor e o formato de cada lado no campo.
function legendaHtml(p, cores) {
  const lado = (forma, time, cor, papel) => time
    ? '<span><i class="sw ' + forma + '" style="background:' + esc(cor || teamOf(time).primary) + '"></i>' +
      esc(time) + ' · ' + papel + '</span>' : '';
  return lado('circ', p.offense, cores.offense, 'ataque') + lado('quad', p.defense, cores.defense, 'defesa') +
    '<span><i class="sw los"></i>Linha de scrimmage</span><span><i class="sw fd"></i>1ª descida</span>';
}

// Só as linhas com dado: o que a fonte não tem fica fora.
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
  return '<p class="play-desc">' + esc(p.description) + '</p>' +
    (p.semFormacao ? '<div class="tags"><span class="tag-chip">SEM DADOS DE FORMAÇÃO</span></div>' : '') +
    rows.map((r) => '<div class="stat-row"><span class="k">' + r[0] + '</span><span class="v">' + r[1] + '</span></div>').join('') +
    (p.tags && p.tags.length ? '<div class="tags">' + p.tags.map((t) =>
      '<span class="tag-chip ' + tagCls(t) + '">' + esc(t) + '</span>').join('') + '</div>' : '');
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
  const inner = badge(teamOf(p.team), 'sm') +
    '<span class="grow"><b>' + esc(p.name || 'Posição genérica') + '</b><small>' +
      (isNum(p.jersey) ? '#' + p.jersey + ' · ' : '') + esc(p.position || '') +
      ' · ' + (p.side === 'defense' ? 'defesa' : 'ataque') + '</small></span>' +
    (p.name ? rateChip(p.rating) : '');
  return p.name
    ? '<button class="row-card" data-player="' + esc(p.nflId) + '">' + inner + '</button>'
    : '<div class="row-card">' + inner + '</div>';
}

/* ------------------------------- jogadas ------------------------------- */
async function coachPlays() {
  const id = J.gameId;
  await into(corpo(), async () => {
    await ensurePlays();
    if (!J.plays.length) return none('Sem jogadas neste jogo.');
    const byQ = {};
    J.plays.forEach((p) => { (byQ[p.quarter] = byQ[p.quarter] || []).push(p); });
    return Object.keys(byQ).sort().map((q) =>
      '<div class="sec-head"><h3>' + (q > 4 ? 'Prorrogação' : q + 'º quarto') + '</h3>' +
      '<span class="muted">' + byQ[q].length + ' jogadas</span></div>' +
      '<div class="list">' + byQ[q].map(playRow).join('') + '</div>').join('');
  }, 'Carregando as jogadas…', () => S.jogoAba === 'jogadas' && J.gameId === id);
}

function playRow(p) {
  let tone = '';
  if (p.tags.indexOf('TOUCHDOWN') >= 0) tone = 'td';
  else if (p.passResult === 'S') tone = 'sack';
  else if (p.passResult === 'IN' || p.tags.indexOf('FUMBLE') >= 0) tone = 'turnover';
  else if (p.result >= 20) tone = 'big';
  const gain = p.result > 0 ? 'pos' : p.result < 0 ? 'neg' : 'zero';
  const chips = (p.semFormacao ? '<span class="tag-chip">SEM DADOS DE FORMAÇÃO</span>' : '') +
    (p.coverage ? '<span class="tag-chip blue">' + esc(p.coverage) + '</span>' : '') +
    (p.formation ? '<span class="tag-chip">' + esc(p.formation) + '</span>' : '') +
    (isNum(p.timeToThrow) ? '<span class="tag-chip">' + secs(p.timeToThrow) + ' pocket</span>' : '') +
    (p.pressured ? '<span class="tag-chip red">PRESSIONADO</span>' : '') +
    p.tags.map((t) => '<span class="tag-chip ' + tagCls(t) + '">' + esc(t) + '</span>').join('');
  return '<button class="play-row' + (tone ? ' ' + tone : '') + '"' + (p.playId === S.playId ? ' aria-current="true"' : '') +
    ' data-play="' + p.playId + '">' +
    '<span class="play-head">' + badge(teamOf(p.offense), 'sm') +
      '<span class="sit">' + (isNum(p.down) ? ordDown(p.down, p.yardsToGo) : esc(p.passResultLabel)) + '</span>' +
      '<span class="clk">Q' + p.quarter + ' ' + esc(p.clock || '') + '</span>' +
      '<span class="gain ' + gain + '">' + signed(p.result) + '</span></span>' +
    '<span class="play-desc">' + esc(p.description) + '</span>' +
    (chips ? '<span class="tags">' + chips + '</span>' : '') +
  '</button>';
}

/* ---------------------------- estatísticas ----------------------------- */
function barra(label, l, r, fmtFn, lowerBetter) {
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
}

function coachStats() {
  const g = J.game;
  const A = g.away, H = g.home;
  const ao = g.teams.away.offense, ho = g.teams.home.offense;
  const ad = g.teams.away.defense, hd = g.teams.home.defense;
  if (!Object.keys(ao).length && !Object.keys(ho).length) {
    corpo().innerHTML = none('Este jogo ainda não tem jogadas na fonte.');
    return;
  }
  // Linha só quando algum dos lados tem o dado.
  const cmp = barra;
  const terceira = (o) => (isNum(o.thirdDownAtt) ? o.thirdDownConv + '/' + o.thirdDownAtt : '—');
  const lados = '<div class="cmp-lados">' + badge(A, 'sm') + badge(H, 'sm') + '</div>';
  const card = (titulo, sub, linhas) => (linhas.join('')
    ? '<div class="card"><div class="card-head"><h3>' + titulo + '</h3>' + (sub ? '<span class="muted">' + sub + '</span>' : '') +
      '</div>' + linhas.join('') + '</div>' : '');
  const pocket = [
    isNum(ao.timeToThrow) ? statRow('Tempo p/ lançar · ' + A.abbr, secs(ao.timeToThrow), delta(ao.timeToThrow, league().timeToThrow, true)) : '',
    isNum(ho.timeToThrow) ? statRow('Tempo p/ lançar · ' + H.abbr, secs(ho.timeToThrow), delta(ho.timeToThrow, league().timeToThrow, true)) : '',
    isNum(ao.pressureRateAllowed) ? statRow('Pressionado · ' + A.abbr, pct(ao.pressureRateAllowed), delta(ao.pressureRateAllowed, league().pressureRate, true, true)) : '',
    isNum(ho.pressureRateAllowed) ? statRow('Pressionado · ' + H.abbr, pct(ho.pressureRateAllowed), delta(ho.pressureRateAllowed, league().pressureRate, true, true)) : '',
  ];

  corpo().innerHTML =
    card('Ataque', 'passes e corridas', [
      lados,
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
    card('Pressão e proteção', '', [
      lados,
      cmp('Sacks aplicados', ad.sacks, hd.sacks, (v) => nm(v)),
      cmp('Pressões geradas', ad.pressures, hd.pressures, (v) => nm(v)),
      cmp('Taxa de pressão', ad.pressureRate, hd.pressureRate, (v) => pct(v)),
      cmp('Taxa de blitz', ad.blitzRate, hd.blitzRate, (v) => pct(v)),
      cmp('Interceptações', ad.interceptions, hd.interceptions, (v) => nm(v)),
    ]) +
    card('Relógio do pocket', '', pocket);
}

function statRow(k, v, extra) {
  return '<div class="stat-row"><span class="k">' + esc(k) + '</span>' +
    '<span class="v">' + v + (extra ? ' ' + extra : '') + '</span></div>';
}

/* ------------------------------- playbook ------------------------------ */
function coachBook() {
  const g = J.game;
  // Bloco sem dado nenhum fica fora: 2026 ainda não tem pessoal nem cobertura.
  const block = (title, sub, items, def) => (!items || !items.length ? '' :
    '<div class="card"><div class="card-head"><h3>' + esc(title) + '</h3><span class="muted">' + esc(sub) + '</span></div>' +
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
  corpo().innerHTML = html || none('Sem dados de formação neste jogo.');
}

/* -------------------------------- replay ------------------------------- */
const ICONE_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>';
const ICONE_PAUSA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13M16 5.5v13"/></svg>';

async function renderBroadcast() {
  const id = J.gameId;
  const body = corpo();
  body.innerHTML = spin('Montando o replay…');
  try {
    if (!J.bc) {
      try {
        const bc = await api.broadcast(id);
        if (J.gameId === id) { J.bc = bc; J.bcIndex = 0; }
      } catch (e) {
        if (S.jogoAba === 'replay' && J.gameId === id) body.innerHTML = none('Este jogo ainda não tem jogadas na fonte.');
        return;
      }
    }
    if (S.jogoAba !== 'replay' || J.gameId !== id || S.tela !== 'jogo') return;
    body.innerHTML =
      '<div class="card" id="bcScore"></div>' +
      '<div class="bc-bar">' +
        '<button class="icon-btn" id="bcPlay" aria-label="Reproduzir a narração">' + ICONE_PLAY + '</button>' +
        '<input type="range" id="bcRange" min="0" max="' + (J.bc.feed.length - 1) + '" value="' + J.bcIndex +
          '" aria-label="Posição no jogo" />' +
        '<span class="pos" id="bcPos"></span>' +
      '</div>' +
      '<div class="sec-head"><h3>Narração</h3><span class="muted">jogada a jogada · toque para ver na prancheta</span></div>' +
      '<div class="timeline" id="bcFeed"></div>' +
      '<div class="card"><div class="card-head"><h3>Painel acumulado</h3><span class="muted">até a jogada atual</span></div>' +
        '<div id="bcPanel"></div></div>';
    paintBc();
  } catch (e) {
    body.innerHTML = oops('Falha no replay: ' + e.message);
  }
}

function paintBc() {
  const bc = J.bc;
  const i = J.bcIndex;
  const p = bc.feed[i];
  const hs = p.score.home, as = p.score.away;

  $('bcScore').innerHTML =
    '<div class="live-score">' +
      '<span class="team">' + badge(bc.away, 'lg') + '<span class="big' + (as > hs ? ' lead' : '') + '">' +
        nm(as) + '</span><span class="name">' + esc(bc.away.nick || bc.away.abbr) + '</span></span>' +
      '<span class="center"><span class="qtr">' + (p.quarter > 4 ? 'PRORROG.' : 'Q' + p.quarter) + ' · ' + esc(p.clock || '') + '</span>' +
        '<span class="situ">' + esc(p.offense || '') + ' com a bola<br>' +
          (isNum(p.down) ? ordDown(p.down, p.yardsToGo) : esc(p.passResultLabel || '')) + '</span></span>' +
      '<span class="team">' + badge(bc.home, 'lg') + '<span class="big' + (hs > as ? ' lead' : '') + '">' +
        nm(hs) + '</span><span class="name">' + esc(bc.home.nick || bc.home.abbr) + '</span></span>' +
    '</div>';

  $('bcPos').textContent = (i + 1) + '/' + bc.feed.length;
  $('bcRange').value = i;

  // Mostra as últimas jogadas, a atual no topo. O tom da jogada vira a cor do
  // marcador (a fonte manda um emoji como ícone; a interface nova não usa emoji).
  const from = Math.max(0, i - 11);
  $('bcFeed').innerHTML = bc.feed.slice(from, i + 1).reverse().map((q, k) =>
    '<button class="tl-item ' + esc(q.narration.tone) + '"' + (k === 0 ? ' aria-current="true"' : '') +
      ' data-play="' + q.playId + '">' +
      '<span class="time">' + esc(q.clock || '') + '</span>' +
      '<span class="ev"><b>' + esc(q.narration.headline) + '</b>' + esc(q.narration.detail) +
      (q.narration.context ? '<span class="ctx">' + esc(q.narration.context) + '</span>' : '') +
      '</span></button>').join('');

  const ch = p.cumulative.home, ca = p.cumulative.away;
  $('bcPanel').innerHTML =
    '<div class="cmp-lados">' + badge(bc.away, 'sm') + badge(bc.home, 'sm') + '</div>' +
    barra('Jogadas', ca.plays, ch.plays, (v) => nm(v)) +
    barra('Jardas', ca.yards, ch.yards, (v) => nm(v)) +
    barra('Passes completos', ca.completions, ch.completions, (v) => nm(v)) +
    barra('Touchdowns', ca.touchdowns, ch.touchdowns, (v) => nm(v)) +
    barra('Sacks sofridos', ca.sacksTaken, ch.sacksTaken, (v) => nm(v)) +
    // Pressões só existem onde a fonte traz (participação até 2025).
    (ca.pressures || ch.pressures ? barra('Pressões da defesa', ca.pressures, ch.pressures, (v) => nm(v)) : '');
}

function bcStep(n) {
  if (!J.bc || !$('bcScore')) return;
  J.bcIndex = Math.max(0, Math.min(J.bc.feed.length - 1, n));
  paintBc();
  if (J.bcIndex >= J.bc.feed.length - 1) stopBc();
}

// Uma jogada a cada 1,4 s ÷ a velocidade das Configurações (0,5×, 1× ou 2×).
const passoMs = () => 1400 / lerConfig().velocidadeReplay;

function toggleBc() {
  if (J.bcTimer) return stopBc();
  if (!J.bc) return;
  if (J.bcIndex >= J.bc.feed.length - 1) J.bcIndex = 0;
  J.bcTimer = setInterval(() => bcStep(J.bcIndex + 1), passoMs());
  const b = $('bcPlay');
  b.innerHTML = ICONE_PAUSA;
  b.setAttribute('aria-label', 'Pausar a narração');
}

function stopBc() {
  clearInterval(J.bcTimer);
  J.bcTimer = null;
  const b = $('bcPlay');
  if (b) { b.innerHTML = ICONE_PLAY; b.setAttribute('aria-label', 'Reproduzir a narração'); }
}
const pararReplay = stopBc;

// Velocidade mudou com o replay andando: continua na nova velocidade.
aoMudar(() => {
  if (!J.bcTimer) return;
  clearInterval(J.bcTimer);
  J.bcTimer = setInterval(() => bcStep(J.bcIndex + 1), passoMs());
});
