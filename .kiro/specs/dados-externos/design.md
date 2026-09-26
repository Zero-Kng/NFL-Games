# Design Document

**Feature:** dados-externos
**Workflow:** requirements-first
**Status:** aprovado
**Data:** 2026-09-25

---

## Overview

O app deixa de ler o dataset do Big Data Bowl e passa a trabalhar sobre **arquivos públicos do nflverse**, baixados pelo servidor e guardados localmente. Isso vale para 2021 a 2026: calendário e placar oficial, todas as jogadas, jogadores em campo e formação, estatísticas por jogador e estatísticas avançadas.

- **Atualização:** um módulo de fontes baixa só o que mudou (usa a data de atualização de cada arquivo) e valida as colunas. O ETL monta, por temporada, tabelas compactas no formato binário que já usamos (`.npz`).
- **Servidor:** carrega essas tabelas e responde pelas **mesmas rotas de hoje**, com o parâmetro `season` a mais. Uma vez por dia, ele se atualiza sozinho e troca os dados sem reiniciar.
- **A prancheta vira um esquema:** os jogadores reais da jogada, colocados em posições-modelo da formação.
- **Ratings:** passam a ser percentis de estatísticas públicas dentro de cada grupo de posição.
- **ESPN (placar ao vivo e matéria do jogo):** é consultada **pelo navegador**, porque bloqueia chamadas de servidor (testado: 403 pelo Python, 200 pelo navegador, com CORS liberado).

---

## Fontes (verificadas em 2026-09-25)

| Conjunto (release do nflverse) | Arquivo | Temporadas | Tamanho (2021–26) | Usado para |
|---|---|---|---|---|
| `schedules` | `games.csv.gz` | todas | 0,5 MB | jogos, placar oficial, prorrogação, rodadas de playoff, **id da ESPN** |
| `players` | `players.csv.gz` | — | 2,4 MB | bio, posição, foto, **ponte entre o id gsis e o id do PFR** |
| `pbp` | `play_by_play_{ano}.csv.gz` | 2021–2026 | 93 MB | todas as jogadas, placar a cada jogada, EPA |
| `pbp_participation` | `pbp_participation_{ano}.csv` | 2021–**2025** | 185 MB | formação, pessoal, box, rushers e os 22 jogadores (nome, posição e número) |
| `ftn_charting` | `ftn_charting_{ano}.csv` | **2022**–2026 | 31 MB | posição do QB, backfield, box, rushers (a única formação de 2026) |
| `stats_player` | `stats_player_week_{ano}.csv.gz` | 2021–2026 | 6 MB | estatísticas por jogo |
| `pfr_advstats` | `advstats_week_{def,pass,rush,rec}_{ano}` | 2021–2026 | 5 MB | pressões, blitz, tackles perdidos, drops, jardas após contato, rating permitido |
| `snap_counts` | `snap_counts_{ano}.csv.gz` | 2021–2026 | 2 MB | snaps por jogador (volume; base da linha ofensiva) |

**Total bruto: ~326 MB.** Com as tabelas processadas, fica em ~500 MB (limite do NFR 4: 1 GB).

**ESPN, só pelo navegador:**
- `site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`: estado de cada jogo (`pre`, `in` ou `post`), placar, quarto e relógio. Hoje mostra 2026, semana 3.
- `.../summary?event={espnId}`: a matéria do jogo (`article.headline`, `published`, `source`, e `links.web.href` para `espn.com/nfl/recap?...`).

---

## Architecture

### Visão de alto nível

```
              nflverse (GitHub releases)                     ESPN (navegador)
                        │                                        │
etl/fontes.py  ── baixa só o que mudou, valida colunas           │
        │         dados/brutos/…  +  dados/manifest.json          │
etl/montar.py  ── uma pasta por temporada, tabelas .npz           │
etl/ratings.py    dados/temporadas/{ano}/{jogos,jogadas,          │
        │                          jogadores,jogador_jogo}.npz    │
        ▼                                                        │
server/data_layer.py ── carrega as temporadas, responde às rotas │
server/prancheta.py  ── esquema da formação de uma jogada        │
server/serve.py      ── rotas (+ season), cache de respostas,     │
                        atualização diária em 2º plano           │
        ▼                                                        ▼
app/ (telas atuais, adaptadas o mínimo) ─── placar ao vivo e matéria (fetch direto)
```

