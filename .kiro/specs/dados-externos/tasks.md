# Implementation Plan

**Feature:** dados-externos
**Status:** aprovado · em execução
**Data:** 2026-09-25

> Regras desta execução:
> - **Branch:** `spec/dados-externos` (já criada). Ao final: um commit e uma PR, com mensagem e descrição preparadas pelo Claude, sem linha de coautoria.
> - **O app continua funcionando até a tarefa 8.** O ETL novo grava em `dados/` e o servidor novo é ligado na tarefa 6. Até lá, o servidor atual segue lendo o dataset, e os testes da spec anterior continuam valendo.
> - **O golden não é usado para comparar nesta spec** (os números mudam de propósito; Decisão 5 do design). A correção vem dos testes de integração contra as fontes. O golden é recapturado na tarefa 9.
> - **A tarefa 4 tem um ponto de parada obrigatório:** os 10 melhores de cada grupo, com nomes, são mostrados ao José antes de a tarefa ser dada como pronta.

---

## Tarefas

- [x] 1. Generalizar o formato binário das tabelas
  - [x] 1.1 `server/tabela_npz.py` a partir do `tracking_npz.py`: `salvar(df, destino)` e `carregar(origem)` para qualquer DataFrame (números bit a bit, texto como categoria, gravação atômica, `allow_pickle=False`). **Ajustes em relação ao codec antigo:**
    - os códigos de categoria passaram de int16 para **int32**, porque o play-by-play tem ~50 mil descrições distintas por temporada;
    - os nomes das colunas ficam guardados à parte (`__colunas`), o que aceita qualquer nome;
    - colunas pandas *nullable* (`Int64`, `boolean`) viram float64 com NaN.
  - [x] 1.2 `tests/test_tabela_npz.py`: 6 testes (ida e volta, nullable, tabela vazia, coluna toda ausente, 70 mil textos distintos, gravação atômica, arquivo corrompido).
  - **Medido com dado real:** o play-by-play inteiro de 2021 (49.922 jogadas × 372 colunas) volta **idêntico** nas 219 colunas numéricas e nas 153 de texto; carrega em **0,55 s** (o CSV leva 3,9 s) e ocupa 16 MB (o CSV compactado, 18 MB).
  - _Requisitos: NFR 2, NFR 4_

- [x] 2. Baixar e validar as fontes
  - [x] 2.1 `etl/fontes.py`: `CATALOGO` com as fontes do design. **Ajuste:** entrou uma **9ª release, `rosters`** (elencos por temporada). A participação de **2021 e 2022 não tem nomes, posições nem números**, só os ids dos jogadores (os nomes começam em 2023), e a tabela `players` só tem o número de camisa **atual**. O elenco da temporada dá o número e a posição daquele ano.
  - [x] 2.2 `sincronizar()`: 1 chamada à API do GitHub por release; baixa só o que mudou; `.tmp` → validação → renomeia; o manifesto é salvo arquivo a arquivo, então uma interrupção não perde o que já foi baixado.
  - [x] 2.3 Caminhos infelizes cobertos (coluna faltando, sem rede, sem rede e sem cópia, limite da API, URL fora da lista).
  - [x] 2.4 `tests/test_fontes.py`: 9 testes com um "GitHub" falso local.
  - [x] 2.5 Primeira sincronização real: **60 arquivos, 330 MB, 102 s, 0 falhas** (meta NFR 3: 5 min). `dados/` já entrou no `.gitignore` (adiantado da 8.3, para os 330 MB não correrem o risco de entrar num commit).
  - _Requisitos: 7.1, 7.5, 7.6, NFR 3, NFR 4, S.2, S.3_

