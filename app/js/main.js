/* ==========================================================================
   NFL GAMES — casca da interface nova (spec novo-visual, tarefa 2).
   Estado compartilhado, cabeçalho, menu lateral, busca, filtros de temporada
   e semana, barra inferior e roteador. Cada tela registra um render() (e,
   se precisar, um sair()).
   ========================================================================== */
import { api, ultimo } from './api.js';
import { $, esc, oops, badge, rateChip } from './ui.js';
import { reduzirMovimento, aoMudarMovimento } from './config.js';
import * as inicio from './telas/inicio.js';
import * as jogo from './telas/jogo.js';
import * as jogadores from './telas/jogadores.js';
import * as noticias from './telas/noticias.js';
import * as extras from './telas/extras.js';

/* ------------------------------- estado ------------------------------- */
export const S = {
  meta: null,
  tela: 'inicio',
  season: null,
  week: null,
  gameId: null,
  playId: null,
  jogoAba: 'prancheta',
  playerId: null,
  filtroTime: null,
  live: {},
  liveFalha: false,
};

const ABAS = ['prancheta', 'jogadas', 'replay', 'estatisticas', 'playbook'];

/* ------------------------------ as telas ------------------------------ */
// filtros: quais linhas de filtro a tela usa ('temporada', 'semana'); sair(), se houver,
// roda quando o usuário deixa a tela (para timers como o do carrossel).
export const TELAS = {
  inicio: { titulo: 'Início', filtros: ['temporada', 'semana'], render: inicio.render, sair: inicio.sair },
  jogo: { titulo: 'Jogo', filtros: [], render: jogo.render, sair: jogo.sair },
  jogadores: { titulo: 'Jogadores', filtros: ['temporada'], render: jogadores.render },
  noticias: { titulo: 'Notícias', filtros: ['temporada', 'semana'], render: noticias.render },
  config: { titulo: 'Configurações', filtros: [], render: extras.renderConfig },
  sobre: { titulo: 'Sobre os dados', filtros: [], render: extras.renderSobre },
};

/* ------------------------------ filtros ------------------------------- */
export const temporadaMeta = () => (S.meta ? S.meta.seasons.find((t) => t.season === S.season) : null);
export const semanaMeta = () => { const t = temporadaMeta(); return t ? t.weeks.find((w) => w.week === S.week) : null; };
export const rotuloSemana = (w) => (w && w.gameType && w.gameType !== 'REG' ? w.rodada : 'Semana ' + (w ? w.week : ''));

function semanaPadrao(season) {
  const t = S.meta.seasons.find((x) => x.season === season);
  if (!t) return null;
  return t.weeks.some((w) => w.week === t.currentWeek) ? t.currentWeek : t.weeks[0].week;
}

function renderFiltros() {
  const usa = TELAS[S.tela].filtros;
  $('filters').hidden = !usa.length;
  $('seasonRow').hidden = !usa.includes('temporada');
  $('weekRow').hidden = !usa.includes('semana');
  $('seasonChips').innerHTML = S.meta.seasons.map((t) =>
    '<button class="chip" data-season="' + t.season + '" aria-pressed="' + (t.season === S.season) + '">' +
    t.season + '</button>').join('');
  const t = temporadaMeta();
  // Temporada regular como "Sem n"; playoffs pelo nome da rodada (3.2).
  $('weekChips').innerHTML = (t ? t.weeks : []).map((w) => {
    const po = w.gameType !== 'REG';
    return '<button class="chip week' + (po ? ' playoff' : '') + '" data-week="' + w.week + '" aria-pressed="' +
      (w.week === S.week) + '" aria-label="' + esc(rotuloSemana(w) + ', ' + w.games + ' jogos') + '">' +
      esc(po ? w.rodada : 'Sem ' + w.week) + '</button>';
  }).join('');
  centralizarAtivos();
}

function centralizarAtivos() {
  ['seasonChips', 'weekChips'].forEach((id) => {
    const box = $(id);
    const ativo = box.querySelector('[aria-pressed="true"]');
    if (ativo) box.scrollLeft = ativo.offsetLeft - (box.clientWidth - ativo.offsetWidth) / 2;
  });
}

export function mudarTemporada(season) {
  if (season === S.season) return;
  S.season = season;
  S.week = semanaPadrao(season);
  S.gameId = null;
  S.playId = null;
  S.playerId = null;
  aoMudarFiltro();
}

export function mudarSemana(week) {
  if (week === S.week) return;
  S.week = week;
  S.gameId = null;
  S.playId = null;
  aoMudarFiltro();
}

function aoMudarFiltro() {
  renderFiltros();
  atualizarSidebar();
  sincronizarUrl();
  TELAS[S.tela].render($(S.tela), { motivo: 'filtro' });
}

