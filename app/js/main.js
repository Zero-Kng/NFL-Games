/* ==========================================================================
   NFL GAMES — casca da interface nova (spec novo-visual, tarefa 2).
   Estado compartilhado, cabeçalho, menu lateral, busca, filtros de temporada
   e semana, barra inferior e roteador. Cada tela registra um render(); até as
   tarefas 3 a 8, as telas são esqueletos.
   ========================================================================== */
import { api } from './api.js';
import { $, esc, icone, oops } from './ui.js';
import { reduzirMovimento, aoMudarMovimento } from './config.js';

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
};

const ABAS = ['prancheta', 'jogadas', 'replay', 'estatisticas', 'playbook'];

/* ------------------------------ as telas ------------------------------ */
// filtros: quais linhas de filtro a tela usa ('temporada', 'semana').
function esqueleto(titulo, tarefa) {
  return (el) => {
    el.innerHTML = '<section class="block"><div class="block-head"><h2>' + esc(titulo) + '</h2></div>' +
      '<div class="state">' + icone('obra') + 'Esta tela entra na tarefa ' + tarefa + ' da spec novo-visual.</div></section>';
  };
}
export const TELAS = {
  inicio: { titulo: 'Início', filtros: ['temporada', 'semana'], render: esqueleto('Início', 3) },
  jogo: { titulo: 'Jogo', filtros: [], render: esqueleto('Jogo', 4) },
  jogadores: { titulo: 'Jogadores', filtros: ['temporada'], render: esqueleto('Jogadores', 6) },
  noticias: { titulo: 'Notícias', filtros: ['temporada', 'semana'], render: esqueleto('Notícias', 7) },
  config: { titulo: 'Configurações', filtros: [], render: esqueleto('Configurações', 8) },
  sobre: { titulo: 'Sobre os dados', filtros: [], render: esqueleto('Sobre os dados', 8) },
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

function sincronizarUrl() {
  const u = new URLSearchParams();
  if (S.season) u.set('season', S.season);
  if (S.week) u.set('week', S.week);
  if (S.gameId) u.set('game', S.gameId);
  if (S.tela !== 'inicio') u.set('screen', S.tela);
  if (S.tela === 'jogo' && S.jogoAba !== 'prancheta') u.set('aba', S.jogoAba);
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
// Os resultados entram na tarefa 7.
function setBusca(abrir) {
  $('searchbar').hidden = !abrir;
  $('btnSearch').setAttribute('aria-expanded', String(abrir));
  if (abrir) {
    $('searchInput').focus();
  } else {
    const estava = $('searchInput').value !== '' || document.activeElement === $('searchInput');
    $('searchInput').value = '';
    $('searchResults').hidden = true;
    $('searchResults').innerHTML = '';
    if (estava) $('btnSearch').focus();
  }
}

/* ------------------------------- eventos ------------------------------- */
document.addEventListener('click', (e) => {
  const t = e.target.closest('button, [data-go], [data-game]');
  if (!t) return;
  if (t.dataset.go) { ir(t.dataset.go); return; }
  if (t.dataset.season) { mudarTemporada(Number(t.dataset.season)); return; }
  if (t.dataset.week) { mudarSemana(Number(t.dataset.week)); return; }
  if (t.dataset.game) { selecionarJogo(t.dataset.game, { aba: t.dataset.aba, playId: t.dataset.play }); }
});
$('btnMenu').addEventListener('click', () => setMenu(true));
$('scrim').addEventListener('click', () => setMenu(false));
$('btnSearch').addEventListener('click', () => setBusca(true));
$('btnSearchClose').addEventListener('click', () => setBusca(false));
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
      'API indisponível. Rode python server/serve.py (ou o RODAR.bat) e abra http://127.0.0.1:8000/novo.html. ' +
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

  const pedida = u.get('screen') || 'inicio';
  const [tela, aba] = LEGADO[pedida] || [pedida, u.get('aba')];
  atualizarSidebar();
  ir(TELAS[tela] ? tela : 'inicio', { aba });
}

boot();
