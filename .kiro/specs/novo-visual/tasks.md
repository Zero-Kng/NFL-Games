# Implementation Plan

**Feature:** novo-visual
**Status:** em execução (v0.4 aprovada em 2026-09-26). Pausada em 2026-09-25; retomada sobre a `dados-externos`.

> **Por que pausou:** o José esclareceu a meta: uma repaginação total, com **todos os dados vindo de APIs**. Decisões tomadas na mesma data:
> - **Dados primeiro, visual depois:** a spec `dados-externos` vem antes, e esta é retomada em cima dos dados novos.
> - **Prancheta sem movimento**, desenhada a partir de dados públicos de formação (não há tracking x/y em API aberta).
> - **Ratings recalculados** com estatísticas públicas (não mais PFF).
> - **Temporadas:** a atual (2026) mais as recentes (2021–2025).
>
> **Impacto:** os Requisitos 7 (notícias), 10 (movimento contínuo da prancheta), 3 (temporadas) e 6 (ratings) terão de ser revistos ao retomar. A tarefa 1 tinha só código não testado, gerado a partir do dataset; ele foi retirado da branch e guardado como referência.
>
> **Retomada (v0.4, 2026-09-26):** revistos com o José (Q6–Q9 no requirements): notícias com tipos novos sobre o placar oficial; o Requisito 10 saiu; Configurações com 2 controles; matéria da ESPN no topo da página Jogo. As tarefas abaixo já estão ajustadas. A branch `spec/novo-visual` foi avançada até a `main` com a `dados-externos`.
**Data:** 2026-09-25

> Regras desta execução:
> - **Branch:** `spec/novo-visual`, criada pelo José antes da tarefa 1. **Um commit por tarefa** (decisão do José em 2026-09-26) e, ao final, uma PR (mensagem e descrição preparadas pelo Claude, sem linha de coautoria).
> - **O app atual continua funcionando até a tarefa 9.** A interface nova é montada em `app/novo.html` + `app/js/*.js`, ao lado do `index.html`/`app.js` atuais. Só na tarefa 9 ela vira o `index.html` e o código antigo sai. Assim, toda tarefa é verificável sem quebrar o que existe, e os testes da spec anterior seguem valendo até a troca.
> - **Toda tarefa que mexe no servidor** termina com `golden.py check` 100% e `pytest` passando.
> - **Toda tarefa de tela** termina com os testes dela passando e uma captura de tela comparada com o rascunho.
> - **"Mover, não reescrever":** as funções do `app.js` que vão para as telas novas mantêm a lógica; muda o HTML e as classes.

---

## Tarefas

- [x] 1. Gerar as notícias e o resumo no servidor
  - [x] 1.1 `NFLData.news(season, week=None)` em `data_layer.py`, conforme o design (componente 2): resultado (todo jogo, com o vencedor pelo placar oficial), virada de 10+ pontos, prorrogação, goleada de 28+, maior jogada da semana (só a 1ª), grande atuação (400+ jd de passe, 5+ TD de passe, 175+ jd correndo ou recebendo, 4+ TD, 3,5+ sacks) e defesa (6+ sacks ou 3+ interceptações de um time). "Incomum" como percentil na temporada, calculado uma vez por temporada. Texto montado só com números do dado.
  - [x] 1.2 `NFLData.summary(season)` → `{ratedPlayers, season}`.
  - [x] 1.3 Rotas `GET /api/news` (`season` e `week` opcionais) e `GET /api/summary` (`season` opcional) em `serve.py`; as da temporada atual entram no aquecimento.
  - [x] 1.4 Caminho infeliz: semana sem jogos disputados → `[]`; `week` ou `season` não numérico → 400; temporada inexistente → 404 (validação atual).
  - [x] 1.5 Testes em `tests/test_news.py`, incluindo: toda semana disputada de 2021–2025 com pelo menos 1 notícia e no máximo 40; o resultado bate com o placar oficial; o golden continua passando.
    - A geração fica em `server/noticias.py` (o `data_layer` só guarda o resultado por temporada, calculado na 1ª vez: ~145 ms). `/api/summary`, `/api/news` e `/api/news?week={semana atual}` entram no aquecimento.
    - `tests/test_news.py`: 17 testes. Os limiares, o placar e a maior jogada são conferidos recalculando direto das tabelas; TB 31 x 29 DAL (2021) sai "TB vence DAL por 31–29". Golden 2.116/2.116; suíte com 169 testes.
  - _Requisitos: 4.3, 7.1, 7.3, 7.6, NFR 2_

