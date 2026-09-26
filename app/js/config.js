/* ==========================================================================
   Configurações do aparelho (spec novo-visual, Requisito 11). Ficam no
   localStorage; se ele falhar ou vier adulterado, valem os padrões (11.5).
   Só valores conhecidos são aceitos: qualquer outro vira o padrão.
   ========================================================================== */

const CHAVE = 'nfl.config.v2';
export const PADRAO = Object.freeze({ avancoNoticias: true, velocidadeReplay: 1 });
const VELOCIDADES = [0.5, 1, 2];

function validar(c) {
  const o = c && typeof c === 'object' ? c : {};
  return {
    avancoNoticias: typeof o.avancoNoticias === 'boolean' ? o.avancoNoticias : PADRAO.avancoNoticias,
    velocidadeReplay: VELOCIDADES.includes(o.velocidadeReplay) ? o.velocidadeReplay : PADRAO.velocidadeReplay,
  };
}

let atual = null;
const ouvintes = new Set();

export function ler() {
  if (atual) return { ...atual };
  try {
    atual = validar(JSON.parse(localStorage.getItem(CHAVE) || '{}'));
  } catch (e) {
    atual = { ...PADRAO };        // localStorage indisponível ou JSON quebrado
  }
  return { ...atual };
}

/** Aplica na hora (11.3), mesmo que não consiga gravar no aparelho. */
export function gravar(parcial) {
  atual = validar({ ...ler(), ...parcial });
  try { localStorage.setItem(CHAVE, JSON.stringify(atual)); } catch (e) { /* modo privado etc. */ }
  ouvintes.forEach((fn) => { try { fn({ ...atual }); } catch (e) { console.error(e); } });
  return { ...atual };
}

export function aoMudar(fn) {
  ouvintes.add(fn);
  return () => ouvintes.delete(fn);
}

const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
export const reduzirMovimento = () => !!(mq && mq.matches);
export function aoMudarMovimento(fn) {
  if (mq && mq.addEventListener) mq.addEventListener('change', () => fn(reduzirMovimento()));
}