/* ------------------------------ navegação ----------------------------- */
export function ir(tela, opcoes) {
  if (!TELAS[tela]) tela = 'inicio';
  opcoes = opcoes || {};
  if (tela === 'jogo' && ABAS.includes(opcoes.aba)) S.jogoAba = opcoes.aba;
  if (S.tela !== tela && TELAS[S.tela].sair) TELAS[S.tela].sair();
  S.tela = tela;
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === tela));
  document.querySelectorAll('[data-go]').forEach((b) => {
    if (b.dataset.go === tela) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  $('pageTitle').textContent = TELAS[tela].titulo;
  document.title = TELAS[tela].titulo + ' · NFL Games';
  setMenu(false);
  setBusca(false);
  renderFiltros();
  sincronizarUrl();
  window.scrollTo({ top: 0 });
  TELAS[tela].render($(tela), { motivo: 'ir' });
}

/** Abre a página Jogo com a partida (e a aba) escolhida. */
export function selecionarJogo(gameId, opcoes) {
  opcoes = opcoes || {};
  const novo = Number(gameId);
  if (novo !== S.gameId) S.playId = null;
  S.gameId = novo;
  if (opcoes.playId) S.playId = Number(opcoes.playId);
  ir('jogo', { aba: opcoes.aba });
}

export function sincronizarUrl() {
  const u = new URLSearchParams();
  if (S.season) u.set('season', S.season);
  if (S.week) u.set('week', S.week);
  if (S.gameId) u.set('game', S.gameId);
  if (S.tela !== 'inicio') u.set('screen', S.tela);
  if (S.tela === 'jogo' && S.jogoAba !== 'prancheta') u.set('aba', S.jogoAba);
  if (S.tela === 'jogo' && S.jogoAba === 'prancheta' && S.playId) u.set('play', S.playId);
  if (S.tela === 'jogadores' && S.playerId) u.set('jogador', S.playerId);
  history.replaceState(null, '', location.pathname + '?' + u.toString());
}

/* ----------------------------- menu lateral ---------------------------- */
function setMenu(abrir) {
  const sb = $('sidebar');
  const estava = sb.classList.contains('open');
  sb.classList.toggle('open', abrir);
  sb.setAttribute('aria-hidden', String(!abrir));
  sb.inert = !abrir;
  $('scrim').hidden = !abrir;
  $('btnMenu').setAttribute('aria-expanded', String(abrir));
  if (abrir) (sb.querySelector('[aria-current="page"]') || sb.querySelector('.side-item')).focus();
  else if (estava) $('btnMenu').focus();
}

function atualizarSidebar() {
  const t = temporadaMeta();
  $('sidebarSub').textContent = t ? 'Temporada ' + t.season + ' · ' + rotuloSemana(semanaMeta()) : '';
}

/* -------------------------------- busca -------------------------------- */
// A lupa abre o campo com o cursor nele (8.1); Cancelar ou Esc fecha e limpa (8.6).
// Resultados em 3 grupos (8.2): Times (de meta.teams) e Notícias (de /api/news da
// temporada inteira) filtrados aqui; Jogadores pela API, com "só o último vence" (8.5).
const BUSCA_MS = 200;
let buscaTimer = null;
const normal = (t) => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

function buscar() {
  clearTimeout(buscaTimer);
  const termo = $('searchInput').value.slice(0, 100).trim();       // S.2
  const box = $('searchResults');
  const atual = ultimo('busca');
  if (!termo) { box.hidden = true; box.innerHTML = ''; return; }
  const n = normal(termo);
  const times = Object.values(S.meta.teams)
    .filter((t) => normal(t.abbr + ' ' + t.name + ' ' + t.nick).includes(n)).slice(0, 5);
  const pedido = { season: S.season };
  let noticiasAchadas = null, jogadoresAchados = null;
  const pintar = () => { if (atual()) renderBusca(termo, times, jogadoresAchados, noticiasAchadas); };
  pintar();
  api.news(pedido.season)
    .then((ns) => { noticiasAchadas = ns.filter((x) => normal(textoDaNoticia(x)).includes(n)).slice(0, 6); })
    .catch(() => { noticiasAchadas = []; })
    .then(pintar);
  // Os jogadores esperam a digitação parar um pouco; resposta de um termo antigo é descartada.
  buscaTimer = setTimeout(() => {
    api.players(pedido.season, { q: termo, limit: 8 })
      .then((ps) => { jogadoresAchados = ps; })
      .catch(() => { jogadoresAchados = []; })
      .then(pintar);
  }, BUSCA_MS);
}

// A manchete usa a sigla ("TB vence DAL"); a busca acha também pelo nome e pelo apelido dos times.
function textoDaNoticia(x) {
  return x.titulo + ' ' + (x.times || []).map((a) => { const t = S.meta.teams[a] || {}; return a + ' ' + (t.name || '') + ' ' + (t.nick || ''); }).join(' ');
}

function renderBusca(termo, times, jogs, ns) {
  const box = $('searchResults');
  const grupo = (titulo, itens) => '<div class="sr-group" role="presentation">' + titulo + '</div>' + itens;
  let html = '';
  if (times.length) {
    html += grupo('Times', times.map((t) =>
      '<button class="sr-item" data-busca-time="' + esc(t.abbr) + '">' + badge(t, 'sm') +
      '<span><b>' + esc(t.name) + '</b><small>' + esc(t.abbr) + ' · jogos na semana</small></span></button>').join(''));
  }
  if (jogs === null) html += grupo('Jogadores', '<div class="sr-carregando">Buscando jogadores…</div>');
  else if (jogs.length) {
    html += grupo('Jogadores', jogs.map((p) =>
      '<button class="sr-item" data-busca-jogador="' + esc(p.nflId) + '">' + rateChip(p.rating) +
      '<span><b>' + esc(p.name) + '</b><small>' + esc(p.position) + ' · ' + esc(p.team) + ' · ' + esc(p.roleLabel) +
      '</small></span></button>').join(''));
  }
  if (ns && ns.length) {
    html += grupo('Notícias', ns.map((x) =>
      '<button class="sr-item" data-game="' + esc(x.gameId) + '">' +
      '<span><b>' + esc(x.titulo) + '</b><small>' + esc(x.tag) + ' · ' + esc(x.rodada || 'Semana ' + x.week) +
      '</small></span></button>').join(''));
  }
  if (!html && jogs !== null && ns !== null) {
    html = '<div class="sr-empty">Nada encontrado para “' + esc(termo) + '”.</div>';       // 8.4
  }
  box.innerHTML = html;
  box.hidden = !html;
}

function setBusca(abrir) {
  $('searchbar').hidden = !abrir;
  $('btnSearch').setAttribute('aria-expanded', String(abrir));
  if (abrir) {
    $('searchInput').focus();
  } else {
    const estava = $('searchInput').value !== '' || document.activeElement === $('searchInput');
    $('searchInput').value = '';
    clearTimeout(buscaTimer);
    ultimo('busca');                    // descarta o que ainda estiver a caminho
    $('searchResults').hidden = true;
    $('searchResults').innerHTML = '';
    if (estava) $('btnSearch').focus();
  }
}

/* ------------------------------- eventos ------------------------------- */
document.addEventListener('click', (e) => {
  const t = e.target.closest('button, [data-go], [data-game]');
  if (!t) return;
  if (t.dataset.buscaTime) { const a = t.dataset.buscaTime; setBusca(false); inicio.filtrarPorTime(a); return; }
  if (t.dataset.buscaJogador) { const id = t.dataset.buscaJogador; setBusca(false); jogadores.abrirJogador(id); return; }
  if (t.dataset.go) { ir(t.dataset.go); return; }
  if (t.dataset.season) { mudarTemporada(Number(t.dataset.season)); return; }
  if (t.dataset.week) { mudarSemana(Number(t.dataset.week)); return; }
  if (t.dataset.game) { selecionarJogo(t.dataset.game, { aba: t.dataset.aba, playId: t.dataset.play }); }
});
$('btnMenu').addEventListener('click', () => setMenu(true));
$('scrim').addEventListener('click', () => setMenu(false));
$('btnSearch').addEventListener('click', () => setBusca(true));
$('btnSearchClose').addEventListener('click', () => setBusca(false));
$('searchInput').addEventListener('input', buscar);
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if ($('sidebar').classList.contains('open')) setMenu(false);
  else if (!$('searchbar').hidden) setBusca(false);
});