- [x] 2. Montar a casca da interface nova
  - [x] 2.1 `app/novo.html` com o cabeçalho (menu, escudo, título, busca), os filtros de temporada e semana, a barra inferior com 4 destinos e o menu lateral (4 destinos + Sobre os dados + Configurações), no HTML do rascunho.
  - [x] 2.2 `app/css/novo.css` com os tokens e componentes do rascunho, sem os padrões apontados pelo verificador de design (borda lateral no item ativo, ponto pulsante, texto < 12 px, sombra com brilho).
  - [x] 2.3 `js/api.js` e `js/ui.js`: `get()` (LRU e dedupe; `games()` fora do cache), `ultimo()`, `into()` e os formatadores (incluindo `inicioLocal` e `dataHora`), **extraídos** do `app.js`.
  - [x] 2.4 `js/main.js`: estado `S`, `ir()`, `selecionarJogo()`, menu lateral (abre, fecha com Esc e com toque fora), filtros de temporada e semana vindos de `meta.seasons` (rodadas de playoff pelo nome; padrão: a semana mais recente já começada), deep link `?season=&week=&game=&screen=`, rotas legadas (`?screen=coach|commentator|scout`) e boot. As telas ainda são esqueletos.
  - [x] 2.5 `js/config.js` (Requisito 11, sem a tela ainda): `ler`, `gravar`, `aoMudar`, `reduzirMovimento`, com padrões se o `localStorage` falhar.
  - [x] 2.6 Fontes com `preload` sem bloquear (mesmo mecanismo do `index.html` atual).
  - _Requisitos: 1.1–1.5, 2.1–2.6, 3.1–3.5, 11.5_
  - **Feito (2026-09-26):** `app/novo.html`, `app/css/novo.css`, `app/js/{api,ui,config,main}.js`. As 6 telas são esqueletos registrados em `TELAS` (main.js); cada tarefa seguinte troca o `render` da sua tela.
    - Ajustes do rascunho contra o verificador: item ativo do menu com fundo e ícone vermelho (sem borda lateral), escudo com borda em vez de halo, nenhum texto abaixo de 12 px, chips e itens com 44 px. Ícones de estado em SVG (sem emoji).
    - Filtros por tela: Início e Notícias usam temporada e semana; Jogadores só temporada; Jogo, Configurações e Sobre, nenhum. A URL acompanha o estado (`?season=&week=&game=&screen=&aba=`).
    - `serve.py` passa a servir `.js` sempre como `text/javascript` (módulos ES; o registro do Windows às vezes diz `text/plain`).
    - Verificador de design: só o aviso da fonte Inter, que é a exceção já registrada em `rascunho/.impeccable/config.json`.
    - **Decidido na tarefa 3 (José, 2026-09-26):** o rótulo curto (tag/kicker) que o rascunho punha acima do título das notícias sai; o tipo vai no rodapé, junto com o jogo ("[BAL] × [LV] · Virada"). Vale também para a lista da tarefa 7.
    - `tests/test_ui_novo.py`: 24 testes (1.1–1.5, 2.1–2.3, 2.5, 2.6, 3.1, 3.2, 3.5, 11.5 e filtros por tela). Suíte: 193.

