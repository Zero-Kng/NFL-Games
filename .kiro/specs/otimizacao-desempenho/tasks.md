# Implementation Plan

**Feature:** otimizacao-desempenho
**Status:** aprovado · em execução
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

- [ ] 2. Endurecer a borda HTTP (sem cache ainda)
  - [ ] 2.1 `serve.py`: classe `Server(ThreadingHTTPServer)` com `request_queue_size = 128`.
  - [ ] 2.2 Semáforo `MAX_PENDENTES = 64` (configurável por argumento `--max-pendentes`, para o teste). Sem vaga, a resposta é `503 {"error": "servidor ocupado, tente novamente"}` + `Retry-After: 2`.
  - [ ] 2.3 Trocar `str(target).startswith(...)` por `target.is_relative_to(APP_DIR.resolve())`.
  - [ ] 2.4 Estáticos com `ETag` (sha1 do conteúdo, memorizado por `(caminho, mtime_ns)`) e `Cache-Control: no-cache`. Se `If-None-Match` bater, a resposta é `304` sem corpo.
  - [ ] 2.5 Caminho infeliz: testes de 403 (`/../server/serve.py` e `/../app2/x`), 400 com parâmetro inválido, 503 com `--max-pendentes 1` e uma requisição lenta segurando a vaga.
  - _Requisitos: 1.2, 1.4, 4.3, 4.4, S.1, S.2, S.3, S.4_

- [ ] 3. Implementar o CacheDeRespostas isolado
  - [ ] 3.1 `server/response_cache.py` com `Resposta`, `CacheDeRespostas.get_or_build`, `aquecer` e `stats`, conforme a interface do design.
  - [ ] 3.2 Single-flight: um `threading.Event` por chave em construção. Quem chega depois espera e recebe o mesmo resultado.
  - [ ] 3.3 LRU por bytes do gzip, com limite de 128 MB.
  - [ ] 3.4 Caminho infeliz: `build()` que lança propaga a exceção para todos os que esperavam, não guarda nada, e a chamada seguinte tenta de novo.
  - [ ] 3.5 Testes unitários: 10 threads na mesma chave executam `build` 1 vez; exceção sem envenenar o cache; despejo por LRU quando passa do limite; chaves diferentes não se bloqueiam.
  - _Requisitos: 1.3, 1.5, 6.5_

- [ ] 4. Ligar o cache nas rotas da API e aquecer no startup
  - _Depende de: 2, 3_
  - [ ] 4.1 `_handle_api`: validação (já existente) → chave normalizada (rota + parâmetros **conhecidos** ordenados) → `get_or_build` → envia o gzip pronto. Se o cliente não aceita gzip, descomprime na hora. Cabeçalhos `X-Cache: HIT|MISS` e `X-Query-Time`.
  - [ ] 4.2 Só respostas 200 entram no cache. `ApiError` (400/404) atravessa sem ser guardado.
  - [ ] 4.3 `aquecer()` em thread daemon depois que o servidor começa a escutar, na ordem: `meta`, `games` por semana, e `game`/`plays`/`broadcast` dos 122 jogos (semana 1 primeiro). Loga o início, o fim e a duração.
  - [ ] 4.4 Caminho infeliz: se uma tarefa do aquecimento falhar, loga e segue para a próxima (o servidor não cai).
  - [ ] 4.5 Rodar `golden.py check` (tem que passar 100%) e `carga.py --usuarios 10`, e anotar o resultado parcial no `linha_de_base.txt`.
  - _Requisitos: 1.1, 1.3, 1.5, 4.2, 5.3, NFR 2_

- [ ] 5. Tornar a preparação de dados incremental e gerar o tracking binário
  - [ ] 5.1 `etl/build_metrics.py`: `ETL_VERSION = 2`, `ensure_cache()` e `Relatorio`. Um jogo é processado se for novo, se o tamanho ou mtime do CSV mudou, se faltar alguma parte ou se `etlVersion` mudou.
  - [ ] 5.2 Por jogo, grava `cache/parts/<id>.timing.csv`, `cache/parts/<id>.motion.csv` e `cache/tracking/<id>.npz` (`savez_compressed`, float64, texto em unicode numpy). A gravação é atômica: escreve em `*.tmp` e renomeia.
  - [ ] 5.3 Se algum jogo mudou, reconcatena `play_timing.csv` e `player_play.csv` a partir das partes, com o **mesmo formato de hoje** (`float_format="%.3f"`, mesma ordem de linhas).
  - [ ] 5.4 `manifest.json` gravado por último. Uma interrupção no meio faz o próximo startup refazer só o que faltou.
  - [ ] 5.5 `serve.py` chama `ensure_cache()` antes de `NFLData`. O progresso aparece no terminal. `RODAR.bat` deixa de testar `cache\play_timing.csv` e só sobe o servidor. `--force` continua funcionando.
  - [ ] 5.6 Caminho infeliz: testes com uma pasta temporária de 2 jogos pequenos (jogo novo processa só ele; CSV alterado reprocessa só ele; `.npz` apagado é regenerado; `etlVersion` diferente reprocessa tudo; `manifest.json` ausente reprocessa tudo).
  - [ ] 5.7 Medir o primeiro preparo completo (122 jogos) do zero. Se passar de 90 s, paralelizar por jogo com `ProcessPoolExecutor` dentro desta mesma tarefa.
  - _Requisitos: 6.2, 6.3, 6.4, NFR 3, restrição de novas fontes de partidas_

