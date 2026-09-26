# Design Document

**Feature:** novo-visual
**Workflow:** requirements-first
**Status:** aprovado
**Data:** 2026-09-25

---

## Overview

O front-end é reescrito sobre a identidade do `rascunho/` e dividido em **módulos ES nativos**, sem etapa de build. Um módulo para a casca (cabeçalho, menu lateral, busca, barra inferior e navegação) e um por tela: Início, Jogo, Jogadores, Notícias, Configurações e Sobre.

A lógica que já funciona é **movida, não reescrita**:
- a prancheta e o replay do Comentarista vão para as abas da página Jogo;
- o Olheiro vira a tela Jogadores;
- o cache `get()` e os contadores "só o último vence" viram um módulo de API compartilhado.

Há três peças novas:
1. **Notícias**, geradas no servidor por uma rota nova e calculadas a partir de fatos que o `data_layer` já tem.
2. **Movimento contínuo da prancheta:** um laço de `requestAnimationFrame` que interpola entre quadros registrados e mostra os quadros exatos ao pausar.
3. **Configurações**, salvas no navegador.

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
                  ├── js/telas/inicio.js      carrossel · 2 cartões · jogos da semana
                  ├── js/telas/jogo.js        5 abas ──► js/prancheta.js (Field + interpolação)
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
5. A prancheta desenha a primeira jogada com tracking e pré-carrega as vizinhas, como já faz hoje.

### Fluxo: prancheta em reprodução (Requisito 10)

1. O play começa e grava `t0 = performance.now()` e `quadro0`.
2. A cada `requestAnimationFrame`: `q = quadro0 + (agora - t0) / 100ms × velocidade`, com `i = floor(q)` e `f = q - i`.
3. Para cada jogador, se existem as posições `P[i]` e `P[i+1]`, ele é desenhado em `P[i] + f × (P[i+1] - P[i])`. Se falta uma das duas, ele fica em `P[i]` (ou some, se `P[i]` também não existe). Nunca se inventa trajetória.
4. O controle deslizante e o relógio mostram `i`, o quadro registrado.
5. Ao pausar, ao arrastar ou ao chegar ao fim, tudo é desenhado exatamente em `P[i]`.
6. Com animação suave desligada ou `prefers-reduced-motion`, o laço usa `f = 0` sempre, igual ao comportamento atual.

### O que já existe e será reusado

- **`app/js/app.js`, reaproveitado por partes:** `get()`/`qs()`/`seq`/`into()` e os formatadores (`esc`, `pct`, `nm`, `secs`, `ordDown`, `brDate`) vão para `api.js`/`ui.js`. `Field` (viewport, marcações, pontos) vai para `prancheta.js`. `coachLineup`, `loadFieldPlay`, `prefetchVizinhas`, `playRow`, `coachStats`, `coachBook`, `renderBroadcast`/`paintBc`, `scoutList`, `scoutDetail`, `radarSVG`, `fillComparePicker` e `showCompare` vão para as telas novas. **A lógica fica; muda o HTML gerado e as classes.**
- **`NFLData.notes()`** já calcula a maior jogada, o pocket mais longo, o mais rápido e as faltas de um jogo. **`NFLData.watch_list()`** alimenta os "Jogadores a observar". **`_derived_score`** e os `play_idx` por jogo alimentam resultado, virada, prorrogação, sacks e interceptações.
- **`CacheDeRespostas`** e o aquecimento: as rotas novas entram no cache sem código extra, e `/api/news` de cada semana entra na lista de aquecimento.
- **`rascunho/style.css`:** os tokens (`--bg`, `--surface`, `--red`...), o cabeçalho, os chips, o carrossel, os cartões, a barra inferior e o menu lateral viram a base do CSS novo.

---

## Components and Interfaces

### 1. Rotas novas no servidor

**Responsabilidade:** entregar notícias e o resumo sem mudar nenhuma rota existente.
**Atende aos requisitos:** 4.3, 7.1–7.4, 7.6, NFR 2

```
GET /api/news?week=N        (sem week: todas as semanas, para a busca)
  200: [ Noticia ]           ordenadas por "incomum" (desc)
GET /api/summary
  200: { "ratedPlayers": int, "season": int, "weeks": [int] }

type Noticia = {
  id: str               # "{gameId}:{tipo}[:{extra}]", estável
  gameId: int, week: int,
  tipo: "virada" | "prorrogacao" | "maior_jogada" | "mais_rapido"
        | "pocket" | "sacks" | "interceptacoes",
  tom: "red" | "blue" | "dark",   # cor do cartão (rascunho)
  tag: str              # rótulo curto: "Tracking", "Defesa"...
  destaque: str         # número grande decorativo do cartão ("21", "4")
  titulo: str, texto: str,
  incomum: float        # 0–1, maior = mais fora da média da liga
  times: [str, str]     # para a busca e para o badge
}
```

