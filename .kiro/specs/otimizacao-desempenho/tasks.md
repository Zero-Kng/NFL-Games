# Implementation Plan

**Feature:** otimizacao-desempenho
**Status:** concluído (2026-09-24)
**Data:** 2026-09-24

> Regras desta execução:
> - **Tarefa 1 vem antes de qualquer mudança de código.** O golden precisa fotografar o comportamento *atual*.
> - Ao fim de cada tarefa que mexe em `server/` ou `etl/`: rodar `python tools/golden.py check` e `pytest`. Se o golden quebrar, a tarefa não está pronta.
> - Commits são feitos pelo José, no repositório do GitHub. O agente para ao fim de cada tarefa, informa o que mudou e sugere a mensagem de commit.

---

## Tarefas

- [x] 1. Criar as ferramentas de verificação e fotografar o comportamento atual
  - **Concluída em 2026-09-24.** Golden: 2.159 URLs (2.151 com 200, 5 com 404, 3 com 400), 317 KB. Rodado de novo num servidor novo, deu 2.159/2.159 idênticas, então as respostas atuais são determinísticas. O check leva ~130 s. Linha de base em `tests/golden/linha_de_base.txt`.
  - **Descobertas que afetam as próximas tarefas:**
    - No dataset, **toda jogada tem tracking** (`hasTracking` nunca é falso). O caso "sem tracking" do critério 2.4 é, na prática, um `playId` inexistente no jogo. Hoje ele leva 28 ms, porque passa por `play_tracking` inteiro.
    - As respostas de erro não trazem `X-Query-Time`. O `bench.py` usa o tempo do cliente nesses casos.
    - A tarefa 4.3 **precisa** logar `aquecimento: inicio` e `aquecimento: concluido`. O `tools/servidor_local.py` espera essas linhas para medir só depois do aquecimento.
  - [x] 1.1 `requirements-dev.txt` com `pytest` e `playwright` (sem `playwright install`: usa o Edge já instalado via `channel="msedge"`). `tests/conftest.py` com uma fixture `servidor` que sobe o `serve.py` numa porta livre, espera `/api/meta` responder e derruba no fim.
  - [x] 1.2 `tools/golden.py capture|check`. `capture` percorre a lista fixa de URLs do design (componente 6) contra um servidor e grava `tests/golden/hashes.json` = `{url: sha256(json canônico)}`. `check` compara e lista cada URL divergente. Ao final existe `hashes.json` capturado **da versão atual, sem nenhuma alteração no código**.
  - [x] 1.3 `tools/bench.py`: tempos por rota com 1 usuário (mediana de 3 execuções), no formato da tabela de linha de base do requirements.md. Usa `--check` para sair com erro se alguma meta de tempo por rota falhar.
  - [x] 1.4 `tools/carga.py --usuarios N`: sessão típica em paralelo. Imprime p50, p95, erros, conexões recusadas e pico de memória do processo servidor. Usa `--check` para comparar com as metas do Requisito 1 e do 6.5.
  - [x] 1.5 Rodar `bench.py` e `carga.py --usuarios 10` na versão atual e salvar a saída em `tests/golden/linha_de_base.txt`. Ela deve reproduzir os números do requirements.md (±20%).
  - _Requisitos: 6.1, NFR 1_

- [x] 2. Endurecer a borda HTTP (sem cache ainda)
  - [x] 2.1 `serve.py`: classe `Server(ThreadingHTTPServer)` com `request_queue_size = 128`.
  - [x] 2.2 Semáforo `MAX_PENDENTES = 64` (configurável por argumento `--max-pendentes`, para o teste). Sem vaga, a resposta é `503 {"error": "servidor ocupado, tente novamente"}` + `Retry-After: 2`.
  - [x] 2.3 Trocar `str(target).startswith(...)` por `target.is_relative_to(APP_DIR.resolve())`.
  - [x] 2.4 Estáticos com `ETag` (sha1 do conteúdo, memorizado por `(caminho, mtime_ns)`) e `Cache-Control: no-cache`. Se `If-None-Match` bater, a resposta é `304` sem corpo.
  - [x] 2.5 Caminho infeliz: testes de 403 (`/../server/serve.py` e `/../app2/x`), 400 com parâmetro inválido, 503 com `--max-pendentes 1` e uma requisição lenta segurando a vaga.
  - _Requisitos: 1.2, 1.4, 4.3, 4.4, S.1, S.2, S.3, S.4_

