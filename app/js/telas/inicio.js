/* ==========================================================================
   Tela Início (spec novo-visual, tarefa 3): carrossel com as 4 primeiras
   notícias da semana, os dois cartões de resumo e os jogos da semana com o
   placar ao vivo. estadoDoJogo, gameCard e aoVivo foram movidos do app.js
   (spec dados-externos): a lógica é a mesma; mudam o HTML e as classes.
   ========================================================================== */
import { api, ultimo } from '../api.js';
import { $, esc, badge, isNum, nm, inicioLocal, into, none, icone } from '../ui.js';
import { ler as lerConfig, aoMudar, reduzirMovimento, aoMudarMovimento } from '../config.js';
import { S, semanaMeta, rotuloSemana, ir } from '../main.js';

const AVANCO_MS = 5000;
const NO_CARROSSEL = 4;

let jogos = [];               // jogos da semana exibida (sem o filtro por time)
const time = (abbr) => (S.meta && S.meta.teams[abbr]) || { abbr, primary: '#013369', name: abbr };

/* ------------------------------ render ------------------------------- */
export function render(el) {
  ligar(el);
  aoVivo.parar();
  carrossel.parar();
  S.live = {};
  S.liveFalha = false;
  el.innerHTML =
    '<section class="block" id="heroBlock" hidden>' +
      '<div class="block-head"><h2 id="heroTitulo">Principais notícias</h2>' +
        '<button class="link-btn" data-go="noticias">Ver todas</button></div>' +
      '<div class="hero" id="hero" role="region" aria-roledescription="carrossel" aria-labelledby="heroTitulo">' +
        '<div class="hero-track" id="heroTrack" aria-live="off"></div>' +
        '<div class="hero-dots" id="heroDots"></div>' +
      '</div>' +
    '</section>' +
    '<section class="block" id="resumoBlock">' +
      '<div class="duo">' +
        '<button class="tile tile-red" data-rolar="jogosBlock">' +
          '<span class="tile-ic"><svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="12" rx="9" ry="5.5" transform="rotate(-35 12 12)"/><path d="m9.5 14.5 5-5M10.5 11l2.5 2.5M12 9.5l2.5 2.5"/></svg></span>' +
          '<span class="tile-num" id="tilePartidas">—</span>' +
          '<span class="tile-label">Partidas na semana</span>' +
        '</button>' +
        '<button class="tile tile-blue" data-go="jogadores">' +
          '<span class="tile-ic"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/></svg></span>' +
          '<span class="tile-num" id="tileAvaliados">—</span>' +
          '<span class="tile-label">Jogadores avaliados</span>' +
        '</button>' +
      '</div>' +
    '</section>' +
    '<section class="block" id="jogosBlock">' +
      '<div class="block-head"><h2>Jogos da semana</h2><span class="muted" id="jogosConta"></span></div>' +
      '<div id="filtroTime"></div>' +
      '<div class="list" id="jogosLista"></div>' +
    '</section>';

  const pedido = { season: S.season, week: S.week };
  const atual = ultimo('inicio');
  const vale = () => atual() && pedido.season === S.season && pedido.week === S.week;

  api.news(pedido.season, pedido.week)
    .then((ns) => { if (vale()) carrossel.montar(ns.slice(0, NO_CARROSSEL)); })
    .catch((e) => { if (vale()) { console.warn('notícias indisponíveis:', e.message); carrossel.montar([]); } });

  api.summary(pedido.season)
    .then((r) => { if (vale()) $('tileAvaliados').textContent = Number(r.ratedPlayers).toLocaleString('pt-BR'); })
    .catch((e) => console.warn('resumo indisponível:', e.message));

  // Erro na semana: a mensagem fica na lista e os filtros continuam utilizáveis (3.4).
  into('jogosLista', async () => {
    jogos = await api.games(pedido.season, pedido.week);
    if (!vale()) return '';
    $('tilePartidas').textContent = jogos.length;
    $('jogosConta').textContent = jogos.length + ' jogos · ' + rotuloSemana(semanaMeta());
    return listaHtml();
  }, 'Carregando as partidas…', vale).then((ok) => {
    if (!ok || !vale()) { if (vale()) jogos = []; return; }
    renderFiltroTime();
    aoVivo.avaliar();
  });
}

