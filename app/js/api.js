/* ==========================================================================
   Acesso à API local (server/serve.py). Extraído do app.js (spec novo-visual,
   tarefa 2.3): cache de respostas com LRU e deduplicação de pedidos em voo, e
   o "só o último vence" para fluxos que podem ser disparados de novo.
   ========================================================================== */

// Cache da sessão (deduplica pedidos iguais, inclusive em voo). LRU com teto,
// para não crescer sem fim numa sessão longa de navegação.
const cache = new Map();
const CACHE_MAX = 150;

export function get(path) {
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
        try { const b = await res.json(); if (b.error) msg = b.error; } catch (e) { /* corpo sem JSON */ }
        throw new Error(msg);
      }
      return res.json();
    });
  cache.set(path, p);
  p.catch(() => { if (cache.get(path) === p) cache.delete(path); });
  return p;
}

export function qs(o) {
  const sp = new URLSearchParams();
  Object.keys(o || {}).forEach((k) => {
    if (o[k] !== undefined && o[k] !== null && o[k] !== '') sp.set(k, o[k]);
  });
  const s = sp.toString();
  return s ? '?' + s : '';
}

// Sem cache da sessão: o status dos jogos (a jogar, sem resultado) muda com o relógio.
function semCache(path) {
  cache.delete(path);
  return get(path);
}

export const api = {
  meta: () => get('/api/meta'),
  games: (season, week) => semCache('/api/games' + qs({ season, week })),
  game: (g) => get('/api/games/' + g),
  plays: (g) => get('/api/games/' + g + '/plays'),
  tracking: (g, p) => get('/api/games/' + g + '/plays/' + p + '/tracking'),
  broadcast: (g) => get('/api/games/' + g + '/broadcast'),
  players: (season, p) => get('/api/players' + qs(Object.assign({ season }, p || {}))),
  player: (id, season) => get('/api/players/' + encodeURIComponent(id) + qs({ season })),
  compare: (a, b, season) => get('/api/compare' + qs({ season, a, b })),
  news: (season, week) => get('/api/news' + qs({ season, week })),
  summary: (season) => get('/api/summary' + qs({ season })),
};

/**
 * "Só o último vence": cada chamada de ultimo(chave) começa um pedido novo e
 * devolve uma função que diz se ele ainda é o mais recente daquela chave.
 * Resposta que chega atrasada (o usuário já pediu outra coisa) é descartada.
 */
const contadores = new Map();
export function ultimo(chave) {
  const n = (contadores.get(chave) || 0) + 1;
  contadores.set(chave, n);
  return () => contadores.get(chave) === n;
}