- [x] 3. Implementar o CacheDeRespostas isolado
  - [x] 3.1 `server/response_cache.py` com `Resposta`, `CacheDeRespostas.get_or_build`, `aquecer` e `stats`, conforme a interface do design.
  - [x] 3.2 Single-flight: um `threading.Event` por chave em construção. Quem chega depois espera e recebe o mesmo resultado.
  - [x] 3.3 LRU por bytes do gzip, com limite de 128 MB.
  - [x] 3.4 Caminho infeliz: `build()` que lança propaga a exceção para todos os que esperavam, não guarda nada, e a chamada seguinte tenta de novo.
  - [x] 3.5 Testes unitários: 10 threads na mesma chave executam `build` 1 vez; exceção sem envenenar o cache; despejo por LRU quando passa do limite; chaves diferentes não se bloqueiam.
  - _Requisitos: 1.3, 1.5, 6.5_

- [x] 4. Ligar o cache nas rotas da API e aquecer no startup
  - _Depende de: 2, 3_
  - [x] 4.1 `_handle_api`: validação (já existente) → chave normalizada (rota + parâmetros **conhecidos** ordenados) → `get_or_build` → envia o gzip pronto. Se o cliente não aceita gzip, descomprime na hora. Cabeçalhos `X-Cache: HIT|MISS` e `X-Query-Time`.
  - [x] 4.2 Só respostas 200 entram no cache. `ApiError` (400/404) atravessa sem ser guardado.
  - [x] 4.3 `aquecer()` em thread daemon depois que o servidor começa a escutar, na ordem: `meta`, `games` por semana, e `game`/`plays`/`broadcast` dos 122 jogos (semana 1 primeiro). Loga o início, o fim e a duração.
  - [x] 4.4 Caminho infeliz: se uma tarefa do aquecimento falhar, loga e segue para a próxima (o servidor não cai).
  - [x] 4.5 Rodar `golden.py check` (tem que passar 100%) e `carga.py --usuarios 10`, e anotar o resultado parcial no `linha_de_base.txt`.
  - **Resultado das tarefas 2 a 4:** golden 2.159/2.159 e 17 testes passando. Detalhe do jogo 111 → 0 ms (4.2 ok); jogada inexistente 28 → 4 ms (2.4 ok). Carga com 10 usuários: p50 457 → 151 ms, mas o **p95 continua em ~1,7 s** porque o tracking ainda é caro (cabe às tarefas 5 e 6).
  - **Desvio registrado:** o `X-Query-Time` de um miss agora inclui serialização e gzip, o que é mais honesto. Por isso a busca de 300 foi medida em 32 ms, contra a meta de 30 ms do 5.3. **Cabe à tarefa 6.7**, acrescentada abaixo.
  - _Requisitos: 1.1, 1.3, 1.5, 4.2, 5.3, NFR 2_

- [x] 5. Tornar a preparação de dados incremental e gerar o tracking binário
  - [x] 5.1 `etl/build_metrics.py`: `ETL_VERSION = 2`, `ensure_cache()` e `Relatorio`. Um jogo é processado se for novo, se o tamanho ou mtime do CSV mudou, se faltar alguma parte ou se `etlVersion` mudou. **Acréscimo:** também reprocessa tudo se o `pffScoutingData.csv` mudar, porque as funções por jogada entram nas métricas. E um jogo que some do dataset sai do cache e dos agregados.
  - [x] 5.2 Por jogo, grava `cache/parts/<id>.timing.csv`, `cache/parts/<id>.motion.csv` e `cache/tracking/<id>.npz`, sempre de forma atômica. **Desvio:** o texto (`team`, `playDirection`, `event`) é gravado como **categoria** (códigos int16 + valores), e não como unicode por célula. Recriar ~200 mil strings por jogo fazia a leitura levar 56–73 ms; com categorias leva ~22 ms, com os mesmos valores (verificado com `assert_frame_equal` em 5 jogos). O codec fica em `server/tracking_npz.py`, usado pelo ETL e pelo servidor.
  - [x] 5.3 Se algum jogo mudou, reconcatena `play_timing.csv` e `player_play.csv` a partir das partes. **Verificado: os dois arquivos saem idênticos byte a byte aos do ETL original** (SHA-256 igual).
  - [x] 5.4 `manifest.json` gravado por último. Uma interrupção no meio faz o próximo startup refazer só o que faltou.
  - [x] 5.5 `serve.py` chama `ensure_cache()` antes de `NFLData`. `RODAR.bat` só sobe o servidor e abre o navegador quando a porta responde (antes abria na hora e, na 1ª execução, mostrava erro). `--force` continua funcionando; a opção `--limit` saiu, porque não faz sentido com o cache incremental.
  - [x] 5.6 Testes de caminho infeliz: `tests/test_ensure_cache.py`, com 10 testes (inclui jogo removido e pasta de tracking ausente).
  - [x] 5.7 Primeiro preparo completo, do zero: **45,6 s** (meta: 90 s), sem precisar paralelizar. Cache binário: **111 MB** (estimativa: 123 MB).
  - _Requisitos: 6.2, 6.3, 6.4, NFR 3, restrição de novas fontes de partidas_