### Fluxo: atualização diária (Requisito 7)

1. Uma thread do servidor acorda a cada 24 h (e também na subida) e chama `fontes.sincronizar()`.
2. `sincronizar` faz **uma** chamada à API do GitHub por release (8 no total) e compara o `updated_at` e o `size` de cada arquivo com o `manifest.json`. Só baixa o que mudou, sempre num `.tmp` que depois é renomeado.
3. Cada arquivo baixado passa pela validação de colunas (S.2). Se falhar, ele é descartado, a cópia anterior é mantida e o erro vai para o log.
4. `montar.temporadas(alteradas)` refaz só as temporadas cujos arquivos mudaram. Na prática, a atual.
5. O servidor carrega um `NFLData` **novo** em segundo plano e, pronto, troca a referência global, limpa o cache de respostas e reaquece a semana atual (7.3). As requisições em andamento terminam com o objeto antigo.
6. Se não houver internet: ele loga e segue com o que tem (7.5). Se não houver internet **e** nenhuma cópia local: mensagem no terminal e o servidor não sobe (7.6).

### Fluxo: placar ao vivo (Requisito 10)

1. `/api/games?season=&week=` devolve cada jogo com `espnId` e `status` (`agendado`, `encerrado` ou `sem_resultado`).
2. Se a semana exibida é a atual e tem jogo sem resultado ainda, o navegador consulta o scoreboard da ESPN **a cada 30 s**.
3. Cada evento é casado pelo `espnId`. Com `state == "in"`, o cartão mostra o placar, o quarto, o relógio e a marca **AO VIVO**. Com `post`, mostra o final e para de consultar aquele jogo.
4. Sem jogo `in` ou `pre` com início já passado na semana, a consulta para (10.4). Se a consulta falhar, o cartão mantém o último placar com "atualização ao vivo indisponível" (10.5).
5. Depois que a atualização diária traz o jogo, vale o placar do nflverse (10.6).

### O que já existe e será reusado

- **`CacheDeRespostas`**, o aquecimento, a borda HTTP (503, ETag, fila) e o `tools/` (golden, bench, carga): sem mudança, só a lista de aquecimento passa a ser da temporada atual.
- **O padrão de `ensure_cache`** (manifesto, processamento incremental, gravação atômica, `ETL_VERSION`): vira a base de `fontes.py` e `montar.py`.
- **`tracking_npz.py`**, que grava números bit a bit e texto como categoria: é generalizado para qualquer tabela (`tabela_npz.py`).
- **`_pct_rank` e a fórmula `40 + média dos percentis × 0,59`** dos ratings: continuam. Mudam as estatísticas de cada eixo.
- **A lógica de cada rota do `data_layer.py`** (cartão de jogo, cartão de jogada, narração, comparação, líderes, jogo a jogo): mantém o formato das respostas. Muda a origem das colunas.
- **Frontend:** o `Field` desenha um quadro só (o esquema) sem mudança nenhuma. A tela atual continua; entram o seletor de temporada, os nomes das rodadas de playoff, o bloco da matéria e o placar ao vivo.

---

## Components and Interfaces

### 1. `etl/fontes.py`

**Responsabilidade:** manter em `dados/brutos/` uma cópia validada e atualizada dos arquivos do nflverse.
**Atende aos requisitos:** 7.1, 7.2, 7.5, 7.6, NFR 3, S.2, S.3

```python
CATALOGO: list[Fonte]      # release, padrão do nome, temporadas, colunas obrigatórias
@dataclass
class Fonte: release: str; padrao: str; anos: range | None; colunas: set[str]

def sincronizar(destino: Path, anos: range, progresso=print) -> Sincronizacao:
    """Baixa só o que mudou (updated_at + size do GitHub). Nunca apaga a cópia
    boa antes de a nova estar validada. Levanta SemDados se não houver internet
    e nenhuma cópia local."""
@dataclass
class Sincronizacao: baixados: list[str]; falhas: list[str]; anos_alterados: set[int]
```

