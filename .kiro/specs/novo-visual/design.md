# Design Document

**Feature:** novo-visual
**Workflow:** requirements-first
**Status:** v0.4 em revisão (retomada sobre os dados do nflverse), aguardando aprovação do José
**Data:** 2026-09-26 (v0.3 aprovada em 2026-09-25)

> **v0.4:** a base agora é a da spec `dados-externos` (2021 em diante, placar oficial e ao vivo, matéria da ESPN, prancheta ilustrativa, ratings por grupo). Mudou: as notícias (tipos novos, limiares medidos de novo), a prancheta (sem interpolação: o antigo Requisito 10 saiu), as Configurações (2 controles), a matéria da ESPN (topo da página Jogo) e "Sobre os dados" (fontes e créditos de `/api/meta`).

---

## Overview

O front-end é reescrito sobre a identidade do `rascunho/` e dividido em **módulos ES nativos**, sem etapa de build. Um módulo para a casca (cabeçalho, menu lateral, busca, barra inferior e navegação) e um por tela: Início, Jogo, Jogadores, Notícias, Configurações e Sobre.

A lógica que já funciona é **movida, não reescrita**:
- a prancheta e o replay do Comentarista vão para as abas da página Jogo;
- o Olheiro vira a tela Jogadores;
- o cache `get()` e os contadores "só o último vence" viram um módulo de API compartilhado.

Há duas peças novas:
1. **Notícias**, geradas no servidor por uma rota nova e calculadas a partir das jogadas e estatísticas que o `data_layer` já tem.
2. **Configurações**, salvas no navegador.

A prancheta, o placar ao vivo, a matéria da ESPN e o seletor de temporada vêm da spec `dados-externos` e são **movidos** para as telas novas.

As rotas atuais da API **não mudam** (o golden continua valendo). Informação nova entra só por rotas novas.

---

## Architecture

### Visão de alto nível

```
index.html ──► js/main.js ── casca: cabeçalho · menu lateral · busca · barra inferior · roteador
                  │
                  ├── js/api.js ........ get() com cache LRU + dedupe, seq "só o último vence"
                  ├── js/config.js ..... Configurações (localStorage, com padrões)
                  │
                  ├── js/telas/inicio.js      carrossel · 2 cartões · jogos da semana (com o placar ao vivo)
                  ├── js/telas/jogo.js        matéria ESPN + 5 abas ──► js/prancheta.js (Field, 1 quadro)
                  ├── js/telas/jogadores.js   a observar · busca · perfil · comparação
                  ├── js/telas/noticias.js    lista da semana
                  └── js/telas/extras.js      Configurações · Sobre os dados
                                   │
serve.py ── rotas atuais (inalteradas) + GET /api/news  + GET /api/summary
                                   │
data_layer.py ── NFLData.news(week) · NFLData.summary()   (novos; reusam o que já existe)
```

São 7 módulos de front-end mais 2 rotas. O motivo de cada um está em "Components" e na Decisão 1.

### Fluxo: tocar numa notícia

1. O usuário toca num slide do carrossel ou num item de Notícias. Os dois vêm de `GET /api/news?week=N`, já no cache do `get()`.
2. `main.js` recebe `data-game` e chama `selecionarJogo(id)`, que atualiza o estado compartilhado.
3. O roteador ativa a tela Jogo na aba Prancheta.
4. `jogo.js` pede `/api/games/{id}` e `/api/games/{id}/plays`, que saem do cache de respostas do servidor e já estão aquecidos.
5. A prancheta desenha a primeira jogada com formação e pré-carrega as vizinhas, como já faz hoje.

### O que já existe e será reusado

- **`app/js/app.js`, reaproveitado por partes:** `get()`/`qs()`/`seq`/`into()` e os formatadores (`esc`, `pct`, `nm`, `secs`, `ordDown`, `brDate`, `inicioLocal`, `dataHora`) vão para `api.js`/`ui.js`. `Field` (viewport, marcações, pontos) vai para `prancheta.js`. `coachLineup`, `loadFieldPlay`, `prefetchVizinhas`, `playRow`, `coachStats`, `coachBook`, `renderBroadcast`/`paintBc`, `scoutList`, `scoutDetail`, `radarSVG`, `fillComparePicker` e `showCompare` vão para as telas novas; **`aoVivo`, `estadoDoJogo`, `gameCard`, `renderMateria`/`linkEspn`/`conferirPlacar` e `renderSobre`** (da `dados-externos`) também. **A lógica fica; muda o HTML gerado e as classes.**
- **`NFLData`** já tem o que as notícias precisam: o placar oficial de cada jogada (`total_home_score`/`total_away_score`), o placar final e a prorrogação do calendário, as jogadas com `yards_gained`, e o `jogador_jogo` com as estatísticas por jogo. **`watch_list()`** alimenta os "Jogadores a observar".
- **`CacheDeRespostas`** e o aquecimento: as rotas novas entram no cache sem código extra, e `/api/news` de cada semana entra na lista de aquecimento.
- **`rascunho/style.css`:** os tokens (`--bg`, `--surface`, `--red`...), o cabeçalho, os chips, o carrossel, os cartões, a barra inferior e o menu lateral viram a base do CSS novo.