- [x] 6. Ler o tracking do `.npz` e montar a resposta da jogada sem `iterrows`
  - _Depende de: 5_
  - [x] 6.1 `_tracking_for_game`: carrega o `.npz` com `allow_pickle=False` e guarda no LRU (6 → 12 jogos), junto com um índice `playId → fatia de linhas`.
  - [x] 6.2 Caminho infeliz: `.npz` ilegível loga `[aviso]` e cai no CSV original; sem `.npz` usa o CSV sem aviso; sem os dois, retorna `None` e a rota responde 404.
  - [x] 6.3 `play_tracking` com numpy e `round()` do Python. **Verificação extra, além do golden:** a função antiga e a nova foram rodadas lado a lado em 1.342 jogadas (10 de cada jogo + uma inexistente por jogo), com **0 diferenças**.
  - [x] ~~6.4 `snap_formation` via cache de respostas~~ **Cortada.** O cache guarda bytes gzip, não dicionários, então reaproveitar exigiria descomprimir e reler o JSON. Com o `play_tracking` novo (~7 ms), a formação já responde em ~7 ms e nenhum requisito pede mais.
  - [x] 6.5 Testes: `tests/test_tracking.py` (`.npz` corrompido, sem `.npz`, sem `.npz` e sem CSV, 404 rápido).
  - [x] 6.6 `golden.py check`: 2.159/2.159 idênticas.
  - [x] 6.7 **(acrescentada)** Busca e participantes sem `iterrows`. Para fechar o 5.3 com folga e reduzir a CPU por jogada: `players_list` usa `to_dict("records")`, e `play_participants` usa uma tabela estreita por jogo (21 colunas, ordenada por jogada, com índice de faixas) em vez de filtrar a tabela larga de participantes. Busca de 300: 27 → 17 ms; `play()`: 5,2 → 3,5 ms.
  - **Resultado das tarefas 5 e 6:** **todas as metas do `bench.py` passaram.** Tracking no 1º acesso 144 → 30 ms (2.1), jogo já aberto 52 → 8 ms (2.2), busca 25 → 17 ms (5.3). Carga com 10 usuários: **p95 1.502 → 282–288 ms** (meta: 300), 0 recusadas, pico de 321 MB. A folga da carga é pequena (~5%); o custo que sobra é a descompressão do `.npz` (~22 ms por jogo novo), que é o preço aceito na Decisão 1 do design.
  - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 5.3_

- [x] 7. Otimizar o cliente
  - [x] 7.1 `boot()`: as partidas da semana do deep link (ou a 1ª) são pedidas **antes** de esperar o `meta`. Não precisou de `Promise.all`: o `get()` deduplica, e o `renderGames()` recebe a mesma promessa em voo.
  - [x] 7.2 Contadores `seq.play` e `seq.scout`. O `into()` ganhou um parâmetro `atual` que descarta respostas (e erros) atrasadas. `scoutDetail` usa o mesmo contador de `scoutList`, porque os dois desenham no mesmo lugar. Trocar de aba no Treinador também invalida uma prancheta que ainda estava carregando.
  - [x] 7.3 `prefetchVizinhas()`, chamada no fim de `loadFieldPlay`.
  - [x] 7.4 O cache `get()` virou LRU (150 entradas). Além disso, uma falha só apaga a entrada se ela ainda for a mesma promessa.
  - [x] 7.5 Google Fonts com `preload` + `onload` e `<noscript>`.
  - [x] 7.6 A pré-carga que falha é silenciosa. **Correção de bug encontrada no caminho:** ao trocar de jogada com a animação rodando, o timer da jogada anterior continuava mexendo no controle deslizante da nova. Agora ele é pausado.
  - **Medido no navegador:** home pronta em ~38 ms (antes ~340); avançar de jogada em 5–6 ms (antes ~65); abrir a prancheta em 54 ms (antes ~220).
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 4.5, 5.1, 5.2_