- Só aceita URLs `https://github.com/nflverse/nflverse-data/releases/download/...` e `https://api.github.com/repos/nflverse/nflverse-data/releases` (S.3).
- A API do GitHub sem autenticação permite 60 chamadas por hora; cada sincronização gasta 8. Com o limite estourado, a sincronização é tratada como "sem internet".

### 2. `etl/montar.py` e `server/tabela_npz.py`

**Responsabilidade:** transformar os brutos de uma temporada em 4 tabelas prontas para o servidor.
**Atende aos requisitos:** 1, 2, 3, 4, 5.3

| Tabela | Uma linha por | Colunas principais |
|---|---|---|
| `jogos` (**geral**, todas as temporadas) | jogo | `gameId` (= `old_game_id`), `season`, `week`, `game_type` (REG, WC, DIV, CON, SB), `rodada`, `gameday`, `gametime`, `home`, `away`, `home_score`, `away_score`, `overtime`, `espnId`. O `status` é calculado **na hora da requisição**, porque depende do relógio |
| `jogadas` | jogada (pbp) | `gameId`, `playId`, `qtr`, `clock`, `down`, `ydstogo`, `yardline_100`, `posteam`, `defteam`, `play_type`, `yards_gained`, `desc`, `epa`, `total_home_score`, `total_away_score`, `pass`/`rush`/`sack`/`interception`/`touchdown`, `penalty`… mais a formação (participação ou FTN): `formacao`, `pessoal_of`, `pessoal_def`, `box`, `rushers`, `qb_local`, `hash`, `cobertura`, `jogadores` (gsis;…), `posicoes`, `numeros`, `nomes` |
| `jogadores` | jogador × temporada | `playerId` (gsis), nome, posição, grupo, time principal, foto, bio, estatísticas da temporada, eixos do radar, percentis, `rating`, `avaliado` |
| `jogador_jogo` | jogador × jogo | `playerId`, `gameId`, snaps e as estatísticas do jogo (jogo a jogo e comparação) |

- **Junções:** as jogadas se ligam à participação por `(old_game_id, play_id)` e ao FTN por `(nflverse_game_id, nflverse_play_id)`. As estatísticas do PFR se ligam ao `stats_player` pela ponte `pfr_id → gsis_id` da tabela `players`.
- `tabela_npz.py` generaliza o `tracking_npz.py`: qualquer DataFrame, números bit a bit e texto como categoria.

### 3. `etl/ratings.py`

**Responsabilidade:** calcular os eixos, os percentis e o rating de cada jogador por grupo e temporada.
**Atende aos requisitos:** 5.1, 5.2, 5.4, 5.5, 5.7

- **Rating** = `40 + média dos percentis dos eixos × 0,59`, **dentro do grupo e da temporada**. É a mesma fórmula de hoje.
- **Mínimo de volume por jogo do time**, para o rating ser justo também no meio da temporada atual. É multiplicado pelos jogos que o time já fez:

| Grupo | Posições | Mínimo por jogo | Eixos (↓ = menor é melhor) |
|---|---|---|---|
| QB | QB | 15 dropbacks | EPA por dropback · CPOE · jardas por tentativa · interceptações por tentativa ↓ · sacks por dropback ↓ · EPA das corridas por jogo |
| RB | RB, FB | 6 toques | EPA por corrida · jardas após contato por corrida · tackles quebrados por toque · jardas recebidas por jogo · fumbles perdidos por toque ↓ |
| WR/TE | WR, TE | 3 alvos | jardas por alvo · EPA por alvo · recepções por alvo · alvos por jogo · % de drops ↓ |
| Linha ofensiva | T, G, C | 30 snaps de ataque | volume (snaps) · faltas por 100 snaps ↓ · % de pressão sofrida pelo time nos jogos dele ↓ · jardas antes do contato do time nos jogos dele |
| Edge | DE, OLB pass rusher | 20 snaps de defesa | pressões por snap · sacks por snap · QB hits por snap · tackles para perda por snap · % de tackles perdidos ↓ |
| Linha defensiva | DT, NT | 20 snaps de defesa | pressões por snap · sacks por snap · QB hits por snap · tackles para perda por snap · % de tackles perdidos ↓ |
| Linebacker | ILB, MLB, OLB/LB de cobertura | 20 snaps de defesa | tackles por snap · tackles para perda por snap · pressões por snap · rating de passe permitido ↓ · % de tackles perdidos ↓ |
| Secundária | CB, S, FS, SS, DB | 20 snaps de defesa | rating de passe permitido ↓ · % de passes completados permitidos ↓ · jardas por alvo permitidas ↓ · (interceptações + passes defendidos) por alvo · % de tackles perdidos ↓ |