- [x] 3. Tela Início
  - _Depende de: 1, 2_
  - [x] 3.1 Carrossel com as 4 primeiras notícias da semana (slides do rascunho), com os pontos de navegação. Avança sozinho a cada 5 s, pausa com o mouse em cima ou durante o toque, e não avança com movimento reduzido ou com o avanço desligado nas Configurações. Semana sem notícias oculta o carrossel.
  - [x] 3.2 Dois cartões: partidas na semana (`games(week).length`) e jogadores avaliados (`summary.ratedPlayers`).
  - [x] 3.3 Lista de jogos da semana (cartão de partida do rascunho), com os estados e o placar ao vivo **movidos** da `dados-externos` (`gameCard`, `estadoDoJogo`, `aoVivo`). Tocar abre a página Jogo com a partida. Filtro por time vindo da busca, com chip "TIME ×".
  - [x] 3.4 Caminho infeliz: erro ao carregar a semana mostra a mensagem na lista, e os filtros continuam utilizáveis.
  - _Requisitos: 3.3, 3.4, 4.1–4.8, 7.4, 7.5_
  - **Feito (2026-09-26):** `app/js/telas/inicio.js` (registrado em `TELAS.inicio`) e os componentes do Início em `novo.css`.
    - Slide: título, texto e rodapé com os escudos dos dois times e o tipo (7.2). Sem rótulo acima do título (decisão acima). Os tons vermelho e azul ficaram um pouco mais escuros que no rascunho para o texto branco passar de 4,5:1.
    - Carrossel: avança a cada 5 s; pausa com o mouse em cima, durante o toque e com o foco dentro; tocar num ponto recomeça a contagem. Parado com movimento reduzido ou com o avanço desligado, e volta na hora quando a configuração muda (`aoMudar`). Pontos com área de toque de 28 × 44 px.
    - Cartões: "Partidas na semana" rola até a lista; "Jogadores avaliados" abre Jogadores.
    - `estadoDoJogo`, `gameCard`, `relogioAoVivo` e `aoVivo` **movidos** do `app.js` com a mesma lógica; o cartão virou `<button>` (teclado sem código extra). `S.live`/`S.liveFalha` foram para o `S` do `main.js`.
    - `ir()` chama `sair()` da tela anterior: fora do Início, o carrossel e o placar ao vivo param.
    - Filtro por time: `filtrarPorTime(abbr)` (a busca da tarefa 7 vai chamar), chip "TIME ×", e o filtro continua ao trocar de semana. Semana sem jogo do time: "{time} não joga nesta semana."
    - Verificador de design: as linhas de jarda do slide (do rascunho) foram registradas como exceção em `.impeccable/config.json`; fora isso, limpo.
    - `tests/test_ui_novo.py`: +24 testes (4.1–4.8, 3.3, 3.4, 7.2, 7.4, 7.5, S.1 no carrossel, filtro por time e os 7 testes de cartão e ao vivo da `test_ui_dados.py` adaptados). Suíte: 217.