---

## Components and Interfaces

### 1. Rotas novas no servidor

**Responsabilidade:** entregar notícias e o resumo sem mudar nenhuma rota existente.
**Atende aos requisitos:** 4.3, 7.1–7.4, 7.6, NFR 2

```
GET /api/news?season=&week=N   (sem season: a atual; sem week: todas as semanas da temporada, para a busca)
  200: [ Noticia ]              ordenadas por "incomum" (desc)
GET /api/summary?season=
  200: { "ratedPlayers": int, "season": int }

type Noticia = {
  id: str               # "{gameId}:{tipo}[:{extra}]", estável
  gameId: int, week: int,
  tipo: "resultado" | "virada" | "prorrogacao" | "goleada" | "maior_jogada"
        | "atuacao" | "defesa",
  tom: "red" | "blue" | "dark",   # cor do cartão (rascunho)
  tag: str              # rótulo curto: "Resultado", "Virada", "Defesa"...
  destaque: str         # número grande decorativo do cartão ("21", "4")
  titulo: str, texto: str,
  incomum: float        # 0–1, maior = mais fora da média da liga
  times: [str, str]     # para a busca e para o badge
}
```

### 2. `NFLData.news(season, week)` e `NFLData.summary(season)` (em `data_layer.py`)

**Responsabilidade:** transformar fatos dos jogos em notícias ordenadas pelo quanto fogem do comum.
**Atende aos requisitos:** 7.1, 7.3

- **Quando um fato vira notícia** (só jogos disputados, com o placar oficial):

| Tipo | Regra | Por semana (2021–2025, média · máx.) |
|---|---|---|
| `resultado` | todo jogo: "X vence Y por A–B" (com "na prorrogação" quando for o caso) | 12,9 · 16 |
| `virada` | o vencedor reverteu desvantagem de **10+ pontos** (placar oficial jogada a jogada) | 1,7 · 6 |
| `prorrogacao` | jogo decidido na prorrogação | 0,8 · 3 |
| `goleada` | margem de **28+ pontos** | 0,9 · 4 |
| `maior_jogada` | a jogada de mais jardas da semana (**só a 1ª**) | 1 |
| `atuacao` | jogador com **400+ jd de passe**, **5+ TD de passe**, **175+ jd correndo ou recebendo**, **4+ TD** ou **3,5+ sacks** num jogo | 1,6 · 6 |
| `defesa` | time com **6+ sacks** ou **3+ interceptações** num jogo | 2,7 · 9 |

- **Medido:** ~21 notícias por semana na média, e **toda semana disputada tem pelo menos 1** (o resultado), inclusive a do Super Bowl, com 1 jogo. Limiares mais baixos para atuação (350 jd, 150 jd, 3 TD) davam 6 por semana, até 14: viravam banais.
- **O "incomum"** é um percentil dentro da família do fato, na temporada inteira, calculado uma vez por temporada na carga: tamanho da virada, margem da goleada, jardas da maior jogada, a estatística da atuação, sacks ou interceptações do time. A prorrogação usa `1 − (jogos com prorrogação ÷ jogos da temporada)`. O **resultado** fica com `0,5 × percentil da margem`, abaixo dos fatos raros: assim o carrossel mostra primeiro o que foge do comum, e a tela Notícias lista também os resultados.
- **Texto:** montado só com números do dado (placar oficial, jardas, TDs, sacks), como a narração já faz. Nada de texto livre. Os nomes de jogador e time passam por `esc()` no cliente (S.1).

### 3. `js/api.js` e `js/ui.js`

**Responsabilidade:** acesso à API (cache LRU, dedupe, "só o último vence") e formatadores/HTML seguro, compartilhados pelas telas.
**Atende aos requisitos:** 8.5, NFR 1, S.1