### 2. `NFLData.news(week)` e `NFLData.summary()` (em `data_layer.py`)

**Responsabilidade:** transformar fatos do jogo em notícias ordenadas pelo quanto fogem do comum.
**Atende aos requisitos:** 7.1, 7.3

- **O "incomum" é um percentil dentro da própria família de fato, na liga inteira** (122 jogos), calculado uma vez no `_load`:
  - maior jogada: percentil do `playResult` entre as maiores jogadas de cada jogo;
  - mais rápido: percentil da velocidade de pico entre os picos de cada jogo;
  - pocket: percentil do `timeToThrow`;
  - sacks e interceptações: percentil entre os times-jogo;
  - virada: percentil do tamanho da desvantagem revertida;
  - prorrogação: `1 − (jogos com prorrogação ÷ 122)`.
- **Quando um fato vira notícia**, para não noticiar o banal (regra medida nos dados, ver abaixo):
  - **Recordes da semana:** maior jogada, jogador mais rápido e pocket mais longo. **Só o 1º da semana** de cada um (3 notícias).
  - **Eventos por jogo:** time com **≥ 5 sacks**; time com **≥ 3 interceptações**; **virada de ≥ 7 pontos** até o último dropback; **prorrogação**.
  - **Medido nas 8 semanas:** de **16 a 21 notícias por semana** com o placar apertado incluído (~1 por jogo). Sem ele (Decisão 3), sobram ~4–5 a menos por semana, **12–17**, ainda bem acima das 4 do carrossel. A primeira proposta (recorde por jogo, pocket ≥ 5 s, sacks ≥ 4, interceptações ≥ 2) dava 50–59 por semana, e o pocket ≥ 5 s disparava em 120 dos 122 jogos, ou seja, não era notícia.
- **Texto:** montado com os números do dado, como já fazem `notes()` e `insights()`. Nada de texto livre.

### 3. `js/api.js` e `js/ui.js`

**Responsabilidade:** acesso à API (cache LRU, dedupe, "só o último vence") e formatadores/HTML seguro, compartilhados pelas telas.
**Atende aos requisitos:** 8.5, NFR 1, S.1

```js
export function get(path): Promise<any>        // igual ao atual (LRU 150, dedupe)
export const api = { meta, games, game, plays, tracking, broadcast, players, player, compare, news, summary }
export function ultimo(chave): () => boolean   // cria um contador; devolve "ainda sou o último?"
export function into(el, fn, msg, atual)       // igual ao atual
// ui.js: esc, pct, nm, secs, ordDown, brDate, weekday, badge(time), icone(nome)
```

### 4. `js/main.js` (casca e roteador)

**Responsabilidade:** estado compartilhado (semana, jogo, jogada), cabeçalho, menu lateral, busca, barra inferior e rotas `?screen=`.
**Atende aos requisitos:** 1.2, 2.1–2.6, 3.1–3.4, 8.1–8.6

```js
const S = { season, week, gameId, playId, jogoAba: "prancheta", playerId, filtroTime }
export function ir(tela, opcoes?)      // "inicio"|"jogo"|"jogadores"|"noticias"|"config"|"sobre"
export function selecionarJogo(id, { aba? })
// Deep links: ?screen=coach -> jogo/prancheta · commentator -> jogo/replay · scout -> jogadores
```

- **Busca:** os times são filtrados localmente a partir de `meta.teams`; os jogadores vêm de `/api/players?q=&limit=8`, com `ultimo("busca")`; as notícias são filtradas localmente a partir de `/api/news` (todas as semanas, ~300 itens). Tocar num time abre o Início com o filtro daquele time (um chip "TIME ×" remove o filtro).

### 5. Telas (`js/telas/*.js`)

**Responsabilidade:** cada uma desenha a sua tela a partir do estado e da API.
**Atende aos requisitos:** 4, 5, 6, 7.5, 9, 11

