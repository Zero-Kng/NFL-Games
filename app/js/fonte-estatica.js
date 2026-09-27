/* ==========================================================================
   Fonte de dados do site publicado (spec site-publico): a mesma API do servidor
   (as 11 funções de api.js), lida dos arquivos que o tools/exportar.py grava em
   api/{versao}/. Só o que não dá para gravar pronto é calculado aqui, espelhando
   o server/data_layer.py: a semana atual e o status pelo relógio (Regras A e B),
   o filtro de jogadores (Regra C) e a comparação (Regra D).
   Todos os caminhos são relativos: o site roda em /NFL-Games/.
   ========================================================================== */

const MSG_GZ = 'Este navegador não consegue abrir os dados do jogo. Atualize o navegador (no iPhone, iOS 16.4 ou mais novo).';

function erro(status, msg) {
  const e = new Error(msg);
  e.status = status;
  return e;
}

/* --------------------------- Regra A: semana atual --------------------------- */
const DIA_NY = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });

/** A última semana que já começou (alguma data <= hoje em Nova York); antes do 1º jogo, a primeira. */
export function semanaAtual(semanas, agoraMs) {
  if (!semanas || !semanas.length) return null;
  const hoje = DIA_NY.format(agoraMs);
  let atual = null;
  for (const w of semanas) if (w.dates.some((d) => d <= hoje)) atual = w.week;
  return atual === null ? semanas[0].week : atual;
}

/* ------------------------------ Regra B: status ------------------------------ */
/** Com placar, encerrado; sem placar, agendado até o início e sem_resultado depois. */
export function statusDoJogo(card, agoraMs) {
  if (card.home && card.away && card.home.score != null && card.away.score != null) return 'encerrado';
  const inicio = card.kickoffUtc ? Date.parse(card.kickoffUtc) : null;
  return inicio === null || inicio > agoraMs ? 'agendado' : 'sem_resultado';
}

/* ---------------------------- Regra C: jogadores ----------------------------- */
const vazio = (v) => v === undefined || v === null || v === '';

/** Filtra a lista já ordenada (rating, volume) como o players_list do servidor. */
export function filtrarJogadores(lista, f) {
  f = f || {};
  let p = lista;
  if (vazio(f.rated) || !['0', 'false'].includes(String(f.rated))) p = p.filter((c) => c.rated);
  if (!vazio(f.q)) {
    const alvo = String(f.q).toUpperCase();          // pandas str.contains(case=False): compara em upper()
    p = p.filter((c) => c.name != null && String(c.name).toUpperCase().includes(alvo));
  }
  if (!vazio(f.position)) {
    const quer = new Set(String(f.position).split(',').map((s) => s.trim().toUpperCase()).filter(Boolean));
    p = p.filter((c) => quer.has(String(c.position).toUpperCase()));
  }
  if (!vazio(f.role)) p = p.filter((c) => c.role === String(f.role).toUpperCase());
  if (!vazio(f.team)) p = p.filter((c) => c.team === String(f.team).toUpperCase());
  const limite = Math.min(vazio(f.limit) ? 40 : Number(f.limit), 300);
  return p.slice(0, limite);
}

/* ---------------------------- Regra D: comparação ---------------------------- */
/** Só compara estatísticas de jogadores do mesmo grupo (como NFLData.compare). */
export function juntarComparacao(pa, pb, ano) {
  const ra = pa.roles[0], rb = pb.roles[0];
  const mesmo = ra.role === rb.role;
  let rows = [];
  if (mesmo) {
    const por = new Map(rb.stats.map((s) => [s.label, s]));
    rows = ra.stats.filter((s) => por.has(s.label))
      .map((s) => ({ label: s.label, unit: s.unit, left: s.value, right: por.get(s.label).value }));
  }
  return { sameRole: mesmo, season: ano, role: ra.role, roleLabel: ra.roleLabel, left: pa, right: pb, rows };
}

/* ------------------------------- gzip ------------------------------- */
/** Lê um .json.gz: descompacta só se ainda vier comprimido (1f 8b); com Content-Encoding, já vem pronto. */
export async function lerGz(res) {
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    if (typeof DecompressionStream === 'undefined') throw erro(0, MSG_GZ);
    const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(fluxo).text());
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