- [x] 4. Página Jogo: cabeçalho, abas e conteúdo movido
  - _Depende de: 2_
  - [x] 4.1 Cabeçalho da partida (placar, times, semana) e 5 abas: Prancheta, Jogadas, Replay, Estatísticas, Playbook. A aba, a partida e a jogada ficam em `S`.
  - [x] 4.2 **Mover** para `js/telas/jogo.js`: `coachLineup`, `loadFieldPlay`, `prefetchVizinhas`, `ensurePlays`, `playRow`, `coachPlays`, `coachStats`, `coachBook`, `renderBroadcast`, `paintBc` e os controles do replay, com o HTML no visual novo e os contadores `seq` preservados.
  - [x] 4.3 Tocar numa jogada em Jogadas ou em Replay abre a Prancheta com ela.
  - [x] 4.4 Caminho infeliz: sem partida escolhida, abre a 1ª da semana; jogada sem formação mostra os dados da jogada e "formação indisponível para esta jogada".
  - [x] 4.5 Matéria da ESPN logo abaixo do placar da página Jogo: **mover** `renderMateria`, `linkEspn` e `conferirPlacar` (só `*.espn.com`, `http`→`https`, some sem matéria).
  - _Requisitos: 5.1–5.9_
  - **Feito (2026-09-26):** `app/js/telas/jogo.js` (registrado em `TELAS.jogo`) e os componentes da página em `novo.css`.
    - Ordem da página: cabeçalho da partida (placar, times, rodada, temporada e estádio), matéria da ESPN, abas e o conteúdo da aba. Abas com `role="tab"` e setas do teclado; a aba ativa rola para a vista.
    - Funções **movidas** com a mesma lógica e os mesmos contadores `seq`: `ensurePlays`, `coachLineup`, `loadFieldPlay`, `prefetchVizinhas`, `playMetaHTML`, `playRow`, `coachPlays`, `coachStats`, `coachBook`, `renderBroadcast`, `paintBc`, os controles do replay, `renderMateria`, `linkEspn` e `conferirPlacar`. O que foi carregado da partida (jogo, jogadas, replay) fica guardado até trocar de partida; `sair()` para o replay e descarta a prancheta em voo.
    - Jogadas e itens da narração são `<button data-play>`: tocar abre a Prancheta com a jogada (5.5). A jogada vai para a URL (`&play=`), que o boot já lia.
    - **Decisões (Claude):**
      - O `Field` foi movido já nesta tarefa para `js/prancheta.js`, porque a aba Prancheta precisa dele; a tarefa 5 fica com a passada de visual. Três ajustes no movido: os ids de jogador agora são texto, e o `Number(k) === sel` antigo nunca batia (o jogador tocado não ficava destacado); os números de jarda passaram de 11 para 12 px; o quadrado da defesa virou classe (`.def`).
      - Sem os controles de animação da prancheta: toda formação tem 1 quadro (`frameCount` = 1), então eles já ficavam sempre ocultos. `Field.play/pause` continuam no arquivo; a tarefa 5 decide.
      - A narração do replay traz um emoji como ícone (da API, que não muda); a tela nova não mostra o emoji e usa o tom da jogada como cor do marcador.
      - O Replay já usa a velocidade das Configurações (1,4 s ÷ velocidade) e troca na hora com `aoMudar`; a tela de Configurações continua na tarefa 8.
    - `tests/test_ui_novo.py`: +17 testes (5.1–5.9, a velocidade do Replay e os testes de matéria da `test_ui_dados.py` adaptados, incluindo "jogo a jogar não consulta a ESPN"). Suíte: 234. Verificador de design: limpo.

- [x] 5. Prancheta no visual novo
  - _Depende de: 4_
  - [x] 5.1 `js/prancheta.js`: `Field` **movido** do `app.js` como está (esquema de 1 quadro, aviso "Esquema ilustrativo", sem controles de animação), com o visual novo. Sem interpolação: o antigo Requisito 10 saiu (Q7).
  - _Requisitos: 5.3, 5.8_
  - **Feito (2026-09-26):** o `Field` já tinha sido movido na tarefa 4; aqui ficou a passada de visual e o que sobrou do movimento.
    - Saíram `play`, `pause`, `toggle`, `setSpeed`, `clockAt` e `onFrame`: sem tracking, toda formação tem 1 quadro (Q7).
    - **Cores dos lados:** cada lado usa a primária do seu time; se as duas forem parecidas, a defesa usa a secundária do time dela (`coresDosLados`). SEA e NE, por exemplo, são o mesmo azul-marinho (`#002244`) e ficavam idênticos no campo. Em fundo claro (secundárias douradas ou prateadas), o número do jogador fica escuro.
    - **Legenda:** diz quem ataca e quem defende ("TB · ataque", "DAL · defesa"), com a cor e o formato (círculo e quadrado) de cada lado.
    - Rótulos das jardas afastados das linhas laterais (antes ficavam em cima delas); o ponto sob o mouse ou com foco vem para a frente (na linha, os números se sobrepõem); texto do ponto em 12 px.
    - Posição genérica (2026, a fonte ainda sem os jogadores): o rótulo diz "Posição genérica · OL · ataque", e o cartão não leva a um perfil.
    - `tests/test_ui_novo.py`: +4 testes (esquema de 1 quadro sem controles, jogador tocado destacado, posições genéricas com as cores dos lados, `coresDosLados`). Suíte: 238. Verificador de design: limpo.