/** Sai do Início: o carrossel e o placar ao vivo param. */
export function sair() {
  carrossel.parar();
  aoVivo.parar();
}

/** Mostra só os jogos de um time (a busca usa; o chip "TIME ×" remove). */
export function filtrarPorTime(abbr) {
  S.filtroTime = abbr || null;
  if (S.tela === 'inicio') { repintarJogos(); renderFiltroTime(); }
  else ir('inicio');
}

// Eventos próprios do Início, ligados uma vez no container da tela.
function ligar(el) {
  if (el.dataset.ligado) return;
  el.dataset.ligado = '1';
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.slide) { carrossel.ir(Number(b.dataset.slide), true); return; }
    if (b.dataset.rolar) { $(b.dataset.rolar).scrollIntoView({ behavior: reduzirMovimento() ? 'auto' : 'smooth', block: 'start' }); return; }
    if ('limparTime' in b.dataset) filtrarPorTime(null);
  });
}

/* ----------------------------- carrossel ----------------------------- */
// Avança sozinho a cada 5 s (4.5); pausa com o mouse em cima, durante o toque
// ou com o foco dentro; parado com movimento reduzido (4.6) ou com o avanço
// desligado nas Configurações. Semana sem notícias: o bloco some (4.7).
const carrossel = {
  timer: null, n: 0, i: 0, alvo: null, pausado: false,
  montar(ns) {
    this.parar();
    this.n = ns.length;
    this.i = 0;
    this.alvo = null;
    this.pausado = false;
    const bloco = $('heroBlock');
    if (!bloco) return;
    bloco.hidden = !ns.length;
    if (!ns.length) return;
    $('heroTrack').innerHTML = ns.map(slideHtml).join('');
    $('heroDots').innerHTML = ns.length < 2 ? '' : ns.map((n, k) =>
      '<button data-slide="' + k + '" aria-label="Notícia ' + (k + 1) + ' de ' + ns.length + '"' +
      (k === 0 ? ' aria-current="true"' : '') + '></button>').join('');
    const hero = $('hero');
    const track = $('heroTrack');
    track.addEventListener('scroll', () => this.sincronizar(), { passive: true });
    const pausa = () => { this.pausado = true; };
    const volta = () => { this.pausado = false; };
    hero.addEventListener('mouseenter', pausa);
    hero.addEventListener('mouseleave', volta);
    hero.addEventListener('touchstart', () => { this.alvo = null; pausa(); }, { passive: true });
    track.addEventListener('wheel', () => { this.alvo = null; }, { passive: true });
    hero.addEventListener('touchend', volta);
    hero.addEventListener('touchcancel', volta);
    hero.addEventListener('focusin', pausa);
    hero.addEventListener('focusout', (e) => { if (!hero.contains(e.relatedTarget)) volta(); });
    this.agendar();
  },
  ativo() {
    return this.n > 1 && lerConfig().avancoNoticias && !reduzirMovimento();
  },
  agendar() {
    this.parar();
    if (!this.ativo()) return;
    this.timer = setInterval(() => {
      if (this.pausado || S.tela !== 'inicio' || !$('heroTrack')) return;
      this.ir(this.i + 1, false);
    }, AVANCO_MS);
  },
  parar() { clearInterval(this.timer); this.timer = null; },
  ir(k, peloUsuario) {
    const track = $('heroTrack');
    if (!track || !this.n) return;
    this.i = (k + this.n) % this.n;
    this.alvo = this.i;
    this.pintarPontos();
    track.scrollTo({ left: track.clientWidth * this.i, behavior: reduzirMovimento() ? 'auto' : 'smooth' });
    if (peloUsuario) this.agendar();          // o toque recomeça a contagem de 5 s
  },
  sincronizar() {
    const track = $('heroTrack');
    if (!track || !track.clientWidth) return;
    const k = Math.round(track.scrollLeft / track.clientWidth);
    // só aceita a posição de repouso (no meio da rolagem o índice ainda é o anterior);
    // rolagem pedida pelo carrossel: espera chegar ao destino
    if (Math.abs(track.scrollLeft - k * track.clientWidth) > 2) return;
    if (this.alvo !== null) { if (k === this.alvo) this.alvo = null; return; }
    if (k === this.i) return;
    this.i = k;
    this.pintarPontos();
  },
  pintarPontos() {
    document.querySelectorAll('#heroDots button').forEach((b, k) => {
      if (k === this.i) b.setAttribute('aria-current', 'true');
      else b.removeAttribute('aria-current');
    });
  },
};
aoMudar(() => carrossel.agendar());
aoMudarMovimento(() => carrossel.agendar());