- [x] 3. Montar as tabelas por temporada
  - _Depende de: 1, 2_
  - [x] 3.1 `etl/montar.py`: `jogos` e `jogadores_bio` **gerais** (economia de espaço, ver o design), e por temporada `jogadas` (play-by-play + participação + FTN; nomes, posições e números de 2021–22 vindos do elenco da temporada) e `jogador_jogo` (estatísticas + avançadas do PFR + snaps, com a ponte `pfr_id → gsis` pela bio **e** pelo elenco).
  - [x] 3.2 Incremental por `origem.json`; `economia=True` descarta os brutos das temporadas encerradas depois de montadas (`fontes.descartar`; a sincronização só os baixa de novo se forem republicados ou forçados).
  - [x] 3.3 `tests/test_montar.py` (21 testes com os dados reais) + 4 testes de descarte em `test_fontes.py`. O "jogo futuro com `status = agendado`" virou "jogo futuro sem placar e com data/hora": o status é calculado na hora da requisição (design atualizado).
  - **Descobertas nos dados reais:**
    - **O `play_id` não é cronológico** em 59 de 285 jogos de 2021 e em todos os 33 de 2026. Pegando o "último lance" pelo `play_id`, 8 jogos mostravam o placar errado (ex.: MIA × LV com 17–25, quando o jogo terminou 28–31). A ordem agora vem do `order_sequence` do nflverse, numa coluna `seq`. Com ela, **o placar oficial bate com o último lance em 100% dos jogos das 6 temporadas** e nunca diminui ao longo do jogo.
    - A fonte de estatísticas tem ~22 registros por temporada **sem id de jogador**; eles são descartados.
    - ~19% dos registros de OL têm 0 snaps de ataque: são reservas que entram só nos times especiais (dado legítimo).
    - De 7 a 61 registros do PFR/snaps por temporada (em ~30 mil) ficam sem ponte para o id do jogador, e são logados.
  - **Números:** as 6 temporadas são montadas em **31 s**; 1.696 jogos (com 65 de playoff); 2021 passou de 8.557 para **48.461 jogadas** (285 jogos). **As tabelas prontas ocupam 42 MB.**
  - _Requisitos: 1.1–1.5, 2.1–2.3, 3.1, 3.2_

- [x] 4. Calcular os ratings
  - _Depende de: 3_
  - [x] 4.1 `etl/ratings.py`: grupos, eixos e mínimos exatamente como a tabela do design; rating = `40 + média dos percentis × 0,59`; `n/d` abaixo do mínimo; eixo sem dado com motivo; `baseReduzida` na OL. Entra no `montar.py` pelo gancho `depois_da_temporada` (`ratings.montar` grava `jogadores.npz`).
  - [x] 4.2 Tabela `jogadores` por temporada: nome, posição, grupo, time principal, jogos, totais da temporada, volume, mínimo, `avaliado`, `rating`, `baseReduzida`, e `eixo{0..5}_valor/_pct/_motivo`. A bio (foto, altura etc.) fica na tabela geral `jogadores_bio`, e o servidor junta as duas.
  - [x] 4.3 `tests/test_ratings.py`: 10 testes (mínimo proporcional, percentil no grupo e escala 40–99, eixo ↓ invertido, eixo ausente fora da média, OL com base reduzida, Edge pelo depth chart e pelo papel, eixo de corrida do QB, alvos por jogo, e **nenhum eixo vazio nos dados reais de 2021 e 2025**).
  - **Bug encontrado e corrigido:** o eixo "Sacks" da linha defensiva saía vazio. `def_sacks` existia no `stats_player` **e** no PFR, e o merge renomeava as duas colunas (`_x`/`_y`). O PFR deixou de trazer essa coluna, e a junção agora **falha alto** se aparecer qualquer coluna repetida (`ETL_VERSION = 3`).
  - [x] 4.4 **Parada obrigatória:** os 10 melhores de cada grupo em 2024 e 2025 estão em `.kiro/specs/dados-externos/validacao_ratings.md`.
    - Decisões do José (2026-09-25), já aplicadas: (1) **grupo Edge** (DE + OLB pass rusher, pelo `depth_chart_position` do elenco, que agora vai para o `jogador_jogo` como `posicao_elenco`; `ETL_VERSION = 4`); (2) **QB com 6 eixos** (+ "Corrida" = EPA das corridas por jogo); (3) WR/TE: **"Alvos por jogo"** no lugar de "Após a recepção"; (4) OL confirmada.
    - Nomes validados pelo José em 2026-09-25.
  - **Economia aplicada** depois da 4.4: `fontes.descartar` nos brutos de 2021–2025 (323 MB liberados; `dados/brutos` com 6,5 MB, só 2026 e os gerais). O `atualizar()` confirma as 6 temporadas prontas sem pedir brutos. Se os ratings mudarem de novo, remontar exige `sincronizar(forcar=...)`.
  - _Requisitos: 5.1, 5.2, 5.4, 5.5, 5.7_

