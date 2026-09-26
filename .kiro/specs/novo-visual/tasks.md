# Implementation Plan

**Feature:** novo-visual
**Status:** ⏸ **PAUSADO** (2026-09-25)

> **Por que pausou:** o José esclareceu a meta: uma repaginação total, com **todos os dados vindo de APIs**. Decisões tomadas na mesma data:
> - **Dados primeiro, visual depois:** a spec `dados-externos` vem antes, e esta é retomada em cima dos dados novos.
> - **Prancheta sem movimento**, desenhada a partir de dados públicos de formação (não há tracking x/y em API aberta).
> - **Ratings recalculados** com estatísticas públicas (não mais PFF).
> - **Temporadas:** a atual (2026) mais as recentes (2021–2025).
>
> **Impacto:** os Requisitos 7 (notícias), 10 (movimento contínuo da prancheta), 3 (temporadas) e 6 (ratings) terão de ser revistos ao retomar. A tarefa 1 tinha só código não testado, gerado a partir do dataset; ele foi retirado da branch e guardado como referência.
**Data:** 2026-09-25

> Regras desta execução:
> - **Branch:** `spec/novo-visual`, criada pelo José antes da tarefa 1. Ao final, um commit e uma PR (mensagem e descrição preparadas pelo Claude, sem linha de coautoria).
> - **O app atual continua funcionando até a tarefa 9.** A interface nova é montada em `app/novo.html` + `app/js/*.js`, ao lado do `index.html`/`app.js` atuais. Só na tarefa 9 ela vira o `index.html` e o código antigo sai. Assim, toda tarefa é verificável sem quebrar o que existe, e os testes da spec anterior seguem valendo até a troca.
> - **Toda tarefa que mexe no servidor** termina com `golden.py check` 100% e `pytest` passando.
> - **Toda tarefa de tela** termina com os testes dela passando e uma captura de tela comparada com o rascunho.
> - **"Mover, não reescrever":** as funções do `app.js` que vão para as telas novas mantêm a lógica; muda o HTML e as classes.

---

## Tarefas

- [ ] 1. Gerar as notícias e o resumo no servidor
  - [ ] 1.1 `NFLData.news(week=None)` em `data_layer.py`, conforme o design (componente 2): recordes da semana (maior jogada, mais rápido, pocket; só o 1º de cada), eventos por jogo (≥ 5 sacks, ≥ 3 interceptações, virada ≥ 7 até o último dropback, prorrogação), "incomum" como percentil na liga, calculado no `_load`. Texto montado só com números do dado.
  - [ ] 1.2 `NFLData.summary()` → `{ratedPlayers, season, weeks}`.
  - [ ] 1.3 Rotas `GET /api/news` (`week` opcional) e `GET /api/summary` em `serve.py`; `/api/news?week=N` e `/api/summary` entram no aquecimento.
  - [ ] 1.4 Caminho infeliz: semana inexistente → `[]`; `week` não numérico → 400 (validação atual).
  - [ ] 1.5 Testes em `tests/test_news.py`.
  - _Requisitos: 4.3, 7.1, 7.3, 7.6, NFR 2_

- [ ] 2. Montar a casca da interface nova
  - [ ] 2.1 `app/novo.html` com o cabeçalho (menu, escudo, título, busca), os filtros de temporada e semana, a barra inferior com 4 destinos e o menu lateral (4 destinos + Sobre os dados + Configurações), no HTML do rascunho.
  - [ ] 2.2 `app/css/novo.css` com os tokens e componentes do rascunho, sem os padrões apontados pelo verificador de design (borda lateral no item ativo, ponto pulsante, texto < 12 px, sombra com brilho).
  - [ ] 2.3 `js/api.js` e `js/ui.js`: `get()` (LRU e dedupe), `ultimo()`, `into()` e os formatadores, **extraídos** do `app.js`.
  - [ ] 2.4 `js/main.js`: estado `S`, `ir()`, `selecionarJogo()`, menu lateral (abre, fecha com Esc e com toque fora), filtros vindos de `meta` (só 2021, semanas 1–8), rotas legadas (`?screen=coach|commentator|scout`) e boot em paralelo (como no `app.js` atual). As telas ainda são esqueletos.
  - [ ] 2.5 `js/config.js` (Requisito 11, sem a tela ainda): `ler`, `gravar`, `aoMudar`, `reduzirMovimento`, com padrões se o `localStorage` falhar.
  - [ ] 2.6 Fontes com `preload` sem bloquear (mesmo mecanismo do `index.html` atual).
  - _Requisitos: 1.1–1.5, 2.1–2.6, 3.1–3.4, 11.5_