| Tela | O que vem de onde |
|---|---|
| Início | `news(week)[0..3]` no carrossel; `games(week).length` e `summary.ratedPlayers` nos cartões; `games(week)` na lista |
| Jogo | Cabeçalho com placar e times; abas Prancheta (`coachLineup`), Jogadas (`coachPlays`), Replay (`renderBroadcast`), Estatísticas (`coachStats`) e Playbook (`coachBook`). Tocar numa jogada em Jogadas ou Replay leva à Prancheta com essa jogada. A aba e a jogada ficam em `S` |
| Jogadores | "A observar" (`game.watch` da partida selecionada, oculto se vazio) + a lista, o perfil e a comparação do Olheiro |
| Notícias | `news(week)`, ou a mensagem de vazio |
| Configurações | 3 controles do Requisito 11 |
| Sobre os dados | `meta.dataset` (o texto que hoje fica no rodapé da home) |

- **As seções "Sugestões de tática" e "Bastidores" não são portadas** (Requisito 9). Os campos `insights` e `notes` continuam na resposta de `/api/games/{id}` para não quebrar o golden; o front só os ignora.

### 6. `js/prancheta.js` (Field com interpolação)

**Responsabilidade:** desenhar e animar o tracking de uma jogada.
**Atende aos requisitos:** 10.1–10.6, 5.8

```js
export class Field {
  constructor(root, dados, { suave, velocidade })
  setFrame(i)        // quadro registrado exato (pausa/arraste)
  play() / pause() / toggle() / setSpeed(v) / setSuave(bool)
  onFrame(i) / onState(tocando) / onSelect(jogador)
}
```

- **Posição por `transform: translate(...)`** em vez de `left`/`top`: não força layout a cada quadro do rAF.
- As coordenadas continuam em porcentagem do campo, e a conversão de `pos()` é a atual.

### 7. `js/config.js`

**Responsabilidade:** ler, gravar e avisar mudanças das configurações.
**Atende aos requisitos:** 11.2–11.5, 4.5–4.6, 10.6

