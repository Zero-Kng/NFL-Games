/* ==========================================================================
   Telas do menu lateral (spec novo-visual, tarefa 8): Configurações
   (Requisito 11) e Sobre os dados (o renderSobre da dados-externos, movido).
   ========================================================================== */
import { $, esc, dataHora } from '../ui.js';
import { ler, gravar, aoMudar, reduzirMovimento } from '../config.js';
import { S } from '../main.js';

const VELOCIDADES = [[0.5, '0,5×'], [1, '1×'], [2, '2×']];

/* ---------------------------- Configurações ---------------------------- */
// Os dois controles do Requisito 11.2; cada mudança vale na hora (11.3), pelo
// aoMudar que o carrossel e o Replay escutam, e fica no aparelho (11.4).
export function renderConfig(el) {
  ligarConfig(el);
  el.innerHTML =
    '<section class="block">' +
      '<div class="card config">' +
        '<div class="config-item">' +
          '<span class="config-texto"><span class="config-nome" id="cfgAvancoNome">Avançar as notícias sozinho</span>' +
            '<span class="config-desc" id="cfgAvancoDesc">O carrossel do Início passa para a notícia seguinte a cada 5 segundos.</span></span>' +
          '<button class="switch" id="cfgAvanco" role="switch" aria-labelledby="cfgAvancoNome" aria-describedby="cfgAvancoDesc"></button>' +
        '</div>' +
        '<p class="config-nota" id="cfgMovimento" hidden>O sistema pede menos movimento: o carrossel fica parado enquanto esse pedido valer.</p>' +
        '<div class="config-item coluna">' +
          '<span class="config-texto"><span class="config-nome" id="cfgVelNome">Velocidade do Replay narrado</span>' +
            '<span class="config-desc" id="cfgVelDesc">Quanto tempo cada jogada fica na tela ao reproduzir o Replay.</span></span>' +
          '<div class="segmentado" role="radiogroup" aria-labelledby="cfgVelNome" aria-describedby="cfgVelDesc">' +
            VELOCIDADES.map(([v, l]) => '<button role="radio" data-vel="' + v + '">' + l + '</button>').join('') +
          '</div>' +
        '</div>' +
      '</div>' +
      '<p class="muted config-rodape">As configurações ficam só neste aparelho.</p>' +
    '</section>';
  pintarConfig();
}

function pintarConfig() {
  const b = $('cfgAvanco');
  if (!b) return;
  const c = ler();
  b.setAttribute('aria-checked', String(c.avancoNoticias));
  $('cfgMovimento').hidden = !reduzirMovimento();
  document.querySelectorAll('[data-vel]').forEach((r) => {
    const sel = Number(r.dataset.vel) === c.velocidadeReplay;
    r.setAttribute('aria-checked', String(sel));
    r.tabIndex = sel ? 0 : -1;
  });
}
aoMudar(pintarConfig);

function ligarConfig(el) {
  if (el.dataset.ligado) return;
  el.dataset.ligado = '1';
  el.addEventListener('click', (e) => {
    if (e.target.closest('#cfgAvanco')) { gravar({ avancoNoticias: !ler().avancoNoticias }); return; }
    const v = e.target.closest('[data-vel]');
    if (v) gravar({ velocidadeReplay: Number(v.dataset.vel) });
  });
  // setas no grupo de velocidades (padrão de radiogroup)
  el.addEventListener('keydown', (e) => {
    const r = e.target.closest('[data-vel]');
    if (!r || !['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    const i = VELOCIDADES.findIndex(([v]) => v === Number(r.dataset.vel)) + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1);
    const v = VELOCIDADES[(i + VELOCIDADES.length) % VELOCIDADES.length][0];
    gravar({ velocidadeReplay: v });
    el.querySelector('[data-vel="' + v + '"]').focus();
  });
}

/* ---------------------------- Sobre os dados --------------------------- */
// Fontes com o crédito de cada licença e a última atualização (movido da dados-externos).
export function renderSobre(el) {
  const m = S.meta;
  const anos = m.seasons.map((t) => t.season);
  el.innerHTML =
    '<section class="block" id="sobreDados">' +
      '<div class="card sobre">' +
        '<p>Temporadas ' + Math.min.apply(null, anos) + ' a ' + Math.max.apply(null, anos) +
        ', temporada regular e playoffs, com todas as jogadas.</p>' +
        '<p class="atualizado">Última atualização: ' +
          (m.ultimaAtualizacao ? esc(dataHora(m.ultimaAtualizacao)) : 'sem registro') + '</p>' +
      '</div>' +
      '<div class="sec-head"><h2>Fontes</h2></div>' +
      '<div class="list">' + (m.fontes || []).map((f) =>
        '<div class="card fonte"><h4>' + esc(f.nome) + '</h4>' +
          '<p>' + esc(f.credito) + '.</p>' +
          '<p class="muted">Usado para: ' + esc(f.usadoPara) + '.</p></div>').join('') + '</div>' +
      '<div class="sec-head"><h2>Como ler</h2></div>' +
      '<div class="card sobre"><p>A prancheta mostra posições-modelo da formação (ilustrativas); os ratings são ' +
        'percentis de estatísticas públicas dentro de cada grupo de posição e temporada. As notícias são geradas ' +
        'a partir desses mesmos dados, sem texto inventado.</p></div>' +
    '</section>';
}