- **Linha ofensiva:** 2 dos 4 eixos são do **time** nos jogos em que o jogador atuou, porque não há pressão cedida individual em fonte pública. A resposta traz `baseReduzida: true` (5.7).
- **Edge × linha defensiva × linebacker** (validação 4.4): pela posição do depth chart do elenco (`depth_chart_position`: DE/DT/NT, OLB/ILB/MLB/LB). "OLB" também cobre o SAM/WILL do 4-3, então OLB/LB vira Edge só com mais pressões que alvos permitidos na temporada; sem números, OLB → Edge e LB → Linebacker. Sem depth chart, vale a posição da estatística.
- **Eixos por grupo:** 4 a 6 (o QB tem 6); a tabela `jogadores` tem `eixo{0..5}`.
- **Eixo sem dado na temporada:** vai como `{"percentile": null, "motivo": "..."}` e fica fora da média (5.5).
- O radar da versão antiga tinha "velocidade", que vinha do tracking. Ele sai.

### 4. `server/prancheta.py`

**Responsabilidade:** posicionar os jogadores de uma jogada num esquema da formação.
**Atende aos requisitos:** 4.1–4.6

```python
def esquema(jogada: dict) -> dict | None:
    """Mesmo formato de hoje de /tracking com 1 quadro: players[{nflId, name,
    jersey, position, side, t:[[x, y, 0, 0, 0]]}], ball, lineOfScrimmage,
    yardsToGo, frameCount=1, ilustrativo=True. None se não houver formação."""
```

- **Coordenadas no sistema do dataset antigo** (x de 0 a 120 no comprimento, y de 0 a 53,3), ataque jogando para `+x` (`playDirection = "right"`). Assim o `Field` atual desenha sem mudança.
- **Ataque:**
  - OL em linha a 1 jd da linha de scrimmage, 1,2 jd entre si (T G C G T; jogadores extras de OL ficam nas pontas).
  - TE colado ao T.
  - WRs abertos, alternando lados: fora a 5 jd da lateral, slot a 13 jd.
  - QB a 2 jd (sob o center, logo atrás do C, que está a 1 jd), 4 jd (pistol) ou 5 jd (shotgun), conforme `qb_local` (FTN) ou, sem ele, a `formacao` (2021: SINGLEBACK/I_FORM/JUMBO = sob o center; EMPTY/WILDCAT = shotgun).
  - RB: no shotgun ao lado do QB; no pistol 2 jd atrás dele; sob o center a 6 jd, com o FB a 3,5 jd (I-form). *(Ajuste da tarefa 5: com "RB 2 jd atrás do QB" e FB a 3 jd, RB e FB ficavam no mesmo ponto no I-form, e o QB a 1 jd ficava em cima do C.)*
  - A bola fica no hash (`starting_hash` do FTN, quando existe; senão, no meio).
- **Defesa:**
  - DL a 1 jd, alinhada aos gaps.
  - LB a 4,5 jd, dentro do box.
  - CB espelhando os WRs a 6 jd.
  - S a 12 jd.
  - Os defensores contados em `box` ficam a até 7 jd e a até 5 jd da bola para os lados (`BOX_PROF`, `BOX_LARG`). Se o `box` passa de DL + LB, os safeties (depois os CBs) mais perto da bola descem a 6 jd; se fica abaixo, os LBs (depois a DL) mais abertos saem para fora do box.
  - **Listas da fonte:** posições trocadas (DL bloqueando no ataque, WR na defesa) viram o papel mais próximo; 10 ou 12 jogadores são desenhados como vieram; o "DB" de 2021–22 é dividido em CB e S pela quantidade. Jogadas com lista, mas sem formação (chutes), dão `None`.