- [ ] 6. Ler o tracking do `.npz` e montar a resposta da jogada sem `iterrows`
  - _Depende de: 5_
  - [ ] 6.1 `_tracking_for_game`: carrega `cache/tracking/<id>.npz` com `allow_pickle=False` e guarda no LRU (que passa de 6 para 12 jogos), junto com um índice `playId → fatia de linhas`.
  - [ ] 6.2 Caminho infeliz: `.npz` ausente ou ilegível loga `[aviso]` e cai no CSV original. Se o CSV também faltar, a função retorna `None` e a rota responde 404.
  - [ ] 6.3 `play_tracking`: montagem com numpy (ordenar por `nflId, frameId`, posição de cada quadro por `searchsorted`) e arredondamento final com `round()` do Python sobre `.tolist()`. O timing é buscado num `dict {(gameId, playId): (snapFrame, releaseFrame)}` montado no `_load`.
  - [ ] 6.4 `snap_formation` passa a usar o resultado de `play_tracking` através do cache (a mesma chave da rota de tracking).
  - [ ] 6.5 Testes: `.npz` corrompido cai no CSV com a mesma resposta; sem `.npz` e sem CSV dá 404; jogada sem tracking dá 404 em até 20 ms.
  - [ ] 6.6 `golden.py check` precisa passar 100%. Aqui é onde o risco de mudar uma casa decimal é maior.
  - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 7. Otimizar o cliente
  - [ ] 7.1 `boot()`: `api.meta()` e `api.games({week})` em paralelo (`Promise.all`). A semana do deep link é lida da URL antes, então as duas chamadas são independentes.
  - [ ] 7.2 Contadores `seq.play` e `seq.scout`: `coachLineup`/`loadFieldPlay` e `scoutList` descartam a resposta se o contador mudou enquanto esperavam.
  - [ ] 7.3 `prefetchVizinhas()`: chamada no fim de `loadFieldPlay`, depois do desenho. Pede as jogadas anterior e seguinte com tracking, no máximo 2 pedidos em voo, e `.catch(() => {})`.
  - [ ] 7.4 O cache `get()` vira LRU com no máximo 150 entradas (uma `Map` reinserida a cada acesso).
  - [ ] 7.5 `index.html`: Google Fonts com `rel="preload" as="style" onload="this.rel='stylesheet'"` e `<noscript>` de fallback.
  - [ ] 7.6 Caminho infeliz: a pré-carga que falha não mostra nada ao usuário. Se a jogada escolhida estiver em pré-carga, reusa a mesma promessa (o `get()` já deduplica).
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 4.5, 5.1, 5.2_

- [ ] 8. Escrever os testes de navegador
  - _Depende de: 7_
  - [ ] 8.1 `tests/test_ui.py` com Playwright (`channel="msedge"`, headless) contra a fixture `servidor`.
  - [ ] 8.2 Atraso simulado com `page.route()`: segurar a 1ª resposta de tracking ou de busca por 800 ms e liberar a 2ª imediatamente. Assim se provam o 3.2 e o 5.2 sem depender de sorte.
  - [ ] 8.3 Falha simulada: `page.route()` aborta o tracking da vizinha e depois clica em "próxima" (3.3). Bloqueia `fonts.googleapis.com` e confere o render (4.5).
  - [ ] 8.4 Tempos com `performance.now()` no próprio page (4.1 e 3.1) e ordem de requisições por `page.on("request")` (3.4).
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 4.5, 5.1, 5.2_

- [ ] 9. Medir o resultado final e documentar
  - _Depende de: 4, 6, 7, 8_
  - [ ] 9.1 Rodar, nesta máquina: `golden.py check`, `pytest`, `bench.py --check` e `carga.py --usuarios 10 --check`. Anexar a saída em `tests/golden/resultado_final.txt` ao lado da linha de base.
  - [ ] 9.2 Se alguma meta falhar: **não afrouxar a meta**. Registrar no `design.md` (Riscos) o que faltou e parar para decidir com o José.
  - [ ] 9.3 README: seção "Desempenho" (tabela antes/depois); nota sobre os ~123 MB de `cache/tracking/`; `requirements-dev.txt` e como rodar os testes; o `RODAR.bat` simplificado.
  - [ ] 9.4 Teste manual do NFR 3: apagar `cache/`, dar duplo clique no `RODAR.bat`, ver o progresso e abrir o app.
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

**Aprovado por:** José Cota em 2026-09-24. O commit fica pendente com a equipe. A tarefa 1 só cria arquivos novos e pode rodar antes dele; **a tarefa 2 em diante só começa depois do commit.**