- [x] 8. Escrever os testes de navegador
  - _Depende de: 7_
  - [x] 8.1 `tests/test_ui.py` com Playwright 1.63 (`channel="msedge"`, headless): **8 testes**, ~40 s.
  - [x] 8.2 **Desvio:** o atraso e a falha são simulados embrulhando o `fetch` da página (`window.__atraso`, `window.__falharUmaVez`), e não com `page.route()`. O Playwright síncrono não deixa segurar uma resposta e soltá-la depois sem bloquear o teste; o embrulho é determinístico e mais simples. O `page.route()` ficou só para "travar" o Google Fonts (4.5).
  - [x] 8.3 Falha da vizinha (3.3) e fonte travada (4.5).
  - [x] 8.4 Tempos medidos na própria página. A ordem de requisições (3.4) vem do Resource Timing (`startTime` da vizinha ≥ `responseEnd` da escolhida).
  - [x] 8.5 **(acrescentada) Prova de que os testes pegam o defeito:** com as proteções de resposta atrasada desligadas de propósito, os testes 3.2 e 5.2 **falham** (a jogada B sobrescreve a C; o resultado de "ma" substitui o de "mahomes"). Com as proteções ligadas, passam.
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 4.5, 5.1, 5.2_

- [x] 9. Medir o resultado final e documentar
  - _Depende de: 4, 6, 7, 8_
  - [x] 9.1 Tudo rodado e salvo em `tests/golden/resultado_final.txt`: golden 2.159/2.159; pytest 39/39 + lento 1/1; `bench.py --check` com todas as metas ok; carga com 10 usuários em 5 rodadas: **393, 347, 289, 288, 263 ms** (3 de 5 dentro dos 300 ms); 0 erros e 0 recusadas; pico de memória de 329 MB (meta 600).
  - [x] 9.2 **Meta 1.1 instável no teste sem pausa: passava em 3 de 5 rodadas.** Levado ao José, que escolheu a opção 2: **medir o cenário que o requisito descreve**, com uma pausa de 1 a 2 s entre cliques (requirements v0.3). O valor da meta (300 ms) não mudou. `carga.py` ganhou a pausa (semente fixa por sessão) e o modo `--sem-pausa` como estresse sem meta. **Resultado: 5 de 5 rodadas dentro, com p95 de 37–42 ms**, 0 erros e ~300 MB. O código original não foi medido com pausa.
    - Tentativas já feitas nesta tarefa, todas com golden 100%: dados do jogo montados uma vez por jogo, com `.tolist()` por coluna em vez de `to_dict` (CPU da carga 1,24 → 0,99 s). Medido e **descartado**: gravar o `.npz` já ordenado (a reordenação custava só 1,8 ms e os arquivos já estavam em ordem).
    - O que sobra por jogada nova: descomprimir o `.npz` (~25 ms por jogo), `round()` (~2 ms), JSON + gzip (~2 ms). O teste de carga dispara sem pausa entre cliques, e com 10 jogos diferentes abertos no mesmo segundo o GIL enfileira essas descompressões.
  - [x] 9.3 README: seções "Como executar", "Estrutura", "Verificação", "Desempenho" (antes/depois e a nota sobre a meta 1.1) e "Problemas comuns".
  - [x] 9.4 Primeiro uso do zero: `cache/` movido para fora e servidor subido pelo mesmo caminho do `RODAR.bat`. Respondeu em 51 s, com o progresso jogo a jogo, e os agregados regenerados saíram idênticos ao ETL original. **O duplo clique literal fica para o José**, porque abriria o navegador padrão dele.
  - [x] 9.5 **(acrescentada) Correção encontrada ao documentar:** um `.npz` corrompido nunca seria regenerado, porque o `ensure_cache` só confere se o arquivo existe e se o CSV mudou. Agora o servidor apaga o arquivo ruim ao detectá-lo, e o próximo startup o refaz. Coberto em `test_npz_corrompido_cai_no_csv`.
  - [x] 9.6 **(acrescentada) Teste intermitente:** `test_ui_home_pronta_ate_200ms` falhou 1 vez em 7 execuções completas; isolado, passou 4 de 4. O típico é ~40 ms, contra o limite de 200. O limite **não** foi alterado; o teste agora mostra a linha do tempo de cada pedido quando falha, para diagnosticar a próxima ocorrência.
  - _Requisitos: todos_

---

## Mapa de cobertura

