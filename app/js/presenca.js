/* ==========================================================================
   Sinal de presença das abas (spec sem-terminal). O NFL-Games.exe roda sem
   terminal e se encerra sozinho quando nenhuma aba do app dá sinal: cada aba
   avisa o servidor a cada 30 s e, ao fechar, avisa a saída (fetch com keepalive,
   que manda o cabeçalho do app; o sendBeacon não manda). No site público não
   há servidor, e nada disto roda (o main.js só chama com !ESTATICO).
   ========================================================================== */

const CABECALHOS = { 'X-NFL-App': '1', 'Content-Type': 'application/json' };

function novoId() {
  return (self.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now();
}

/** Começa a dar sinal; devolve parar(), que cancela o intervalo (sem avisar a saída). */
export function iniciarPresenca({ buscar = (u, o) => fetch(u, o), intervaloMs = 30000 } = {}) {
  const aba = novoId();
  const enviar = (saiu, keepalive) => {
    // Falha (servidor subindo ou já parado) é ignorada: a contagem do servidor é folgada.
    try {
      buscar('/api/presenca', { method: 'POST', headers: CABECALHOS, keepalive,
        body: JSON.stringify({ aba, saiu }) }).catch(() => {});
    } catch (e) { /* sem fetch: nada a fazer */ }
  };
  enviar(false, false);
  const timer = setInterval(() => enviar(false, false), intervaloMs);
  const sair = () => enviar(true, true);
  window.addEventListener('pagehide', sair);
  return function parar() {
    clearInterval(timer);
    window.removeEventListener('pagehide', sair);
  };
}