```js
export function get(path): Promise<any>        // igual ao atual (LRU 150, dedupe)
export const api = { meta, games, game, plays, tracking, broadcast, players, player, compare, news, summary }
// cada chamada leva a temporada de S, como hoje; games() não entra no cache (status muda com o relógio)
export function ultimo(chave): () => boolean   // cria um contador; devolve "ainda sou o último?"
export function into(el, fn, msg, atual)       // igual ao atual
// ui.js: esc, pct, nm, secs, ordDown, brDate, weekday, badge(time), icone(nome)
```

### 4. `js/main.js` (casca e roteador)

**Responsabilidade:** estado compartilhado (semana, jogo, jogada), cabeçalho, menu lateral, busca, barra inferior e rotas `?screen=`.
**Atende aos requisitos:** 1.2, 2.1–2.6, 3.1–3.4, 8.1–8.6

```js
const S = { season, week, gameId, playId, jogoAba: "prancheta", playerId, filtroTime, live, liveFalha }
export function ir(tela, opcoes?)      // "inicio"|"jogo"|"jogadores"|"noticias"|"config"|"sobre"
export function selecionarJogo(id, { aba? })
// Deep links: ?screen=coach -> jogo/prancheta · commentator -> jogo/replay · scout -> jogadores
```

- **Filtros:** temporada e semana vêm de `meta.seasons` (rodadas de playoff pelo nome); sem escolha, a semana mais recente já começada (`currentWeek`), como hoje. Deep link: `?season=&week=&game=&screen=`.
- **Busca:** os times são filtrados localmente a partir de `meta.teams`; os jogadores vêm de `/api/players?q=&limit=8`, com `ultimo("busca")`; as notícias são filtradas localmente a partir de `/api/news?season=` (todas as semanas da temporada, ~350 itens). Tocar num time abre o Início com o filtro daquele time (um chip "TIME ×" remove o filtro).

### 5. Telas (`js/telas/*.js`)

**Responsabilidade:** cada uma desenha a sua tela a partir do estado e da API.
**Atende aos requisitos:** 4, 5, 6, 7.5, 9, 11

| Tela | O que vem de onde |
|---|---|
| Início | `news(week)[0..3]` no carrossel; `games(week).length` e `summary.ratedPlayers` nos cartões; `games(week)` na lista, com os estados e o placar ao vivo (`aoVivo`) da `dados-externos` |
| Jogo | Cabeçalho com placar, times e semana/rodada; **a matéria da ESPN logo abaixo** (`renderMateria`, só `*.espn.com`, some sem matéria); abas Prancheta (`coachLineup`, com o aviso de esquema ilustrativo), Jogadas (`coachPlays`), Replay (`renderBroadcast`), Estatísticas (`coachStats`) e Playbook (`coachBook`). Tocar numa jogada em Jogadas ou Replay leva à Prancheta com essa jogada. A aba e a jogada ficam em `S` |
| Jogadores | "A observar" (`game.watch` da partida selecionada, oculto se vazio) + a lista, o perfil e a comparação do Olheiro |
| Notícias | `news(week)`, ou a mensagem de vazio |
| Configurações | 2 controles do Requisito 11 |
| Sobre os dados | `meta.fontes` (fontes, créditos das licenças) e `meta.ultimaAtualizacao` (o `renderSobre` de hoje) |

- **As seções "Sugestões de tática" e "Bastidores" não são portadas** (Requisito 9). Os campos `insights` e `notes` (vazios desde a `dados-externos`) continuam na resposta de `/api/games/{id}` para não quebrar o golden; o front só os ignora.

### 6. `js/prancheta.js` (Field)

**Responsabilidade:** desenhar o esquema ilustrativo de uma jogada.
**Atende aos requisitos:** 5.3, 5.8

- O `Field` atual, movido como está (1 quadro, sem controles de animação, aviso "Esquema ilustrativo"), com o visual novo. **Sem interpolação:** o antigo Requisito 10 saiu (Q7).

### 7. `js/config.js`

**Responsabilidade:** ler, gravar e avisar mudanças das configurações.
**Atende aos requisitos:** 11.2–11.5, 4.5–4.6

```js
const PADRAO = { avancoNoticias: true, velocidadeReplay: 1 }   // replay: 1 jogada a cada 1,4 s ÷ velocidade
export function ler(): Config        // try/catch: se falhar, PADRAO
export function gravar(parcial)       // try/catch; aplica mesmo sem conseguir gravar
export function aoMudar(fn)
export const reduzirMovimento: () => boolean  // matchMedia('(prefers-reduced-motion: reduce)')
```

### 8. CSS (`app/css/app.css`, substituído)

