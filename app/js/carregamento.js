/* ==========================================================================
   Tela de carregamento: o servidor abre a porta antes de carregar os dados, e
   o navegador ja abre. Enquanto a API responde 503 ("carregando"), esta tela
   cobre o app e acompanha /api/estado a cada instante: a fase, a ultima linha
   de progresso (a mesma do terminal) e, na primeira carga, o aviso de que
   leva alguns minutos. Pronto: a tela some e o app abre, sem recarregar.
   ========================================================================== */
import { $ } from './ui.js';

const INTERVALO_MS = 700;
const FALHAS_ATE_DESISTIR = 3;          // a conexao caiu varias vezes seguidas: o servidor foi encerrado
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));

function mostrar(titulo, fase, nota, erro) {
  const tela = $('carregando');
  tela.hidden = false;
  tela.classList.toggle('erro', !!erro);
  $('carregandoTitulo').textContent = titulo;
  $('carregandoFase').textContent = fase;                 // texto do servidor: sempre como texto
  $('carregandoNota').hidden = !nota;
  if (nota) $('carregandoNota').textContent = nota;
}

/**
 * Espera os dados ficarem prontos, mostrando o progresso. Devolve true quando
 * o app pode seguir; false se a carga falhou ou o servidor foi encerrado (a
 * tela fica com a explicacao).
 */
export async function esperarDados() {
  mostrar('Preparando os dados', 'Iniciando…', '', false);
  let falhas = 0;
  for (;;) {
    let estado;
    try {
      const r = await fetch('/api/estado', { cache: 'no-store', headers: { Accept: 'application/json' } });
      estado = await r.json();
      falhas = 0;
    } catch (e) {
      if (++falhas >= FALHAS_ATE_DESISTIR) {
        mostrar('O app foi encerrado', 'Veja a mensagem na janela do terminal e abra o app de novo.', '', true);
        return false;
      }
      await dormir(INTERVALO_MS);
      continue;
    }
    if (estado.pronto) {
      $('carregando').hidden = true;
      return true;
    }
    if (estado.fase === 'erro') {
      mostrar('Não foi possível carregar os dados', estado.mensagem || '',
        'Veja os detalhes na janela do terminal.', true);
      return false;
    }
    mostrar('Preparando os dados', estado.mensagem || 'Carregando…',
      estado.primeiraCarga
        ? 'Na primeira vez, o app baixa e monta os dados do nflverse (~330 MB). Leva alguns minutos; esta tela avança sozinha.'
        : '',
      false);
    await dormir(INTERVALO_MS);
  }
}