- [x] 6. Tela Jogadores
  - _Depende de: 2_
  - [x] 6.1 **Mover** `scoutList`, `scoutDetail`, `radarBlock`/`radarSVG`, `fillComparePicker` e `showCompare` para `js/telas/jogadores.js`, no visual novo (lista no estilo `row-card` do rascunho).
  - [x] 6.2 Seção "Jogadores a observar" com `game.watch` da partida selecionada, atualizada ao trocar de partida e oculta se vazia.
  - _Requisitos: 6.1–6.4_
  - **Feito (2026-09-26):** `app/js/telas/jogadores.js` (registrado em `TELAS.jogadores`) e os componentes em `novo.css`.
    - "A observar" no topo: cartões com rolagem lateral (escudo, rating, nome, posição e grupo), com o link "DAL @ TB" para a partida. Tocar num cartão abre o perfil.
    - Lista no `row-card` do rascunho (posição no ranking, nome, posição · time · grupo · snaps · jogos, rating); busca pelo nome (280 ms de espera, 100 caracteres) e filtro por posição em chips. Ao voltar do perfil, a busca e o filtro continuam.
    - Perfil: cabeçalho com avatar da posição, rating e dados físicos; radar, números da temporada, onde se alinha, jogo a jogo e comparação. O perfil vai para a URL (`&jogador=`), e o boot o lê. `abrirJogador(id)` fica exportada para a busca da tarefa 7; o jogador tocado na prancheta também abre o perfil.
    - Funções **movidas** com a mesma lógica; os contadores `seq.scout` viraram `ultimo('scout')` (e `ultimo('comparar')` na comparação, que antes não descartava resposta atrasada).
    - **Decisões (Claude):**
      - Sem partida escolhida, "A observar" usa a 1ª partida da semana, como a página Jogo (5.7), sem mudar a partida selecionada.
      - Radar no tema escuro: rótulos em 13 px, e os longos em duas linhas ("Jardas por / tentativa") para caberem sem encolher o radar nem a fonte.
      - O código das abas de função do perfil (`data-role`) não veio: o `scoutDetail` antigo já não as desenhava.
    - `tests/test_ui_novo.py`: +8 testes (6.1–6.4, temporada, primeira da semana, prancheta → perfil e perfil por link). Suíte: 246. Verificador de design: limpo.

- [x] 7. Notícias e busca geral
  - _Depende de: 1, 2_
  - [x] 7.1 Tela Notícias: `news(week)` no estilo `news-item` do rascunho; tocar abre a página Jogo; mensagem para semana vazia.
  - [x] 7.2 Busca: a lupa abre o campo com o cursor nele. Os resultados vêm em 3 grupos: Times (de `meta.teams`), Jogadores (`/api/players?q=&limit=8` com `ultimo("busca")`) e Notícias (de `/api/news`, todas as semanas). O termo é cortado em 100 caracteres. Tocar num resultado leva ao destino. "Nada encontrado para "…"". Cancelar ou Esc fecha e limpa.
  - _Requisitos: 7.2, 7.5, 7.6, 8.1–8.6, S.2_
  - **Feito (2026-09-26):** `app/js/telas/noticias.js` (registrado em `TELAS.noticias`) e a busca em `main.js`, como no design.
    - Notícias: `news-item` do rascunho (quadrado com o número em destaque, título, texto) e, no rodapé, os escudos dos dois times e o tipo, como decidido na tarefa 3. A contagem e a semana ficam ao lado do título.
    - Busca: Times filtrados de `meta.teams` (sigla, nome e apelido, sem diferença de acento e maiúscula; até 5); Jogadores de `/api/players?q=&limit=8` depois de 200 ms sem digitar, com `ultimo("busca")`; Notícias de `/api/news?season=` (a temporada inteira, do cache; até 6). Enquanto os jogadores chegam, o grupo mostra "Buscando jogadores…"; "Nada encontrado" só aparece com as três listas vazias.
    - Destinos: o time abre o Início filtrado (chip "TIME ×", da tarefa 3); o jogador abre o perfil (`abrirJogador`, da tarefa 6); a notícia abre a página Jogo. Fechar a busca descarta a resposta que ainda estiver a caminho.
    - **Decisão (Claude):** a notícia também é encontrada pelo nome e pelo apelido dos times dela, porque a manchete usa só a sigla ("TB vence DAL"): sem isso, "buccaneers" não achava nenhuma notícia do TB.
    - `tests/test_ui_novo.py`: +11 testes (7.1, 7.2, 7.5, 7.6, troca de semana, 8.1–8.6 com o `fetch` embrulhado da spec anterior no 8.5, S.2 e o termo escapado no "Nada encontrado"). Suíte: 257. Verificador de design: limpo.