- [x] 5. Esquema da prancheta
  - _Depende de: 3_
  - [x] 5.1 `server/prancheta.py`: `esquema(jogada)` conforme o design (ataque para `+x`, OL/TE/WR/QB/RB por formação e `qb_local`, defesa por grupo e `box`, bola no hash), no formato de `/tracking` com 1 quadro e `ilustrativo: true`.
  - [x] 5.2 Esquema genérico (sem nomes, `generico: true`) quando só há FTN; `None` sem nenhuma formação.
  - [x] 5.3 Testes: 11 × 11 jogadores dentro do campo; QB mais fundo no shotgun que sob o center; o número de defensores no box confere; o genérico sem nomes; sem formação → `None`. `tests/test_prancheta.py`: 22 testes, incluindo 400 jogadas reais de 2021, 2023, 2025 e 2026 cada (box confere, dentro do campo, ids únicos, **nenhum par de jogadores a menos de 1 jd**).
  - Ajustes ao design (registrados lá): QB sob o center a 2 jd (a 1 jd ficava em cima do C em ~30% das jogadas); RB a 6 jd e FB a 3,5 jd sob o center; box com 5 jd de largura para cada lado da bola; posições trocadas e listas com 10/12 jogadores tratadas; chutes (lista sem formação) → `None`.
  - A resposta traz também `formacao: {nome, pessoalAtaque, pessoalDefesa, box, rushers}` para o painel da prancheta (4.2).
  - _Requisitos: 4.1–4.6_

- [ ] 6. Ligar o servidor aos dados novos
  - _Depende de: 3, 4, 5_
  - [ ] 6.1 `server/data_layer.py` reescrito sobre as tabelas das 6 temporadas, mantendo o formato das respostas de todas as rotas atuais; `season` nas listagens (padrão: a atual); id de jogador gsis nas rotas; `/tracking` e `/formation` pelo `esquema`; `insights`/`notes` vazios; campos sem fonte fora das respostas.
  - [ ] 6.2 `server/serve.py`: sincroniza e monta na subida; thread de atualização diária; troca atômica de `DATA`; `CACHE.limpar()` + reaquecimento da semana atual; `/api/meta` com `ultimaAtualizacao`, `fontes`/créditos e temporadas/semanas com os nomes das rodadas; primeira subida sem internet e sem cópia sai com mensagem e código 1.
  - [ ] 6.3 Testes: cada rota responde nas 6 temporadas; a troca de dados durante requisições não gera erro; o cache é limpo depois da troca; a subida sem dados sai com código 1; `RODAR.bat` mostra o progresso da primeira carga.
  - _Requisitos: 1.3, 2.1, 3.1–3.4, 4.1, 5.3, 5.6, 7.1–7.4, 7.6, 8.3, 9.1, NFR 2, NFR 5_

- [ ] 7. Adaptar as telas atuais
  - _Depende de: 6_
  - [ ] 7.1 Seletor de temporada; chips de playoff com os nomes das rodadas; id de jogador em texto em todas as telas.
  - [ ] 7.2 Cartões de jogo com os estados "a jogar", "resultado ainda não disponível", encerrado e **AO VIVO** (módulo de placar ao vivo: a cada 30 s só enquanto houver jogo em andamento na semana; para ao encerrar; mensagem na falha; o nflverse prevalece depois).
  - [ ] 7.3 Bloco da matéria do jogo na Home (título, data, fonte e link, só `*.espn.com`, `http` → `https`); some se falhar.
  - [ ] 7.4 Prancheta com o aviso "Esquema ilustrativo" e sem os controles de animação quando `frameCount == 1`; "formação indisponível" quando não houver esquema.
  - [ ] 7.5 Blocos sem dado ocultos (velocidade, insights, bastidores); avisos antigos do dataset removidos; "Sobre os dados" com as fontes, os créditos e a última atualização.
  - [ ] 7.6 Testes de navegador com a ESPN simulada (`page.route`): `pre` → `in` → `post`, erro, matéria presente, ausente e com link estranho.
  - _Requisitos: 1.4, 1.5, 3.3, 3.4, 4.3, 4.5, 6.1–6.3, 8.1–8.3, 9.1, 9.2, 10.1–10.6, S.1, S.4_