| Requisito | Critério | Tarefa | Teste |
|---|---|---|---|
| 1 | 1.1 | 4 | `tools/carga.py --usuarios 10 --check` (p95 ≤ 300 ms) |
| 1 | 1.2 | 2, 4 | `tools/carga.py --usuarios 10 --check` (0 recusadas) |
| 1 | 1.3 | 3, 4 | `test_respostas_concorrentes_iguais_ao_golden` |
| 1 | 1.4 | 2 | `test_api_responde_503_quando_lotado` |
| 1 | 1.5 | 3 | `test_cache_excecao_nao_envenena_nem_bloqueia_outras_chaves` |
| 2 | 2.1 | 6 | `tools/bench.py --check` (tracking primeiro acesso ≤ 60 ms) |
| 2 | 2.2 | 6 | `tools/bench.py --check` (tracking jogo aquecido ≤ 20 ms) |
| 2 | 2.3 | 6 | `tools/golden.py check` (URLs de tracking e formation) |
| 2 | 2.4 | 6 | `test_jogada_sem_tracking_404_rapido` |
| 2 | 2.5 | 6 | `test_npz_corrompido_cai_no_csv`, `test_sem_npz_e_sem_csv_404` |
| 3 | 3.1 | 7, 8 | `test_ui_proxima_jogada_ate_50ms` |
| 3 | 3.2 | 7, 8 | `test_ui_troca_rapida_mostra_so_a_ultima_jogada` |
| 3 | 3.3 | 7, 8 | `test_ui_prefetch_falho_carrega_normal` |
| 3 | 3.4 | 7, 8 | `test_ui_prefetch_so_depois_da_jogada_escolhida` |
| 4 | 4.1 | 7, 8 | `test_ui_home_pronta_ate_200ms` |
| 4 | 4.2 | 4 | `tools/bench.py --check` (detalhe do jogo ≤ 60 ms após aquecimento) |
| 4 | 4.3 | 2 | `test_estatico_revalidado_com_304` |
| 4 | 4.4 | 2 | `test_estatico_alterado_devolve_200_com_etag_nova` |
| 4 | 4.5 | 7, 8 | `test_ui_sem_fontes_externas_renderiza` |
| 5 | 5.1 | 7, 8 | `test_ui_busca_mostra_texto_final` |
| 5 | 5.2 | 7, 8 | `test_ui_busca_resposta_antiga_descartada` |
| 5 | 5.3 | 4 | `tools/bench.py --check` (busca de 300 ≤ 30 ms) |
| 6 | 6.1 | 1, todas | `tools/golden.py check` |
| 6 | 6.2 | 5 | `test_startup_com_cache_pronto_ate_5s` |
| 6 | 6.3 | 5 | `test_primeiro_preparo_ate_90s` (marcado `lento`) + tarefa 9.4 manual |
| 6 | 6.4 | 5 | `test_ensure_cache_jogo_novo`, `..._csv_alterado`, `..._npz_apagado`, `..._versao_diferente`, `..._sem_manifest` |
| 6 | 6.5 | 3, 4 | `tools/carga.py --usuarios 10 --check` (pico ≤ 600 MB) |
| NFR | 1 | 1 | existência de `tools/bench.py` e `tools/carga.py` + tarefa 1.5 |
| NFR | 2 | 4 | `test_api_envia_x_query_time_e_x_cache` |
| NFR | 3 | 5, 9 | tarefa 9.4 (manual: duplo clique no `RODAR.bat`) |
| Segurança | S.1 | 2 | `test_estatico_fora_de_app_403` (`../` e pasta vizinha `app2`) |
| Segurança | S.2 | 2, 4 | `test_parametro_invalido_400_e_nao_entra_no_cache` |
| Segurança | S.3 | 2 | `test_api_responde_503_quando_lotado` |
| Segurança | S.4 | 2 | `test_host_padrao_e_localhost` |

---

## Ordem de execução

```
1 (golden ANTES de tudo)
├── 2 ──┐
├── 3 ──┴── 4 ──┐
├── 5 ── 6 ─────┤
└── 7 ── 8 ─────┴── 9
```

2, 3, 5 e 7 são independentes entre si. A execução segue a numeração para simplificar a revisão e os commits.

---

## Fora desta entrega

- Animação interpolada da prancheta (spec de UX).
- Integração com APIs de outras partidas (spec própria; a tarefa 5 só deixa o terreno pronto).
- Remover ou arquivar o `ui_kiro/`.
- Reescrever `insights` e `_tendencies` (descartado no design, Decisão 2).
- CI no GitHub rodando `pytest` e `golden.py check`. Vale como próxima spec pequena.

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente
- [x] Mapa de cobertura preenchido, incluindo segurança
- [ ] Commit feito antes de iniciar a execução, porque checkpoint não desfaz bash nem MCP (**feito pelo José**)

**Aprovado por:** José Cota em 2026-09-24. O commit fica pendente com a equipe. Decisão do José (2026-09-24): **um único commit ao final da execução**, cobrindo todas as tarefas. O ponto de retorno durante a execução é o próprio golden, que prova, tarefa a tarefa, que nenhuma resposta mudou.