**Responsabilidade:** o sistema visual do rascunho e os componentes que o rascunho não desenhou (abas, prancheta, linha do tempo do replay, barras de comparação, radar, perfil, formulário de configurações), no mesmo idioma visual.
**Atende aos requisitos:** 1.1–1.4, NFR 3–5

- Os tokens do rascunho viram a única fonte de cor, raio, fonte e movimento.
- **Correções contra os avisos do verificador de design** (herdados do protótipo e presentes em parte no rascunho):
  - o destaque lateral de 3 px do item ativo do menu vira fundo + cor do texto;
  - o ponto pulsante do "REPLAY" deixa de pulsar;
  - não há texto menor que 12 px;
  - as sombras são só de elevação, sem brilho colorido.
- A fonte Inter continua: foi uma decisão registrada no `rascunho/.impeccable/config.json`.

> **Teste de corte aplicado:**
> - (a) "Uma rota `/api/home` que devolve jogos, notícias e resumo de uma vez": cortada, porque os jogos já têm rota e já estão em cache.
> - (b) "Um módulo de estado reativo": cortado, porque um objeto `S` mais `ir()` resolvem.
> - (c) "Um módulo por aba da página Jogo": cortado, porque as 5 abas cabem em `jogo.js` reusando as funções atuais.

---

## Data Model

Não há persistência no servidor. No navegador:

| Entidade | Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|---|
| `localStorage["nfl.config.v2"]` | `avancoNoticias` | bool | não | padrão `true` |
| | `velocidadeReplay` | 0.5, 1 ou 2 | não | padrão `1`; qualquer outro valor vira `1` |

**Migração necessária:** não.

---

## Error Handling

| Falha | Detecção | Resposta | Requisito |
|---|---|---|---|
| Fontes externas não carregam | `onload` do preload nunca dispara | a página já está desenhada com a fonte do sistema (mesmo mecanismo da spec anterior) | 1.5 |
| Falha ao carregar os jogos da semana | `into()` pega a exceção | mensagem de erro na lista; os chips seguem funcionando | 3.4 |
| Semana sem notícias (ainda sem jogos disputados) | `news(week)` devolve `[]` | o Início esconde o carrossel; Notícias mostra "Sem notícias para esta semana" | 4.7, 7.6 |
| Página Jogo sem partida escolhida | `S.gameId` nulo | seleciona o 1º jogo da semana | 5.7 |
| Jogada sem formação | `hasFormation` falso (ou `api.tracking` → 404) | dados da jogada e "formação indisponível para esta jogada" no lugar do campo | 5.8 |
| Matéria da ESPN ausente, com erro ou com link fora da ESPN | `renderMateria` | o bloco some; link estranho não é exibido | 5.9 |
| Nenhum jogador a observar | `game.watch` vazio | a seção fica oculta | 6.4 |
| Resposta de busca atrasada | `ultimo("busca")()` falso | descartada | 8.5 |
| Busca sem resultado | as três listas vazias | "Nada encontrado para "{termo}"" | 8.4 |
| Configurações ilegíveis | `JSON.parse` ou `localStorage` lança | `PADRAO` | 11.5 |
| Link antigo (`?screen=coach` etc.) | mapa de rotas legadas | tela nova equivalente | 2.6 |
| Movimento reduzido no sistema | `matchMedia` | sem transições e sem carrossel automático | 1.4, 4.6 |

---

## Segurança

- **Texto vindo dos dados:** todo texto passa por `esc()` antes de entrar no HTML (é o padrão atual, que agora vale também para notícias e busca). As notícias são montadas no servidor e escapadas no cliente como qualquer outro campo (S.1).
- **Busca:** o termo é cortado em 100 caracteres no cliente (`slice(0, 100)`) e o servidor já limita o `limit` (S.2).
- **Configurações:** só aceitam os valores conhecidos; qualquer outro vira o padrão (evita um estado quebrado vindo de um `localStorage` adulterado).

---

## Testing Strategy