function aplicarMovimento() {
  document.documentElement.dataset.movimento = reduzirMovimento() ? 'reduzido' : 'normal';
}
aoMudarMovimento(aplicarMovimento);

/* --------------------------------- boot -------------------------------- */
// Links antigos (2.6): ?screen=coach|commentator|scout abrem a tela nova equivalente.
const LEGADO = {
  coach: ['jogo', 'prancheta'], commentator: ['jogo', 'replay'], scout: ['jogadores'], home: ['inicio'],
};

async function boot() {
  aplicarMovimento();
  const u = new URLSearchParams(location.search);
  try {
    S.meta = await api.meta();
  } catch (e) {
    $('inicio').classList.add('active');
    $('inicio').innerHTML = '<section class="block">' + oops(
      'API indisponível. Abra o NFL-Games (ou rode python rodar.py) e acesse http://127.0.0.1:8000. ' +
      'Detalhe: ' + e.message) + '</section>';
    $('filters').hidden = true;
    return;
  }
  const querTemporada = Number(u.get('season'));
  const querSemana = Number(u.get('week'));
  S.season = S.meta.seasons.some((t) => t.season === querTemporada) ? querTemporada : S.meta.season;
  S.week = temporadaMeta().weeks.some((w) => w.week === querSemana) ? querSemana : semanaPadrao(S.season);
  if (Number(u.get('game'))) S.gameId = Number(u.get('game'));
  if (Number(u.get('play'))) S.playId = Number(u.get('play'));
  if (u.get('jogador')) S.playerId = u.get('jogador').slice(0, 40);

  const pedida = u.get('screen') || 'inicio';
  const [tela, aba] = LEGADO[pedida] || [pedida, u.get('aba')];
  atualizarSidebar();
  ir(TELAS[tela] ? tela : 'inicio', { aba });
}

boot();