- [ ] 3. Tela Início
  - _Depende de: 1, 2_
  - [ ] 3.1 Carrossel com as 4 primeiras notícias da semana (slides do rascunho), com os pontos de navegação. Avança sozinho a cada 5 s, pausa com o mouse em cima ou durante o toque, e não avança com movimento reduzido ou com o avanço desligado nas Configurações. Semana sem notícias oculta o carrossel.
  - [ ] 3.2 Dois cartões: partidas na semana (`games(week).length`) e jogadores avaliados (`summary.ratedPlayers`).
  - [ ] 3.3 Lista de jogos da semana (cartão de partida do rascunho). Tocar abre a página Jogo com a partida. Filtro por time vindo da busca, com chip "TIME ×".
  - [ ] 3.4 Caminho infeliz: erro ao carregar a semana mostra a mensagem na lista, e os filtros continuam utilizáveis.
  - _Requisitos: 3.3, 3.4, 4.1–4.7, 7.4, 7.5_

- [ ] 4. Página Jogo: cabeçalho, abas e conteúdo movido
  - _Depende de: 2_
  - [ ] 4.1 Cabeçalho da partida (placar, times, semana) e 5 abas: Prancheta, Jogadas, Replay, Estatísticas, Playbook. A aba, a partida e a jogada ficam em `S`.
  - [ ] 4.2 **Mover** para `js/telas/jogo.js`: `coachLineup`, `loadFieldPlay`, `prefetchVizinhas`, `ensurePlays`, `playRow`, `coachPlays`, `coachStats`, `coachBook`, `renderBroadcast`, `paintBc` e os controles do replay, com o HTML no visual novo e os contadores `seq` preservados.
  - [ ] 4.3 Tocar numa jogada em Jogadas ou em Replay abre a Prancheta com ela.
  - [ ] 4.4 Caminho infeliz: sem partida escolhida, abre a 1ª da semana; jogada sem tracking mostra os dados da jogada e o aviso "Tracking indisponível".
  - _Requisitos: 5.1–5.8_

- [ ] 5. Prancheta com movimento contínuo
  - _Depende de: 4_
  - [ ] 5.1 `js/prancheta.js`: `Field` movido do `app.js`, com posição por `transform` e laço de `requestAnimationFrame` que interpola entre `P[i]` e `P[i+1]`.
  - [ ] 5.2 Pausa, arraste e fim da jogada desenham o quadro exato; a troca de velocidade mantém a continuidade.
  - [ ] 5.3 Caminho infeliz: um jogador sem posição num dos quadros não é interpolado; com movimento reduzido ou animação suave desligada, o avanço é quadro a quadro.
  - [ ] 5.4 A velocidade inicial vem das Configurações.
  - _Requisitos: 10.1–10.6, 11.3_

- [ ] 6. Tela Jogadores
  - _Depende de: 2_
  - [ ] 6.1 **Mover** `scoutList`, `scoutDetail`, `radarBlock`/`radarSVG`, `fillComparePicker` e `showCompare` para `js/telas/jogadores.js`, no visual novo (lista no estilo `row-card` do rascunho).
  - [ ] 6.2 Seção "Jogadores a observar" com `game.watch` da partida selecionada, atualizada ao trocar de partida e oculta se vazia.
  - _Requisitos: 6.1–6.4_

- [ ] 7. Notícias e busca geral
  - _Depende de: 1, 2_
  - [ ] 7.1 Tela Notícias: `news(week)` no estilo `news-item` do rascunho; tocar abre a página Jogo; mensagem para semana vazia.
  - [ ] 7.2 Busca: a lupa abre o campo com o cursor nele. Os resultados vêm em 3 grupos: Times (de `meta.teams`), Jogadores (`/api/players?q=&limit=8` com `ultimo("busca")`) e Notícias (de `/api/news`, todas as semanas). O termo é cortado em 100 caracteres. Tocar num resultado leva ao destino. "Nada encontrado para "…"". Cancelar ou Esc fecha e limpa.
  - _Requisitos: 7.2, 7.5, 7.6, 8.1–8.6, S.2_

- [ ] 8. Configurações e Sobre os dados
  - _Depende de: 2, 5_
  - [ ] 8.1 Tela Configurações: animação suave (liga/desliga), avanço automático das notícias (liga/desliga) e velocidade padrão (0,25×, 0,5×, 1× ou 2×), aplicados na hora via `aoMudar`.
  - [ ] 8.2 Tela Sobre os dados com `meta.dataset` (escopo e ressalvas), incluindo a atribuição que já existe no README.
  - _Requisitos: 2.3, 11.1–11.4_