// O jogo da notícia fica no rodapé, com o tipo (7.2); nada de rótulo acima do título.
function slideHtml(n) {
  const [a, b] = n.times || [];
  const tom = ['red', 'blue', 'dark'].includes(n.tom) ? n.tom : 'dark';
  return '<button class="slide ' + tom + '" data-game="' + esc(n.gameId) + '" data-noticia="' + esc(n.id) + '">' +
    '<span class="slide-big" aria-hidden="true">' + esc(n.destaque) + '</span>' +
    '<span class="slide-title">' + esc(n.titulo) + '</span>' +
    '<span class="slide-text">' + esc(n.texto) + '</span>' +
    '<span class="slide-foot">' +
      (a ? badge(time(a), 'sm') : '') + (a && b ? '<span class="slide-x" aria-hidden="true">×</span>' : '') +
      (b ? badge(time(b), 'sm') : '') +
      '<span class="slide-tipo">' + esc(n.tag) + '</span>' +
    '</span>' +
  '</button>';
}

/* ------------------------------ os jogos ----------------------------- */
function visiveis() {
  return S.filtroTime ? jogos.filter((g) => g.home.abbr === S.filtroTime || g.away.abbr === S.filtroTime) : jogos;
}

function listaHtml() {
  if (!jogos.length) return none('Nenhum jogo nesta semana.');
  const vs = visiveis();
  if (!vs.length) return none(time(S.filtroTime).nick ? time(S.filtroTime).nick + ' não joga nesta semana.' : 'Nenhum jogo deste time nesta semana.');
  return vs.map(gameCard).join('');
}

function repintarJogos() {
  const lista = $('jogosLista');
  if (lista && jogos.length) lista.innerHTML = listaHtml();
}

function renderFiltroTime() {
  const box = $('filtroTime');
  if (!box) return;
  box.innerHTML = S.filtroTime
    ? '<button class="chip chip-filtro" data-limpar-time aria-label="Remover o filtro ' + esc(S.filtroTime) + '">' +
      esc(S.filtroTime) + icone('fechar') + '</button>'
    : '';
}

// Estado exibido de um jogo: o placar oficial do nflverse vale sempre que ele
// existir (10.6); sem ele, o placar ao vivo da ESPN, quando houver.
export function estadoDoJogo(g) {
  if (g.status === 'encerrado') return { tipo: 'final', home: g.home.score, away: g.away.score };
  const ao = S.live[g.espnId];
  if (ao && ao.state === 'in') return Object.assign({ tipo: 'aovivo' }, ao);
  if (ao && ao.state === 'post') return Object.assign({ tipo: 'final-espn' }, ao);
  return { tipo: g.status };    // 'agendado' ou 'sem_resultado'
}

function relogioAoVivo(e) {
  if (e.name === 'STATUS_HALFTIME') return 'Intervalo';
  const q = e.period > 4 ? 'PRORROG.' : 'Q' + e.period;
  return q + ' · ' + (e.clock || '');
}