- [x] 8. Configurações e Sobre os dados
  - _Depende de: 2, 4_
  - [x] 8.1 Tela Configurações: avanço automático das notícias (liga/desliga) e velocidade do Replay narrado (0,5×, 1× ou 2×), aplicados na hora via `aoMudar`.
  - [x] 8.2 Tela Sobre os dados com `meta.fontes` (fontes e créditos das licenças) e `meta.ultimaAtualizacao`: **mover** o `renderSobre` da `dados-externos`.
  - _Requisitos: 2.3, 11.1–11.4_
  - **Feito (2026-09-26):** `app/js/telas/extras.js` (`renderConfig` e `renderSobre`, registrados em `TELAS`). Com isso, nenhuma tela é mais esqueleto: saíram o `esqueleto()` do `main.js` e o ícone "obra".
    - Configurações: um interruptor (`role="switch"`) para o avanço das notícias e um grupo de 3 opções (`role="radiogroup"`, com setas) para a velocidade do Replay. Cada toque grava e vale na hora pelo `aoMudar`, que o carrossel (tarefa 3) e o Replay (tarefa 4) já escutavam. Com movimento reduzido no sistema, uma nota avisa que o carrossel fica parado.
    - Sobre os dados: `renderSobre` movido, com as fontes em cartões (nome, crédito da licença e para que é usada), a última atualização e o "como ler" (prancheta ilustrativa, ratings por grupo e notícias geradas dos dados).
    - Sem título repetido: o cabeçalho já diz "Configurações" e "Sobre os dados".
    - `tests/test_ui_novo.py`: +6 testes (11.1–11.4, a nota de movimento reduzido e o "Sobre" da `test_ui_dados.py`, adaptado). Suíte: 263. Verificador de design: limpo.

- [ ] 9. Trocar a interface e remover o código antigo
  - _Depende de: 3, 4, 5, 6, 7, 8_
  - [ ] 9.1 `novo.html` vira `index.html`; saem o `app.js` e o `app.css` antigos. `tests/test_ui.py` e `tests/test_ui_dados.py` passam a rodar sobre as telas novas (ao vivo, matéria, prancheta e "Sobre" continuam cobertos).
  - [ ] 9.2 Conferir que "Sugestões de tática", "Bastidores", "Treinador", "Olheiro" e "Comentarista" não aparecem em nenhuma tela.
  - [ ] 9.3 Passada de acessibilidade: alvos ≥ 44 px, contraste ≥ 4,5:1, uso completo pelo teclado com foco visível, e todo texto dos dados passando por `esc()`.
  - _Requisitos: 2.4, 9.1, 9.2, NFR 3–5, S.1_

- [ ] 10. Verificação final e documentação
  - _Depende de: 9_
  - [ ] 10.1 `golden.py check`, `pytest` (incluindo os testes adaptados da spec anterior), `bench.py --check` e `carga.py --usuarios 10 --check`.
  - [ ] 10.2 Revisão visual das 6 telas ao lado do rascunho (capturas de tela no `tasks.md`) e checagem do verificador de design.
  - [ ] 10.3 README: as telas novas, o novo mapa de rotas (links antigos continuam funcionando) e as notícias.
  - [ ] 10.4 Se alguma meta falhar: não afrouxar, registrar e parar para decidir com o José.
  - _Requisitos: NFR 1, NFR 2, todos_