- **Sem lista de jogadores (2026):** o ataque é montado com 5 OL, QB, `n_offense_backfield` RBs e o resto em WR, e a defesa com `box` jogadores na frente e o resto atrás, **sem nomes nem números**, e com `generico: true` (4.4).

### 5. `server/data_layer.py` (reescrito sobre as tabelas)

**Responsabilidade:** responder às rotas atuais a partir das tabelas das 6 temporadas.
**Atende aos requisitos:** 1–5, 8.3

- **O formato das respostas é o mesmo de hoje**, para as telas atuais funcionarem (Requisito 8). Campos que deixam de existir (velocidade de pico, tempo até a pressão por tracking) saem das respostas, e o front esconde o bloco correspondente.
- **`season` em todas as rotas de listagem**; sem ele, vale a temporada atual.
- **`gameId` continua numérico** (o `old_game_id`, como `2025090400`, é único entre temporadas). **O id de jogador passa a ser o gsis (`00-0033077`)**, e a rota `/api/players/{id}` aceita `[0-9A-Za-z-]+`.
- `/tracking` passa a devolver o **esquema de 1 quadro**, e `/formation` o mesmo esquema no formato de hoje.
- `insights` e `notes` (sugestões táticas e bastidores) vão como listas vazias: eles saem de vez na `novo-visual`, e aqui não vale portá-los.

### 6. `server/serve.py`

**Responsabilidade:** rotas com `season`, a atualização diária em segundo plano e a troca segura dos dados.
**Atende aos requisitos:** 7.1–7.6, NFR 2

```python
def atualizar(forcar_subida: bool) -> None
    # fontes.sincronizar -> montar -> NFLData novo -> troca DATA -> CACHE.limpar() -> aquecer
```

- A troca é atômica: `DATA` é uma referência só, e cada requisição pega a sua no início.
- O `CacheDeRespostas` ganha `limpar()`.
- `/api/meta` ganha `ultimaAtualizacao`, a lista de `fontes` com os créditos (9.1) e as temporadas e semanas disponíveis, com os nomes das rodadas de playoff.

**Como ficou (tarefa 6):**
- **Subida:** sem cópia montada, sincroniza e monta **antes** de servir, com o progresso no terminal; sem internet nesse caso, mensagem e código 1 (7.6). Com cópia local, **sobe na hora** e a busca por dados novos (7.1) roda em segundo plano 1 s depois, e a partir daí a cada 24 h (7.2). Assim a subida não depende da rede (NFR 2: ~3–4 s).
- `montar.sincronizar_e_montar()` é o ciclo único (subida, atualização diária e `python etl/montar.py`), incluindo baixar de novo os brutos de uma temporada que precise ser remontada.
- **`--offline`** (`fontes.SemAcesso`): o mesmo caminho de "sem internet", sem tocar na rede. Os testes e as ferramentas (`tools/`) sobem o servidor assim, porque a API do GitHub só permite 60 chamadas por hora.
- **Troca sem resposta velha:** cada `NFLData` tem uma `versao`, que entra na chave do cache; e `limpar()` começa uma nova geração, em que o que estava sendo montado com os dados antigos não é guardado. Uma requisição que pegou os dados antigos pouco antes da troca termina com eles, mas nunca grava nem lê a resposta dos novos.
- **`/api/games` não entra no cache:** o status (`agendado`, `sem_resultado`, `encerrado`) depende do relógio. As contagens por jogo são pré-calculadas na carga (~2 ms por semana).
- **Memória:** as tabelas grandes ficam com o texto como categoria, e do `jogador_jogo` só as colunas usadas: ~290 MB para as 6 temporadas, ~500 MB de pico no teste de carga. Na troca diária, os dois conjuntos convivem por alguns segundos e continuam abaixo de 1 GB (NFR 5).
- **Formato das respostas:** o mesmo de antes, com as adições `season`, `gameType`, `rodada`, `kickoffUtc`, `status`, `espnId` e `plays` no cartão de jogo; `playType`, `epa`, `hasFormation`/`semFormacao` no cartão de jogada; `baseReduzida`, `seasons`, `foto`, `minimo`/`volume` e `motivo` do eixo no perfil; `formacao`, `ilustrativo` e `generico` na prancheta. Até a tarefa 7, ficam também `hasTracking` (= `hasFormation`) e `dataset` (sem avisos), que o front atual lê.