export function gameCard(g) {
  const e = estadoDoJogo(g);
  const temPlacar = e.tipo === 'final' || e.tipo === 'aovivo' || e.tipo === 'final-espn';
  const hw = temPlacar && isNum(e.home) && isNum(e.away) && e.home > e.away;
  const aw = temPlacar && isNum(e.home) && isNum(e.away) && e.away > e.home;
  const falha = S.liveFalha ? '<span class="live-falha">atualização ao vivo indisponível</span>' : '';
  let centro, status;
  if (temPlacar) {
    centro = '<span class="score">' +
      '<span class="' + (aw || e.tipo === 'aovivo' ? '' : 'lose') + '">' + nm(e.away) + '</span>' +
      '<span class="sep">–</span>' +
      '<span class="' + (hw || e.tipo === 'aovivo' ? '' : 'lose') + '">' + nm(e.home) + '</span></span>';
    if (e.tipo === 'aovivo') {
      status = '<span class="badge-live">AO VIVO</span> ' + esc(relogioAoVivo(e)) + falha;
    } else {
      status = 'FINAL' + (g.overtime ? ' <span class="badge-ot">PRORROG.</span>' : '') + ' · ' + esc(inicioLocal(g));
    }
  } else if (e.tipo === 'agendado') {
    centro = '<span class="pending">A JOGAR</span>';
    status = esc(inicioLocal(g));
  } else {
    centro = '<span class="sem-resultado">resultado ainda não disponível</span>';
    status = esc(inicioLocal(g)) + falha;
  }
  const lado = (t, venceu) => '<span class="team' + (venceu ? ' win' : '') + '">' + badge(t) +
    '<span class="name">' + esc(t.nick || t.abbr) + '</span></span>';
  return '<button class="match' + (g.gameId === S.gameId ? ' selected' : '') + '" data-game="' + g.gameId + '" ' +
    'data-estado="' + e.tipo + '" aria-label="' + esc(g.away.abbr + ' contra ' + g.home.abbr) + '">' +
    lado(g.away, aw) +
    '<span class="center">' + centro + '<span class="when">' + status + '</span></span>' +
    lado(g.home, hw) +
    '</button>';
}

/* --------------------------- placar ao vivo --------------------------- */
// ESPN direto do navegador (ela recusa chamadas de servidor). A cada 30 s,
// só enquanto a semana exibida tiver jogo já começado e ainda sem o placar
// final. O nflverse, quando traz o jogo, prevalece.
const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl';
const AO_VIVO_MS = 30000;
const SEMANA_ESPN = { WC: 1, DIV: 2, CON: 3, SB: 5 };
export const aoVivo = {
  timer: null,
  parar() { clearTimeout(this.timer); this.timer = null; },
  // Jogos que pedem consulta: começaram, não têm o placar oficial e a ESPN ainda não encerrou.
  pendentes() {
    const agora = Date.now();
    return jogos.filter((g) => g.status !== 'encerrado' && g.espnId && g.kickoffUtc &&
      Date.parse(g.kickoffUtc) <= agora && !(S.live[g.espnId] && S.live[g.espnId].state === 'post'));
  },
  avaliar() {
    this.parar();
    if (this.pendentes().length) { this.consultar(); return; }
    // Nenhum em andamento: dorme até o próximo início da semana (se houver).
    const agora = Date.now();
    const futuros = jogos.filter((g) => g.status === 'agendado' && g.kickoffUtc)
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
    const mudou = () => pedido.season !== S.season || pedido.week !== S.week || S.tela !== 'inicio';
    try {
      const r = await fetch(ESPN + '/scoreboard?dates=' + S.season + '&seasontype=' + tipo + '&week=' + semana);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (mudou()) return;
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
      if (mudou()) return;
      console.warn('placar ao vivo indisponível:', e.message);
      S.liveFalha = true;       // mantém o último placar conhecido
    }
    repintarJogos();
    if (this.pendentes().length) this.timer = setTimeout(() => this.consultar(), AO_VIVO_MS);
    else this.avaliar();
  },
};