/* ------------------------------- a fonte ------------------------------- */
export function fonteEstatica({ get, buscar = (u, o) => fetch(u, o), agora = () => Date.now() }) {
  let versaoP = null;
  const versao = () => versaoP || (versaoP = buscar('api/versao.json', { cache: 'no-store' })
    .then((r) => { if (!r.ok) throw erro(r.status, 'HTTP ' + r.status); return r.json(); })
    .then((j) => j.versao)
    .catch((e) => { versaoP = null; throw e; }));

  const ler = async (rel, leitor) => get('api/' + (await versao()) + '/' + rel, leitor);

  /** 404 do arquivo vira a resposta do servidor para aquela rota: um erro com a mensagem dele, ou um valor. */
  async function se404(promessa, resposta) {
    try { return await promessa; } catch (e) {
      if (e.status !== 404) throw e;
      if (resposta instanceof Error) throw resposta;
      return resposta;
    }
  }

  const meta = () => ler('meta.json');
  async function temporada(season) {
    const m = await meta();
    if (vazio(season)) return m.season;
    const ano = Number(season);
    const anos = m.seasons.map((t) => t.season);
    if (!anos.includes(ano)) throw erro(404, 'temporada ' + ano + ' indisponivel (ha ' + Math.min(...anos) + ' a ' + Math.max(...anos) + ')');
    return ano;
  }

  const bundle = (g) => ler('jogos/' + g + '.json.gz', lerGz);
  const pranchetas = (g) => ler('jogos/' + g + '.pranchetas.json.gz', lerGz);
  const comStatus = (card) => Object.assign({}, card, { status: statusDoJogo(card, agora()) });
  const perfil = async (id, ano) => ler(ano + '/jogadores/' + encodeURIComponent(id) + '.json');

  return {
    async meta() {
      const m = await meta();
      const agoraMs = agora();
      const seasons = m.seasons.map((t) => Object.assign({}, t, { currentWeek: semanaAtual(t.weeks, agoraMs) }));
      const atual = seasons.find((t) => t.season === m.season);
      return Object.assign({}, m, { seasons, currentWeek: atual ? atual.currentWeek : null });
    },
    async games(season, week) {
      const ano = await temporada(season);
      const lista = await se404(ler(ano + '/semanas/' + week + '.json'), []);
      return lista.map(comStatus);
    },
    async game(g) {
      const b = await se404(bundle(g), erro(404, 'jogo ' + g + ' nao encontrado'));
      return comStatus(b.game);
    },
    async plays(g) {
      const b = await se404(bundle(g), null);
      return b ? b.plays : [];
    },
    async tracking(g, p) {
      const msg = erro(404, 'formacao indisponivel para esta jogada');
      const t = await se404(pranchetas(g), msg);
      if (!t[String(p)]) throw msg;
      return t[String(p)];
    },
    async broadcast(g) {
      const msg = erro(404, 'jogo nao encontrado ou ainda sem jogadas');
      const b = await se404(bundle(g), msg);
      if (!b.broadcast) throw msg;
      return b.broadcast;
    },
    async players(season, filtros) {
      const ano = await temporada(season);
      return filtrarJogadores(await ler(ano + '/jogadores.json'), filtros);
    },
    async player(id, season) {
      const msg = erro(404, 'jogador sem dados na temporada');
      if (!vazio(season)) return se404(perfil(id, await temporada(season)), msg);
      // sem temporada, o servidor usa a mais recente em que o jogador aparece
      const m = await meta();
      for (const t of m.seasons.slice().sort((a, b) => b.season - a.season)) {
        const p = await se404(perfil(id, t.season), null);
        if (p) return p;
      }
      throw msg;
    },
    async compare(a, b, season) {
      if (vazio(a) || vazio(b)) throw erro(400, "informe os parametros 'a' e 'b' com os ids dos jogadores");
      const ano = await temporada(season);
      const msg = erro(404, 'um dos jogadores nao tem dados na temporada');
      const [pa, pb] = await Promise.all([se404(perfil(a, ano), null), se404(perfil(b, ano), null)]);
      if (!pa || !pb) throw msg;
      return juntarComparacao(pa, pb, ano);
    },
    async news(season, week) {
      const ano = await temporada(season);
      return vazio(week) ? ler(ano + '/noticias.json') : se404(ler(ano + '/noticias/' + week + '.json'), []);
    },
    async summary(season) {
      return ler((await temporada(season)) + '/resumo.json');
    },
  };
}