### 7. Frontend atual: adaptações mínimas (`app/js/app.js`)

**Responsabilidade:** manter as 4 telas atuais funcionando com os dados novos.
**Atende aos requisitos:** 6, 8, 9, 10, S.1, S.4

- Seletor de temporada acima das semanas; chips de playoff com os nomes das rodadas.
- Cartão de jogo: `agendado` mostra data e horário, `sem_resultado` mostra o aviso, e o **placar ao vivo** vem do módulo `aoVivo` (fluxo acima).
- **Matéria do jogo** na Home, abaixo da partida selecionada: título, data, fonte e link, **só se o link for `https://*.espn.com/`** (S.4). Links `http://` passam para `https://`.
- Prancheta: um aviso "Esquema ilustrativo: posições-modelo da formação"; os controles de animação ficam ocultos quando `frameCount == 1`.
- Blocos sem dado (velocidade, insights, bastidores) ficam ocultos, em vez de mostrar "—" ou "0".
- "Sobre os dados": fontes, créditos e a hora da última atualização.

> **Teste de corte aplicado:**
> - (a) **Next Gen Stats** como fonte: cortado. O CPOE já vem nas estatísticas por jogador, e os NGS só cobrem quem passa dos mínimos da NFL.
> - (b) Um **proxy no servidor para a ESPN**: cortado, porque a ESPN bloqueia chamadas de servidor.
> - (c) Uma **biblioteca cliente do nflverse** (`nflreadpy`): cortada, porque traria o `polars` como dependência para fazer o que 8 downloads diretos já fazem.

---

## Data Model

```
dados/                         (não versionado; ~100–150 MB com a economia abaixo)
├─ manifest.json               {arquivo: {updated_at, size, baixadoEm, descartado}}, ultimaSincronizacao
├─ brutos/{release}/{arquivo}  cópias validadas: só da temporada atual + calendário e jogadores
├─ jogos.npz                   TODAS as temporadas (do calendário; refeito quando ele muda, ~diário)
├─ jogadores_bio.npz           bio, foto e posição atual (de players.csv)
└─ temporadas/{ano}/           jogadas.npz · jogador_jogo.npz · jogadores.npz · origem.json
                               (origem.json = assinaturas dos brutos da temporada: refaz se mudarem)
```

**Economia de espaço (decidida pelo José em 2026-09-25, depois da primeira sincronização real: 330 MB brutos):**
- Depois que uma **temporada encerrada** (anterior à atual) é montada, os brutos dela são **apagados**, e o manifesto marca `descartado: true` com o `updated_at`/`size` de referência.
- A sincronização não baixa de novo um arquivo descartado, **a menos que o nflverse o republique** (uma correção muda o `updated_at`). Nesse caso ele é baixado, a temporada é remontada e o bruto é descartado de novo.
- Por isso o **calendário** e a **bio** saíram das pastas por temporada: o calendário muda todo dia (placar da temporada atual), e não dá para remontar as temporadas encerradas sem os brutos delas.
- A temporada atual continua com os brutos e é atualizada todo dia.

**Migração necessária:** sim, mas só de descarte. `cache/` (métricas do dataset) e `nfl-big-data-bowl-regional-event-data-main/` deixam de ser lidos. **Apagar o dataset do repositório** (826 MB versionados) fica para o José decidir (Q-D1).

---

## Error Handling