- [ ] 9. Trocar a interface e remover o código antigo
  - _Depende de: 3, 4, 5, 6, 7, 8_
  - [ ] 9.1 `novo.html` vira `index.html`; saem o `app.js` e o `app.css` antigos. `server/ui_test_all.py` é atualizado para as telas novas.
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
| 3 | 3.2 | 2 | `test_ui_semanas_so_com_dados` |
| 3 | 3.3 | 3 | `test_ui_trocar_semana_atualiza_inicio` |
| 3 | 3.4 | 3 | `test_ui_erro_na_semana_mantem_filtros` |
| 4 | 4.1 | 3 | `test_ui_inicio_ordem_das_secoes` |
| 4 | 4.2 | 3 | `test_ui_cartao_partidas_da_semana` |
| 4 | 4.3 | 1, 3 | `test_summary_rated_players` + `test_ui_cartao_jogadores_avaliados` |
| 4 | 4.4 | 3 | `test_ui_partida_abre_pagina_jogo` |
| 4 | 4.5 | 3 | `test_ui_carrossel_avanca_a_cada_5s` (relógio controlado) |
| 4 | 4.6 | 3 | `test_ui_carrossel_parado_com_movimento_reduzido` |
| 4 | 4.7 | 3 | `test_ui_semana_sem_noticias_oculta_carrossel` (resposta simulada vazia) |
| 5 | 5.1 | 4 | `test_ui_jogo_cabecalho_da_partida` |
| 5 | 5.2 | 4 | `test_ui_jogo_5_abas` |
| 5 | 5.3 | 4 | `test_ui_abas_do_antigo_treinador` (prancheta com 22 jogadores, jogadas por quarto, estatísticas, playbook) |
| 5 | 5.4 | 4 | `test_ui_replay_narrado_placar_e_acumulado` |
| 5 | 5.5 | 4 | `test_ui_jogada_em_jogadas_ou_replay_abre_prancheta` |
| 5 | 5.6 | 4 | `test_ui_trocar_aba_mantem_jogo_e_jogada` |
| 5 | 5.7 | 4 | `test_ui_jogo_sem_partida_abre_primeira_da_semana` |
| 5 | 5.8 | 4 | `test_ui_jogada_sem_tracking_mostra_aviso` (404 simulado) |
| 6 | 6.1 | 6 | `test_ui_jogadores_busca_filtro_perfil_comparacao` |
| 6 | 6.2 | 6 | `test_ui_jogadores_a_observar_da_partida` |
| 6 | 6.3 | 6 | `test_ui_a_observar_atualiza_ao_trocar_partida` |
| 6 | 6.4 | 6 | `test_ui_a_observar_oculto_sem_avaliados` (resposta simulada) |
| 7 | 7.1 | 1 | `test_news_so_tipos_permitidos_e_numeros_do_dado`, `test_news_virada_diz_ate_ultimo_dropback`, `test_news_sem_noticia_de_placar` |
| 7 | 7.2 | 1, 7 | `test_news_referencia_o_jogo` + `test_ui_noticia_mostra_o_jogo` |
| 7 | 7.3 | 1 | `test_news_ordenadas_por_incomum` |
| 7 | 7.4 | 3 | `test_ui_carrossel_4_primeiras` |
| 7 | 7.5 | 3, 7 | `test_ui_noticia_abre_pagina_jogo` |
| 7 | 7.6 | 1, 7 | `test_news_entre_4_e_30_por_semana` + `test_ui_noticias_semana_vazia` |
| 8 | 8.1 | 7 | `test_ui_lupa_abre_busca_com_foco` |
| 8 | 8.2 | 7 | `test_ui_busca_agrupa_times_jogadores_noticias` |
| 8 | 8.3 | 7 | `test_ui_resultado_da_busca_leva_ao_destino` |
| 8 | 8.4 | 7 | `test_ui_busca_nada_encontrado` |
| 8 | 8.5 | 7 | `test_ui_busca_resposta_antiga_descartada` (adaptado) |
| 8 | 8.6 | 7 | `test_ui_busca_cancelar_e_esc_limpam` |
| 9 | 9.1 | 9 | `test_ui_sem_sugestoes_de_tatica` |
| 9 | 9.2 | 9 | `test_ui_sem_bastidores` |
| 10 | 10.1 | 5 | `test_ui_prancheta_posicao_intermediaria_durante_play` |
| 10 | 10.2 | 5 | `test_ui_prancheta_quadros_registrados_exatos` |
| 10 | 10.3 | 5 | `test_ui_prancheta_pausa_e_arraste_no_quadro_exato` |
| 10 | 10.4 | 5 | `test_ui_prancheta_velocidade_mantem_continuidade` |
| 10 | 10.5 | 5 | `test_prancheta_sem_quadro_nao_interpola` (dados simulados) |
| 10 | 10.6 | 5, 8 | `test_ui_prancheta_quadro_a_quadro_com_movimento_reduzido`, `..._com_suave_desligado` |
| 11 | 11.1 | 8 | `test_ui_menu_abre_configuracoes` |
| 11 | 11.2 | 8 | `test_ui_configuracoes_tres_controles` |
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

- **Notícia de placar/resultado, placar oficial, jogadas completas e matérias da ESPN:** spec `dados-externos` (fontes já testadas).
- CI no GitHub.
- Versão desktop própria.

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente (a interface nova vive em `novo.html` até a tarefa 9)
- [x] Mapa de cobertura preenchido, incluindo segurança
- [x] Branch `spec/novo-visual` criada antes da execução (**feito pelo José**)

**Aprovado por:** José Cota em 2026-09-25. O plano foi mantido: várias temporadas entram na spec `dados-externos`; os filtros desta spec já mostram o que existir nos dados.
