/* ==========================================================================
   Tela Notícias (spec novo-visual, tarefa 7): as notícias da semana, geradas
   no servidor a partir dos dados (/api/news), da mais incomum para a menos.
   Tocar numa notícia abre a página Jogo da partida (7.5).
   ========================================================================== */
import { api, ultimo } from '../api.js';
import { $, esc, badge, none, into } from '../ui.js';
import { S, semanaMeta, rotuloSemana } from '../main.js';

const teamOf = (a) => (S.meta && S.meta.teams[a]) || { abbr: a, primary: '#013369', name: a };

export function render(el) {
  el.innerHTML =
    '<section class="block">' +
      '<div class="block-head"><h2>Notícias</h2><span class="muted" id="noticiasConta"></span></div>' +
      '<div class="list" id="noticiasLista"></div>' +
    '</section>';
  const pedido = { season: S.season, week: S.week };
  const atual = ultimo('noticias');
  const vale = () => atual() && pedido.season === S.season && pedido.week === S.week;
  into('noticiasLista', async () => {
    const ns = await api.news(pedido.season, pedido.week);
    if (!vale()) return '';
    $('noticiasConta').textContent = (ns.length ? ns.length + (ns.length === 1 ? ' notícia' : ' notícias') + ' · ' : '') +
      rotuloSemana(semanaMeta());
    // 7.6: semana ainda sem jogos disputados
    if (!ns.length) return none('Sem notícias para esta semana.');
    return ns.map(noticiaHtml).join('');
  }, 'Carregando as notícias…', vale);
}

// O jogo da notícia fica no rodapé, com o tipo (7.2); nada de rótulo acima do título.
export function noticiaHtml(n) {
  const [a, b] = n.times || [];
  const tom = ['red', 'blue', 'dark'].includes(n.tom) ? n.tom : 'dark';
  return '<button class="news-item" data-game="' + esc(n.gameId) + '" data-noticia="' + esc(n.id) + '">' +
    '<span class="news-thumb ' + tom + '" aria-hidden="true">' + esc(n.destaque) + '</span>' +
    '<span class="news-corpo">' +
      '<span class="news-titulo">' + esc(n.titulo) + '</span>' +
      '<span class="news-texto">' + esc(n.texto) + '</span>' +
      '<span class="news-rodape">' +
        (a ? badge(teamOf(a), 'xs') : '') + (a && b ? '<span aria-hidden="true">×</span>' : '') + (b ? badge(teamOf(b), 'xs') : '') +
        '<span class="news-tipo">' + esc(n.tag) + '</span>' +
      '</span>' +
    '</span>' +
  '</button>';
}