| Falha | Detecção | Resposta | Requisito |
|---|---|---|---|
| Jogo ainda não disputado | `status == agendado` | "a jogar", com data e horário, sem placar | 1.4 |
| Jogo disputado sem dados na fonte | sem placar em `schedules` | "resultado ainda não disponível" | 1.5 |
| A matéria da ESPN e o nflverse divergem no placar | comparação no navegador | vale o nflverse; `console.warn` (não há como logar no servidor a partir da ESPN) | 2.4 |
| Jogada sem formação | colunas de formação vazias | na lista, "sem dados de formação"; na prancheta, "formação indisponível" | 3.4, 4.5 |
| Formação sem lista de jogadores (2026) | `jogadores` vazio | esquema genérico (`generico: true`) | 4.4 |
| Jogador abaixo do mínimo | volume < mínimo × jogos | rating `n/d` | 5.4 |
| Estatística do eixo inexistente | coluna ausente ou toda vazia | eixo com `percentile: null` e `motivo` | 5.5 |
| Comparar funções diferentes | grupos diferentes | recusa com mensagem, como hoje | 5.6 |
| Matéria indisponível | fetch falha ou `article` ausente | o bloco some | 6.3 |
| Fonte fora do ar ou sem internet | exceção de rede | segue com a cópia local e loga | 7.5 |
| Primeira subida sem internet e sem cópia | `SemDados` | mensagem no terminal e sai com código 1 | 7.6 |
| Limite da API do GitHub | HTTP 403/429 com `X-RateLimit-Remaining: 0` | tratado como "sem internet" até a próxima janela | 7.5 |
| Placar ao vivo indisponível | fetch falha | último placar + "atualização ao vivo indisponível"; nova tentativa em 30 s | 10.5 |
| Arquivo baixado sem as colunas esperadas | validação de `Fonte.colunas` | descarta o arquivo, mantém o anterior, loga | S.2 |
| Link de matéria fora da ESPN | `new URL(href).hostname` não termina em `espn.com` | o link não é exibido | S.4 |
| Texto externo com HTML | — | `esc()` em todo texto, como hoje | S.1 |

---

## Segurança

- **Entrada externa:** todo texto das fontes passa por `esc()` no navegador. O servidor nunca monta HTML.
- **Integridade:** a validação de colunas e tipos é feita **antes** de substituir a cópia boa; a gravação é atômica.
- **Destinos:** o servidor só acessa os dois domínios do nflverse listados. O navegador só acessa `site.api.espn.com`, e só exibe links de `*.espn.com`.
- **Licenças:** crédito ao nflverse (CC-BY-4.0) e à ESPN/AP na tela "Sobre os dados" e junto de cada matéria.

---

## Testing Strategy

| Nível | O que cobre | O que é simulado |
|---|---|---|
| Unitário | `fontes`: baixa só o que mudou, rejeita arquivo sem coluna, mantém a cópia boa, trata limite de API e falta de rede. `prancheta`: posições por formação, esquema genérico, sem formação → None. `ratings`: mínimos proporcionais, percentil por grupo, eixo ausente, `baseReduzida` na OL | um servidor HTTP local de teste fazendo o papel do GitHub (releases + arquivos pequenos) |
| Integração (dados reais) | 6 temporadas carregadas; **placar oficial = soma dos pontos do play-by-play** em todos os jogos; TB × DAL 2021 = 29–31; playoffs presentes com os nomes das rodadas; todas as jogadas (corridas incluídas) | nada; usa a cópia baixada |
| Navegador (Playwright) | seletor de temporada; "a jogar" e "sem resultado"; placar ao vivo (liga, atualiza, para, falha); matéria (aparece, some, link fora da ESPN barrado); prancheta com aviso ilustrativo; telas antigas sem campos vazios | ESPN simulada com `page.route()` (estados `pre`, `in`, `post` e erro) |
| Desempenho | `bench.py` e `carga.py --usuarios 10` na semana mais recente disputada; subida ≤ 10 s; memória ≤ 1 GB | nada |
| Regressão | `golden.py`: **recapturado** ao fim desta spec, como a nova base | — |

**Critério de pronto:** todo critério do requirements tem um teste nomeado no `tasks.md`.

---

## Decisões e alternativas descartadas

### Decisão 1: arquivos do nflverse baixados e processados localmente

