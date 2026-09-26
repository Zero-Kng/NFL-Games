/* ==========================================================================
   Formatadores, HTML seguro e estados de tela, compartilhados pelas telas.
   Extraídos do app.js (spec novo-visual, tarefa 2.3). Todo texto vindo dos
   dados passa por esc() antes de entrar no HTML (S.1).
   ========================================================================== */

export function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
export const isNum = (v) => v !== null && v !== undefined && v !== '' && !isNaN(v);
export const pct = (v, d) => (isNum(v) ? (v * 100).toFixed(d === undefined ? 0 : d) + '%' : '—');
export const nm = (v, d) => (isNum(v) ? Number(v).toFixed(d === undefined ? 0 : d) : '—');
export const secs = (v) => (isNum(v) ? Number(v).toFixed(1) + 's' : '—');
export const signed = (v) => (isNum(v) ? (v > 0 ? '+' + v : '' + v) : '—');
export const $ = (id) => document.getElementById(id);

export function ordDown(d, y) {
  if (!isNum(d)) return '—';
  return (['', '1ª', '2ª', '3ª', '4ª'][d] || d + 'ª') + ' e ' + y;
}

const DIAS = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB'];
const dois = (n) => String(n).padStart(2, '0');

// Datas do calendário vêm como AAAA-MM-DD; o horário do jogo, em UTC (kickoffUtc).
export function brDate(s) {
  if (!s) return '';
  const a = String(s).slice(0, 10).split('-');
  return a[2] + '/' + a[1];
}
export function weekday(s) {
  if (!s) return '';
  return DIAS[new Date(String(s).slice(0, 10) + 'T12:00:00').getDay()];
}
export function inicioLocal(g) {
  if (!g.kickoffUtc) return weekday(g.date) + ' ' + brDate(g.date);
  const d = new Date(g.kickoffUtc);
  return DIAS[d.getDay()] + ' ' + dois(d.getDate()) + '/' + dois(d.getMonth() + 1) +
    ' · ' + dois(d.getHours()) + 'h' + dois(d.getMinutes());
}
export function dataHora(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function badge(t, size) {
  t = t || {};
  return '<span class="badge' + (size ? ' ' + size : '') + '" style="background:' + esc(t.primary || '#013369') +
    '" title="' + esc(t.name || t.abbr || '') + '">' + esc(t.abbr || '?') + '</span>';
}
export function rateCls(r) {
  if (!isNum(r)) return 'na';
  return r >= 88 ? 'elite' : r >= 75 ? 'good' : r >= 60 ? 'avg' : 'low';
}
export function rateChip(r) {
  return '<span class="rate ' + rateCls(r) + '">' + (isNum(r) ? r : 'n/d') + '</span>';
}
export function delta(v, lg, lowerBetter, asPct) {
  if (!isNum(v) || !isNum(lg)) return '';
  const d = v - lg;
  const good = lowerBetter ? d < 0 : d > 0;
  const flat = Math.abs(d) < (asPct ? 0.005 : 0.05);
  const cls = flat ? 'flat' : good ? 'up' : 'down';
  const txt = asPct ? (Math.abs(d) * 100).toFixed(0) + 'pp' : Math.abs(d).toFixed(1);
  return '<span class="delta ' + cls + '">' + (d > 0 ? '+' : d < 0 ? '−' : '') + txt + ' vs liga</span>';
}

/* ------------------------------- ícones ------------------------------- */
// Um só traço (1,8) para todo o app; nada de emoji no lugar de ícone.
const ICONES = {
  carregando: '<path d="M12 4a8 8 0 1 1-8 8"/>',
  vazio: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 13h4l1.5 2h5L16 13h4"/>',
  erro: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.2v.2"/>',
  obra: '<path d="M4 20h16M6 20l3-11h6l3 11M9.5 13h5"/><path d="M12 9V4"/>',
};
export function icone(nome) {
  return '<svg viewBox="0 0 24 24" aria-hidden="true">' + (ICONES[nome] || '') + '</svg>';
}

/* ------------------------------- estados ------------------------------ */
export const spin = (m) => '<div class="state loading" role="status">' + icone('carregando') + esc(m || 'Carregando…') + '</div>';
export const oops = (m) => '<div class="state error" role="alert">' + icone('erro') + esc(m) + '</div>';
export const none = (m) => '<div class="state">' + icone('vazio') + esc(m) + '</div>';

/**
 * Renderiza num container com os estados de carregando e erro. `atual`, se
 * informado, diz se este pedido ainda é o mais recente: resposta atrasada é
 * descartada. Devolve true se o resultado foi desenhado.
 */
export async function into(el, fn, msg, atual) {
  if (typeof el === 'string') el = $(el);
  if (!el) return false;
  el.innerHTML = spin(msg);
  let html;
  try { html = (await fn()) || ''; }
  catch (e) {
    if (atual && !atual()) return false;
    console.error(e);
    el.innerHTML = oops('Falha ao carregar: ' + e.message);
    return false;
  }
  if (atual && !atual()) return false;
  el.innerHTML = html;
  return true;
}