- [ ] 8. Aposentar o dataset do Big Data Bowl
  - _Depende de: 6, 7_
  - [ ] 8.1 Remover a leitura do dataset e do `cache/` antigo: `etl/build_metrics.py`, `server/tracking_npz.py` (substituído pelo `tabela_npz.py`) e os testes que dependiam deles (`test_tracking.py`, `test_ensure_cache.py`), trocados pelos testes das tarefas 1–6.
  - [ ] 8.2 Adaptar `tools/bench.py`, `tools/carga.py` e `tests/test_ui.py` para a semana mais recente disputada; `server/smoke_test.py` e `ui_test_all.py` para os dados novos.
  - [ ] 8.3 `.gitignore`: `dados/` e `nfl-big-data-bowl-regional-event-data-main/`.
  - [ ] 8.4 **Feito pelo José:** tirar o dataset do versionamento: `git rm -r --cached nfl-big-data-bowl-regional-event-data-main` (e o `cache/` antigo, se ainda houver algo rastreado).
  - _Requisitos: 3.3, 8.1, NFR 4_

- [ ] 9. Medição final e documentação
  - _Depende de: 8_
  - [ ] 9.1 `pytest`, `bench.py --check`, `carga.py --usuarios 10 --check` (semana mais recente disputada), subida ≤ 10 s, memória ≤ 1 GB, primeira carga ≤ 5 min e disco ≤ 1 GB. Resultados em `tests/golden/resultado_dados_externos.txt`.
  - [ ] 9.2 Recapturar o golden como a nova base (Decisão 5).
  - [ ] 9.3 README: as fontes e os créditos, temporadas e playoffs, a atualização diária, o placar ao vivo, a prancheta ilustrativa, os ratings novos e o que deixou de existir (animação, velocidade de pico).
  - [ ] 9.4 Se alguma meta falhar: não afrouxar, registrar e parar para decidir com o José.
  - _Requisitos: NFR 1–5, 9.1_

---

## Mapa de cobertura