```js
const PADRAO = { animacaoSuave: true, avancoNoticias: true, velocidade: 1 }
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
| `localStorage["nfl.config.v1"]` | `animacaoSuave` | bool | não | padrão `true` |
| | `avancoNoticias` | bool | não | padrão `true` |
| | `velocidade` | 0.25, 0.5, 1 ou 2 | não | padrão `1`; qualquer outro valor vira `1` |

**Migração necessária:** não.

---

## Error Handling

| Falha | Detecção | Resposta | Requisito |
|---|---|---|---|
| Fontes externas não carregam | `onload` do preload nunca dispara | a página já está desenhada com a fonte do sistema (mesmo mecanismo da spec anterior) | 1.5 |
| Falha ao carregar os jogos da semana | `into()` pega a exceção | mensagem de erro na lista; os chips seguem funcionando | 3.4 |
| Semana sem notícias | `news(week)` devolve `[]` | o Início esconde o carrossel; Notícias mostra "Sem notícias para esta semana" | 4.7, 7.6 |
| Página Jogo sem partida escolhida | `S.gameId` nulo | seleciona o 1º jogo da semana | 5.7 |
| Jogada sem tracking | `api.tracking` → 404 | dados da jogada e aviso "Tracking indisponível" no lugar do campo | 5.8 |
| Jogador sem posição num dos quadros | `P[i]` ou `P[i+1]` nulo | fica parado em `P[i]` ou some; nada é interpolado | 10.5 |
| Nenhum jogador a observar | `game.watch` vazio | a seção fica oculta | 6.4 |
| Resposta de busca atrasada | `ultimo("busca")()` falso | descartada | 8.5 |
| Busca sem resultado | as três listas vazias | "Nada encontrado para "{termo}"" | 8.4 |
| Configurações ilegíveis | `JSON.parse` ou `localStorage` lança | `PADRAO` | 11.5 |
| Link antigo (`?screen=coach` etc.) | mapa de rotas legadas | tela nova equivalente | 2.6 |
| Movimento reduzido no sistema | `matchMedia` | sem transições e sem carrossel automático; prancheta quadro a quadro | 1.4, 4.6, 10.6 |

---

## Segurança

- **Texto vindo dos dados:** todo texto passa por `esc()` antes de entrar no HTML (é o padrão atual, que agora vale também para notícias e busca). As notícias são montadas no servidor e escapadas no cliente como qualquer outro campo (S.1).
- **Busca:** o termo é cortado em 100 caracteres no cliente (`slice(0, 100)`) e o servidor já limita o `limit` (S.2).
- **Configurações:** só aceitam os valores conhecidos; qualquer outro vira o padrão (evita um estado quebrado vindo de um `localStorage` adulterado).

---

## Testing Strategy

| Nível | O que cobre | O que é simulado |
|---|---|---|
| Unitário (pytest) | `news()`: limiares, ordenação por "incomum", texto só com números do dado, placar sem declarar vencedor; `summary()` | nada |
| Regressão | `golden.py check` (as rotas atuais não mudam) | nada |
| Navegador (Playwright + Edge) | navegação com 4 destinos, sem "Treinador/Olheiro/Comentarista"; filtros só com 2021 e semanas 1–8; notícia abre o jogo; 5 abas mantendo jogo e jogada; interpolação (posição entre quadros ≠ quadro, pausa = quadro exato); configurações persistem após recarregar e caem no padrão com `localStorage` corrompido; busca agrupada, vazia e com resposta atrasada; links antigos; reduced-motion | latência e falha pelo `fetch` embrulhado (como na spec anterior); `prefers-reduced-motion` pelo `emulateMedia` |
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
**Motivo:** o "incomum" precisa de distribuições da liga inteira (122 jogos), que só o servidor tem. No navegador seriam 16 pedidos por semana e dados de liga duplicados.
**Custo aceito:** uma rota e ~150 linhas no `data_layer`.

### Decisão 3: sem notícia de placar nesta spec

**Contexto:** o placar do app é o **do último dropback**. O dataset não tem os pontos marcados depois (field goal final, TD terrestre). Exemplo real: TB × DAL, semana 1, aparece 28–29, mas o oficial foi **31–29 para o TB**.
**Alternativas consideradas:** (a) "X vence Y por A–B" (falso em casos como esse); (b) manchetes cuidadosas, como "29–28 no último dropback"; (c) não gerar notícia de placar até existir o placar oficial.
**Escolha:** (c), decidida pelo José em 2026-09-25 depois da pesquisa de APIs. **O nflverse tem o placar oficial**, e a coluna `old_game_id` é exatamente o nosso `gameId`. A notícia de placar volta na spec `dados-externos`, dizendo quem venceu.
**Motivo:** (b) seria uma notícia confusa, que logo seria trocada pela versão oficial.
**Efeito em outros tipos:** a **virada** continua, sempre escrita como "até o último dropback" (é um fato do dataset: o time reverteu a desvantagem até ali).
**Custo aceito:** um tipo de notícia a menos por algumas semanas.

### Decisão 4: interpolação linear só na reprodução

**Alternativas consideradas:** curvas suaves (spline); interpolar também ao arrastar a linha do tempo.
**Escolha:** linear entre dois quadros consecutivos, só durante o play.
**Motivo:** a 10 quadros por segundo, a distância entre quadros é pequena (< 1 jd) e o linear já parece contínuo. A spline "inventaria" curvaturas. Arrastando, o usuário quer ver o dado exato (Requisito 10.3).
**Custo aceito:** em mudanças bruscas de direção, o movimento pode parecer levemente "anguloso".

---

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| A reorganização quebra algo que funciona hoje (prancheta, replay, comparação) | alto | as funções são movidas, não reescritas; os testes de navegador da spec anterior são adaptados às telas novas **antes** de remover o código antigo |
| Os módulos ES aumentam o tempo da home além de 200 ms | médio | medido na tarefa de desempenho; se passar, `modulepreload` no HTML ou um único arquivo |
| Os limiares das notícias geram poucas ou notícias demais | baixo | **já medido no design:** 16–21 por semana com a regra escolhida; um teste fixa um mínimo de 4 e um máximo de 30 por semana, para pegar mudança acidental |
| O laço de `requestAnimationFrame` gasta bateria com a prancheta parada | baixo | o laço só roda enquanto a jogada toca |
| O rascunho não desenhou abas, prancheta, replay, radar e comparação; o visual deles vira decisão do implementador | médio | seguem os tokens e componentes do rascunho; revisão visual das 6 telas antes de fechar (tarefa manual) |

---

## Aprovação

- [x] Todo requisito do requirements.md está atendido por algum componente
- [x] Nenhum componente existe sem requisito que o justifique
- [x] Todo SE...ENTÃO aparece na tabela de erros
- [x] Pelo menos um componente foi cortado na revisão (`/api/home`, estado reativo, módulo por aba)
- [x] Decisões relevantes registradas com alternativa descartada
- [x] Decisão 3 decidida pelo time: sem notícia de placar até a spec `dados-externos`

**Aprovado por:** José Cota em 2026-09-25 ("vamos terminar a spec visual"; a notícia de placar fica para a spec de APIs)