**Alternativas consideradas:** consultar uma API a cada requisição (ESPN, SportsDataIO); a biblioteca `nflreadpy`.
**Escolha:** baixar os arquivos das releases e montar tabelas locais.
**Motivo:**
- dá para funcionar sem internet (7.5);
- as metas de desempenho (ms) seguem valendo, o que seria impossível consultando a internet a cada clique;
- o nflverse é aberto (CC-BY) e atualizado diariamente;
- sem dependência nova.

**Custo aceito:** ~500 MB em disco e um atraso de até 24 h nas jogadas da temporada atual (o placar ao vivo cobre o dia do jogo).

### Decisão 2: a ESPN direto no navegador

**Alternativas consideradas:** um proxy no servidor.
**Escolha:** `fetch` no navegador.
**Motivo:** a ESPN responde 403 a chamadas de servidor (testado) e libera CORS para o navegador.
**Custo aceito:** depende de uma API não oficial. Se ela mudar, o placar ao vivo e a matéria somem (com aviso), e o resto do app não é afetado.

### Decisão 3: a prancheta sem movimento reusa o `/tracking` com 1 quadro

**Alternativas consideradas:** uma rota nova e um componente novo de desenho.
**Escolha:** o mesmo formato de `/tracking`, com `frameCount = 1` e `ilustrativo = true`.
**Motivo:** o `Field` atual desenha sem mudança, e a `novo-visual` vai redesenhar a prancheta de qualquer forma.
**Custo aceito:** o nome da rota fica enganoso (`tracking` sem tracking). Ela será renomeada na `novo-visual`.

### Decisão 4: o id de jogador passa a ser o gsis

**Alternativas consideradas:** criar um id numérico próprio.
**Escolha:** o `gsis_id` (`00-0033077`).
**Motivo:** é o id comum a todas as fontes (play-by-play, estatísticas, participação e, pela ponte, o PFR). Um id próprio seria mais uma tabela de conversão para manter.
**Custo aceito:** a rota de jogador passa a aceitar texto, e o front deixa de converter o id com `Number()`.

### Decisão 5: o golden é recapturado, não comparado

**Contexto:** o golden provava que "nenhum número mudou". Aqui os números **devem** mudar (placar oficial, jogadas completas, ratings novos).
**Escolha:** recapturar ao final desta spec, como a nova base. Durante a spec, a correção vem dos testes de integração contra as fontes (a soma dos pontos, o placar do TB × DAL, a contagem de jogadas).
**Custo aceito:** durante a spec não há a rede de segurança de "tudo igual". Ela volta a existir a partir da recaptura.

---

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| O nflverse muda o nome ou as colunas de um arquivo | alto | validação de colunas antes de trocar a cópia (S.2); o app segue com a cópia anterior e o log aponta o arquivo |
| A ESPN bloqueia ou muda a API | médio | afeta só o placar ao vivo e a matéria; os dois somem com aviso |
| As fórmulas dos ratings geram rankings estranhos (ex.: um OLB que é pass rusher avaliado como LB) | médio | conferência na tarefa de ratings com nomes conhecidos por temporada (os 10 melhores de cada grupo), com o José validando antes de fechar |
| A participação de 2026 só sai depois da temporada | baixo | já coberto: esquema genérico pelo FTN (4.4) |
| A memória com 6 temporadas passa de 1 GB | médio | só as colunas usadas; texto como categoria; medido na tarefa de carga |
| As telas antigas quebram com o id de jogador em texto | médio | teste de navegador de cada tela na tarefa do front |

---

## Aprovação

- [x] Todo requisito do requirements.md está atendido por algum componente
- [x] Nenhum componente existe sem requisito que o justifique
- [x] Todo SE...ENTÃO aparece na tabela de erros
- [x] Pelo menos um componente foi cortado na revisão (NGS, proxy da ESPN, nflreadpy)
- [x] Decisões relevantes registradas com alternativa descartada
- [x] **Q-D1:** apagar do repositório a pasta do dataset do Big Data Bowl (826 MB)? **Sim.** Sai do versionamento (os arquivos continuam no disco e no histórico) e entra no `.gitignore`.

**Aprovado por:** José Cota em 2026-09-25, incluindo os eixos e mínimos dos ratings. A validação final dos rankings, com nomes, é feita na tarefa de ratings.