| Requisito | Critério | Tarefa | Teste |
|---|---|---|---|
| 1 | 1.1 | 3, 6 | `test_temporadas_2021_a_2026_com_playoffs` |
| 1 | 1.2 | 3, 7 | `test_rodadas_de_playoff_com_nome` + `test_ui_chips_de_playoff` |
| 1 | 1.3 | 6 | `test_api_jogos_da_semana_com_data_horario_times` |
| 1 | 1.4 | 3, 7 | `test_jogo_futuro_agendado` + `test_ui_cartao_a_jogar` |
| 1 | 1.5 | 3, 7 | `test_jogo_sem_resultado` + `test_ui_cartao_sem_resultado` |
| 2 | 2.1 | 3 | `test_placar_oficial_confere_com_ultimo_lance`, `test_tb_dal_2021_31_29` |
| 2 | 2.2 | 3 | `test_prorrogacao_marcada` |
| 2 | 2.3 | 6 | `test_replay_placar_por_jogada_inclui_corridas_e_chutes` |
| 2 | 2.4 | 7 | `test_ui_materia_com_placar_divergente_mantem_nflverse` |
| 3 | 3.1 | 3, 6 | `test_jogadas_incluem_corridas_chutes_retornos` |
| 3 | 3.2 | 6 | `test_api_jogada_situacao_resultado_descricao` |
| 3 | 3.3 | 7, 8 | `test_ui_sem_avisos_do_dataset_antigo` |
| 3 | 3.4 | 6, 7 | `test_api_jogada_sem_formacao_marcada` + `test_ui_jogada_sem_formacao` |
| 4 | 4.1 | 5 | `test_esquema_22_jogadores_com_numero_e_posicao` |
| 4 | 4.2 | 5, 6 | `test_esquema_traz_formacao_pessoal_box_rushers` |
| 4 | 4.3 | 7 | `test_ui_prancheta_aviso_ilustrativo` |
| 4 | 4.4 | 5 | `test_esquema_generico_sem_nomes` |
| 4 | 4.5 | 5, 7 | `test_esquema_sem_formacao_none` + `test_ui_formacao_indisponivel` |
| 4 | 4.6 | 5 | `test_esquema_em_jogo_de_2021` |
| 5 | 5.1 | 4 | `test_rating_percentil_dentro_do_grupo_e_temporada` |
| 5 | 5.2 | 4, 6 | `test_radar_valor_bruto_e_percentil` |
| 5 | 5.3 | 6 | `test_api_jogador_temporada_e_jogo_a_jogo` |
| 5 | 5.4 | 4 | `test_minimo_proporcional_aos_jogos_do_time`, `test_abaixo_do_minimo_nd` |
| 5 | 5.5 | 4 | `test_eixo_sem_dado_fora_da_media_com_motivo` |
| 5 | 5.6 | 6 | `test_api_compare_mesmo_grupo_e_temporada` |
| 5 | 5.7 | 4 | `test_ol_base_reduzida` |
| 6 | 6.1 | 7 | `test_ui_materia_titulo_resumo_data_link` |
| 6 | 6.2 | 7 | `test_ui_materia_mostra_fonte` |
| 6 | 6.3 | 7 | `test_ui_materia_indisponivel_some` |
| 7 | 7.1 | 2 | `test_sincroniza_so_o_que_mudou` |
| 7 | 7.2 | 6 | `test_atualizacao_diaria_agendada` (relógio controlado) |
| 7 | 7.3 | 6 | `test_troca_de_dados_sem_reiniciar_e_cache_limpo` |
| 7 | 7.4 | 6, 7 | `test_meta_ultima_atualizacao` + `test_ui_sobre_mostra_ultima_atualizacao` |
| 7 | 7.5 | 2 | `test_sem_rede_segue_com_copia_local`, `test_limite_da_api_tratado_como_sem_rede` |
| 7 | 7.6 | 2, 6 | `test_sem_rede_e_sem_copia_levanta_semdados` + `test_subida_sem_dados_sai_com_codigo_1` |
| 8 | 8.1 | 7 | `test_ui_quatro_telas_funcionam_com_dados_novos` |
| 8 | 8.2 | 7 | `test_ui_seletor_de_temporada` |
| 8 | 8.3 | 6, 7 | `test_api_sem_campos_sem_fonte` + `test_ui_blocos_sem_dado_ocultos` |
| 9 | 9.1 | 6, 7 | `test_meta_fontes_com_creditos` + `test_ui_sobre_mostra_fontes` |
| 9 | 9.2 | 7 | `test_ui_materia_mostra_fonte` |
| 10 | 10.1 | 7 | `test_ui_ao_vivo_placar_quarto_relogio` |
| 10 | 10.2 | 7 | `test_ui_ao_vivo_atualiza_a_cada_30s` (relógio controlado) |
| 10 | 10.3 | 7 | `test_ui_ao_vivo_encerrado_para_de_consultar` |
| 10 | 10.4 | 7 | `test_ui_sem_jogo_em_andamento_nao_consulta` |
| 10 | 10.5 | 7 | `test_ui_ao_vivo_falha_mantem_ultimo_placar` |
| 10 | 10.6 | 7 | `test_ui_encerrado_prevalece_nflverse` |
| NFR | 1 | 9 | `bench.py --check`, `carga.py --usuarios 10 --check`, `test_ui_home_pronta_ate_200ms` |
| NFR | 2 | 6, 9 | `test_subida_com_copia_local_ate_10s` |
| NFR | 3 | 2, 9 | `test_primeira_carga_ate_5min` (marcado `lento`) |
| NFR | 4 | 2, 9 | `test_disco_ate_1gb` |
| NFR | 5 | 9 | `carga.py` (pico de memória ≤ 1 GB) |
| Segurança | S.1 | 7 | `test_ui_texto_externo_nao_vira_html` |
| Segurança | S.2 | 2 | `test_arquivo_sem_coluna_rejeitado_mantem_copia` |
| Segurança | S.3 | 2 | `test_url_fora_da_lista_recusada` |
| Segurança | S.4 | 7 | `test_ui_link_fora_da_espn_nao_exibido` |

---

## Ordem de execução

```
1 ──┐
2 ──┴── 3 ──┬── 4 (parada: validação dos ratings) ──┐
            └── 5 ──────────────────────────────────┴── 6 ── 7 ── 8 ── 9
```

---

## Fora desta entrega

- Visual novo, tela Notícias, busca geral e Configurações: spec `novo-visual` (pausada), retomada depois desta.
- Temporadas anteriores a 2021.
- Jogada a jogada ao vivo.

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente (o servidor novo só é ligado na tarefa 6)
- [x] Mapa de cobertura preenchido, incluindo segurança
- [x] Branch `spec/dados-externos` criada

**Aprovado por:** José Cota em 2026-09-25