---

## Mapa de cobertura

Todos os testes de navegador ficam em `tests/test_ui_novo.py` (Playwright + Edge, com o `fetch` embrulhado da spec anterior), exceto quando indicado.

| Requisito | Critério | Tarefa | Teste |
|---|---|---|---|
| 1 | 1.1 | 2, 10 | revisão visual 10.2 (manual) + `test_ui_tokens_do_rascunho` (cores computadas de fundo, superfície e destaque) |
| 1 | 1.2 | 2 | `test_ui_cabecalho_em_todas_as_telas` |
| 1 | 1.3 | 2 | `test_ui_moldura_centralizada_em_tela_larga` |
| 1 | 1.4 | 2 | `test_ui_sem_transicoes_com_movimento_reduzido` |
| 1 | 1.5 | 2 | `test_ui_sem_fontes_externas_renderiza` (adaptado) |
| 2 | 2.1 | 2 | `test_ui_barra_inferior_com_4_destinos` |
| 2 | 2.2 | 2 | `test_ui_destino_ativo_destacado` |
| 2 | 2.3 | 2 | `test_ui_menu_lateral_itens` |
| 2 | 2.4 | 9 | `test_ui_nomes_antigos_ausentes` |
| 2 | 2.5 | 2 | `test_ui_menu_fecha_com_esc_e_toque_fora` |
| 2 | 2.6 | 2 | `test_ui_links_antigos_abrem_tela_nova` |
| 3 | 3.1 | 2 | `test_ui_temporadas_so_com_dados` |
| 3 | 3.2 | 2 | `test_ui_semanas_so_com_dados` (com as rodadas de playoff pelo nome) |
| 3 | 3.3 | 3 | `test_ui_trocar_semana_atualiza_inicio` |
| 3 | 3.4 | 3 | `test_ui_erro_na_semana_mantem_filtros` |
| 3 | 3.5 | 2 | `test_ui_abre_na_semana_mais_recente` |
| 4 | 4.1 | 3 | `test_ui_inicio_ordem_das_secoes` |
| 4 | 4.2 | 3 | `test_ui_cartao_partidas_da_semana` |
| 4 | 4.3 | 1, 3 | `test_summary_rated_players` + `test_ui_cartao_jogadores_avaliados` |
| 4 | 4.4 | 3 | `test_ui_partida_abre_pagina_jogo` |
| 4 | 4.5 | 3 | `test_ui_carrossel_avanca_a_cada_5s` (relógio controlado) |
| 4 | 4.6 | 3 | `test_ui_carrossel_parado_com_movimento_reduzido` |
| 4 | 4.7 | 3 | `test_ui_semana_sem_noticias_oculta_carrossel` (resposta simulada vazia) |
| 4 | 4.8 | 3, 9 | os testes de cartão e ao vivo de `test_ui_dados.py`, adaptados |
| 5 | 5.1 | 4 | `test_ui_jogo_cabecalho_da_partida` |
| 5 | 5.2 | 4 | `test_ui_jogo_5_abas` |
| 5 | 5.3 | 4 | `test_ui_abas_do_antigo_treinador` (prancheta com 22 jogadores, jogadas por quarto, estatísticas, playbook) |
| 5 | 5.4 | 4 | `test_ui_replay_narrado_placar_e_acumulado` |
| 5 | 5.5 | 4 | `test_ui_jogada_em_jogadas_ou_replay_abre_prancheta` |
| 5 | 5.6 | 4 | `test_ui_trocar_aba_mantem_jogo_e_jogada` |
| 5 | 5.7 | 4 | `test_ui_jogo_sem_partida_abre_primeira_da_semana` |
| 5 | 5.8 | 4 | `test_ui_jogada_sem_formacao_mostra_aviso` |
| 5 | 5.9 | 4 | `test_ui_materia_no_topo_da_pagina_jogo` + os de matéria de `test_ui_dados.py`, adaptados |
| 6 | 6.1 | 6 | `test_ui_jogadores_busca_filtro_perfil_comparacao` |
| 6 | 6.2 | 6 | `test_ui_jogadores_a_observar_da_partida` |
| 6 | 6.3 | 6 | `test_ui_a_observar_atualiza_ao_trocar_partida` |
| 6 | 6.4 | 6 | `test_ui_a_observar_oculto_sem_avaliados` (resposta simulada) |
| 7 | 7.1 | 1 | `test_news_so_tipos_permitidos_e_numeros_do_dado`, `test_news_resultado_com_placar_oficial`, `test_news_limiares` |
| 7 | 7.2 | 1, 7 | `test_news_referencia_o_jogo` + `test_ui_noticia_mostra_o_jogo` |
| 7 | 7.3 | 1 | `test_news_ordenadas_por_incomum` |
| 7 | 7.4 | 3 | `test_ui_carrossel_4_primeiras` |
| 7 | 7.5 | 3, 7 | `test_ui_noticia_abre_pagina_jogo` |
| 7 | 7.6 | 1, 7 | `test_news_toda_semana_disputada_tem_noticia` + `test_ui_noticias_semana_vazia` |
| 8 | 8.1 | 7 | `test_ui_lupa_abre_busca_com_foco` |
| 8 | 8.2 | 7 | `test_ui_busca_agrupa_times_jogadores_noticias` |
| 8 | 8.3 | 7 | `test_ui_resultado_da_busca_leva_ao_destino` |
| 8 | 8.4 | 7 | `test_ui_busca_nada_encontrado` |
| 8 | 8.5 | 7 | `test_ui_busca_resposta_antiga_descartada` (adaptado) |
| 8 | 8.6 | 7 | `test_ui_busca_cancelar_e_esc_limpam` |
| 9 | 9.1 | 9 | `test_ui_sem_sugestoes_de_tatica` |
| 9 | 9.2 | 9 | `test_ui_sem_bastidores` |
| 10 | — | — | removido na v0.4 (Q7) |
| 11 | 11.1 | 8 | `test_ui_menu_abre_configuracoes` |
| 11 | 11.2 | 8 | `test_ui_configuracoes_dois_controles` (e o Replay na velocidade escolhida) |
| 11 | 11.3 | 8 | `test_ui_configuracao_aplica_sem_recarregar` |
| 11 | 11.4 | 8 | `test_ui_configuracao_persiste_ao_recarregar` |
| 11 | 11.5 | 2 | `test_ui_configuracao_corrompida_usa_padrao` |
| NFR | 1 | 10 | `test_ui_home_pronta_ate_200ms`, `test_ui_proxima_jogada_ate_50ms` (adaptados) + `carga.py --check` |
| NFR | 2 | 1, 10 | `golden.py check` |
| NFR | 3 | 9 | `test_ui_alvos_de_toque_44px` |
| NFR | 4 | 9 | `test_ui_contraste_minimo` |
| NFR | 5 | 9 | `test_ui_navegacao_por_teclado` |
| Segurança | S.1 | 9 | `test_ui_texto_do_dado_nao_vira_html` (resposta simulada com `<img onerror>`) |
| Segurança | S.2 | 7 | `test_ui_busca_corta_em_100_caracteres` |

---

## Ordem de execução

```
1 ───────────┬── 3 (Início) ──────────┐
2 (casca) ───┼── 4 (Jogo) ── 5 ── 8 ──┤
             ├── 6 (Jogadores) ───────┼── 9 (troca) ── 10
             └── 7 (Notícias/busca) ──┘
```

1 e 2 são independentes. A execução segue a numeração.

---

## Fora desta entrega

- CI no GitHub.
- Versão desktop própria.

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente (a interface nova vive em `novo.html` até a tarefa 9)
- [x] Mapa de cobertura preenchido, incluindo segurança
- [x] Branch `spec/novo-visual` criada antes da execução (**feito pelo José**)

**Aprovado por:** José Cota em 2026-09-25 (v0.3) e em 2026-09-26 (v0.4).