| Nível | O que cobre | O que é simulado |
|---|---|---|
| Unitário (pytest) | `news()`: limiares, ordenação por "incomum", texto só com números do dado, resultado com o vencedor pelo placar oficial, toda semana disputada com notícia; `summary()` | nada |
| Regressão | `golden.py check` (as rotas atuais não mudam) | nada |
| Navegador (Playwright + Edge) | navegação com 4 destinos, sem "Treinador/Olheiro/Comentarista"; filtros com as temporadas e rodadas dos dados; notícia abre o jogo; 5 abas mantendo jogo e jogada; matéria no topo da página Jogo; configurações persistem após recarregar e caem no padrão com `localStorage` corrompido; busca agrupada, vazia e com resposta atrasada; links antigos; reduced-motion; **os testes da `dados-externos` (`test_ui_dados.py`: ao vivo, matéria, prancheta, "Sobre") adaptados às telas novas** | latência e falha pelo `fetch` embrulhado; ESPN por `page.route`; relógio por `page.clock`; `prefers-reduced-motion` pelo `emulateMedia` |
| Desempenho | `bench.py`, `carga.py --usuarios 10`, `test_ui_home_pronta_ate_200ms` e `test_ui_proxima_jogada_ate_50ms` (adaptados às telas novas) | nada |
| Acessibilidade | alvos ≥ 44 px e contraste ≥ 4,5:1 medidos no navegador (`getBoundingClientRect` + cores computadas) | nada |
| Manual | comparação visual com o rascunho, lado a lado, nas 6 telas | |

**Critério de pronto:** todo critério do requirements tem um teste nomeado no `tasks.md`.

---

## Decisões e alternativas descartadas

### Decisão 1: dividir o front-end em módulos ES nativos

**Alternativas consideradas:** manter o `app.js` único (1.121 linhas, que cresceriam com notícias, busca, configurações e menu); módulos com um bundler.
**Escolha:** `<script type="module">` com 7 arquivos, sem build.
**Motivo:** os navegadores atuais carregam módulos sem ferramenta. O arquivo único passaria de ~1.600 linhas, e a página Jogo e a prancheta ganham lógica nova que fica mais fácil de testar isolada. O requisito proíbe etapa de build, o que exclui o bundler.
**Custo aceito:** 7 pedidos de JS em vez de 1. Localmente é desprezível (revalidação por ETag, 304). Numa rede lenta, dá para voltar a um arquivo só.

### Decisão 2: notícias geradas no servidor

**Alternativas consideradas:** gerar no navegador a partir de `/api/games/{id}` de cada jogo da semana.
**Escolha:** rota `/api/news` no servidor.
**Motivo:** o "incomum" precisa de distribuições da temporada inteira (~285 jogos), que só o servidor tem. No navegador seriam 16 pedidos por semana e dados de liga duplicados.
**Custo aceito:** uma rota e ~150 linhas no `data_layer`.

### Decisão 3: a notícia de resultado volta, com o placar oficial

**Contexto (v0.3):** o placar do dataset antigo era o do último dropback (TB × DAL aparecia 28–29; o oficial foi 31–29 para o TB), então a notícia de resultado tinha saído.
**v0.4:** com a `dados-externos`, o placar é o oficial do nflverse, jogada a jogada. O resultado volta dizendo quem venceu, e a virada passa a considerar o jogo inteiro (não mais "até o último dropback").
**Custo aceito:** nenhum.

### Decisão 4 (removida na v0.4): interpolação da prancheta

A interpolação linear entre quadros saiu com o antigo Requisito 10: sem tracking, não há quadros para interpolar (Q7).

---

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| A reorganização quebra algo que funciona hoje (prancheta, replay, comparação, placar ao vivo, matéria) | alto | as funções são movidas, não reescritas; os testes de navegador das specs anteriores (`test_ui.py`, `test_ui_dados.py`) são adaptados às telas novas **antes** de remover o código antigo |
| Os módulos ES aumentam o tempo da home além de 200 ms | médio | medido na tarefa de desempenho; se passar, `modulepreload` no HTML ou um único arquivo |
| Os limiares das notícias geram poucas ou notícias demais | baixo | **medido na v0.4:** ~21 por semana (2021–2025); um teste fixa pelo menos 1 notícia por semana disputada e no máximo 40, para pegar mudança acidental |
| O rascunho não desenhou abas, prancheta, replay, radar e comparação; o visual deles vira decisão do implementador | médio | seguem os tokens e componentes do rascunho; revisão visual das 6 telas antes de fechar (tarefa manual) |

---

## Aprovação

- [x] Todo requisito do requirements.md está atendido por algum componente
- [x] Nenhum componente existe sem requisito que o justifique
- [x] Todo SE...ENTÃO aparece na tabela de erros
- [x] Pelo menos um componente foi cortado na revisão (`/api/home`, estado reativo, módulo por aba)
- [x] Decisões relevantes registradas com alternativa descartada
- [x] Decisão 3 decidida pelo time: sem notícia de placar até a spec `dados-externos` (v0.4: volta, com o placar oficial)

**Aprovado por:** José Cota em 2026-09-25 (v0.3). **v0.4: aguardando aprovação.**
