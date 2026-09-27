# Implementation Plan

**Feature:** site-publico
**Status:** em revisão
**Data:** 2026-09-27

> **Para agentes:** sub-skill obrigatória: superpowers:subagent-driven-development (recomendada) ou superpowers:executing-plans, tarefa por tarefa. Os passos usam caixas (`- [ ]`) para acompanhar.

**Objetivo:** publicar a interface atual (`app/`) no GitHub Pages, com os dados exportados em arquivos e atualizados todo dia, tão funcional quanto o app do PC.

**Arquitetura:** `tools/exportar.py` grava as respostas da `NFLData` em `site/api/{versao}/`. O `api.js` troca de fonte quando o `index.html` tem `<meta name="nfl-dados" content="estatico">`. A `fonte-estatica.js` lê os arquivos e refaz no navegador só a semana atual, o status, o filtro de jogadores e a comparação. Um workflow do Actions sincroniza, monta, exporta e publica no Pages.

**Tecnologia:** Python 3.12 (pandas, numpy), JS de módulos ES sem build, `DecompressionStream`, pytest com Playwright e Edge, GitHub Actions (`upload-pages-artifact`, `deploy-pages`).

**Spec:** `.kiro/specs/site-publico/requirements.md` e `design.md`. Leia os dois antes de cada tarefa.

## Restrições globais

- Endereço: `https://zero-kng.github.io/NFL-Games/`. O site roda **no subcaminho** `/NFL-Games/`, então nenhum caminho da fonte estática pode começar com `/`.
- Temporadas 2021 a 2026, temporada regular e playoffs.
- **O visual não muda**: nenhum arquivo de `app/css/` e nenhum texto das telas, exceto as duas mensagens abaixo.
- Mensagem de abertura no site (4.3), exata: `Não foi possível carregar os dados. Verifique a conexão e tente de novo.`
- Mensagem sem `DecompressionStream` (4.2), exata: `Este navegador não consegue abrir os dados do jogo. Atualize o navegador (no iPhone, iOS 16.4 ou mais novo).`
- Mensagens de 404 e 400 iguais às do servidor, byte a byte, sem acento como lá:
  - `jogo {id} nao encontrado`
  - `formacao indisponivel para esta jogada`
  - `jogo nao encontrado ou ainda sem jogadas`
  - `jogador sem dados na temporada`
  - `um dos jogadores nao tem dados na temporada`
  - `informe os parametros 'a' e 'b' com os ids dos jogadores`
  - `temporada {ano} indisponivel (ha {min} a {max})`
- Limites: Pages ≤ 1 GB (RNF 1); até a Início pronta ≤ 1 MB transferido (RNF 2); abrir um jogo com a 1ª prancheta ≤ 400 KB (RNF 3); publicação diária ≤ 30 min (RNF 4).
- Workflow com `permissions: {contents: read, pages: write, id-token: write}` e nada além.
- **Um commit por tarefa**, mensagem em português, **sem linha de coautoria**. Push e PR só quando o José pedir.
- Toda tarefa que mexe no servidor termina com `python tools/golden.py check` 100% e `pytest` passando.
- Ao fim de toda tarefa que mexe em `app/` ou `server/`: regenerar o `NFL-Games.exe` da raiz (`python tools/empacotar.py`, mover `dist/NFL-Games.exe` para a raiz e apagar `dist/`) e conferir que ele sobe.

## Foco de revisão

Situações que a spec implica e que um usuário real vai encontrar. Cada uma tem teste na tarefa dona:

1. **O Pages entregar o `.gz` com `Content-Encoding: gzip`** (o navegador já descompacta): o jogo tem de abrir do mesmo jeito. Teste na tarefa 3 (`test_gz_com_content_encoding`).
2. **Celular em outro fuso** (Brasília, 23h30 de uma quinta de jogo, quando em Nova York ainda é o mesmo dia): semana atual e status iguais aos do servidor. Teste na tarefa 3 (`test_fuso_do_aparelho_nao_muda_semana_nem_status`).
3. **Busca com acento, apóstrofo e maiúsculas** (`ja'marr`, `JOSÉ`, `é`, espaço no fim): mesmos jogadores e ordem que o servidor. Teste na tarefa 3 (`test_busca_igual_ao_servidor`).
4. **Link antigo ou digitado errado** (`?season=2019`, `?game=123`, `?jogador=xx`): a mesma mensagem do PC, sem erro de JavaScript. Teste na tarefa 3 (`test_404_iguais_ao_servidor`) e na 5 (a bateria já abre esses links).
5. **Jogo futuro ou sem jogadas** (bundle com `plays: []` e `broadcast: null`, pranchetas `{}`): a tela Jogo mostra o mesmo estado vazio do PC. Teste na tarefa 2 (`test_jogo_futuro_exportado`) e na 3 (`test_jogo_futuro_igual_ao_servidor`).

---

## Tarefas

- [x] 1. Ordenação estável da lista de jogadores no servidor
  - **Arquivos:** modificar `server/data_layer.py` (`players_list`, o `sort_values`); teste em `tests/test_servidor_dados.py`.
  - **Produz:** `NFLData.players_list` com empates de `rating` e `volume` na ordem da tabela `t.jogadores`. A tarefa 2 grava a lista completa nessa ordem.
  - [x] 1.1 Escrever `test_players_list_empates_na_ordem_da_tabela`:
    - para 2021, pega a tabela `t.jogadores` (avaliados);
    - ordena com `sort_values(["rating", "volume"], ascending=[False, False], na_position="last", kind="stable")`;
    - confere que `players_list(2021, limit=300)` devolve os `nflId` nessa ordem.
    - Repete com `rated_only=False` e com `position="WR"`.
  - [x] 1.2 Rodar `pytest tests/test_servidor_dados.py -k empates -v`. Esperado: FAIL, ou PASS por sorte. Se passar, confirmar que o teste compara listas com pelo menos um empate (`assert` de que existe empate).
  - [x] 1.3 Acrescentar `kind="stable"` ao `sort_values` de `players_list`.
  - [x] 1.4 Rodar `pytest tests/test_servidor_dados.py -v` e `python tools/golden.py check`.
    - Esperado: PASS e 2116/2116.
    - Se o golden acusar diferença: conferir à mão que é só ordem entre empatados, registrar aqui quais URLs mudaram, recapturar com `python tools/golden.py capture` e rodar o `check` de novo.
  - [x] 1.5 Commit: `Lista de jogadores com ordenação estável: empatados ficam na ordem da tabela (site-publico, tarefa 1)`.
  - **Feito (2026-09-27):** o teste passou já na 1ª execução, com empates reais nos três casos. Motivo: o pandas ignora `kind` ao ordenar por várias colunas e usa sempre um método estável. O código do servidor não mudou (só um comentário registrando a dependência); o teste fica como garantia. Golden não se aplica (nenhuma resposta mudou).
  - _Requisitos: 2.2_

- [x] 2. Exportador `tools/exportar.py`
  - **Arquivos:** criar `tools/exportar.py`; teste em `tests/test_exportar.py`; `.gitignore` ganha `site/`.
  - **Consome:** `NFLData(dados: Path, hoje=None)` e os métodos `meta`, `games_list`, `game`, `game_plays`, `broadcast`, `play_tracking`, `players_list`, `player`, `news` e `summary` (`server/data_layer.py`).
  - **Produz:**
    - `exportar(dados: Path, saida: Path, temporadas: set[int] | None = None, processos: int = 4, agora: datetime | None = None) -> str`: devolve a versão `AAAAMMDDTHHMM`, em UTC.
    - `verificar(saida: Path, limite_bytes: int = 1_000_000_000) -> list[str]`: lista de problemas; vazia quando está tudo certo.
    - `gravar_json(caminho: Path, obj, gz: bool = False) -> None`: escrita atômica (`.tmp` e depois `os.replace`), com `json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))`.
    - CLI `python tools/exportar.py [--saida site] [--dados dados] [--processos 4] [--temporadas 2021,2026]`: sai com código 1 se `verificar` achar problema.
    - A estrutura de arquivos é a do Data Model do design. O bundle do jogo tem as chaves `game`, `plays` e `broadcast` (`null` se não houver).
    - As pranchetas saem como um dicionário `{"<playId>": tracking}`, só com os lances que têm prancheta. **Todo jogo** da temporada ganha os dois arquivos, inclusive os futuros (`plays: []`, pranchetas `{}`).
    - `jogadores.json` é `players_list(ano, rated_only=False, limit=10**6)`.
    - Os perfis saem para todo `nflId` de `t.jogadores.index`.
  - [x] 2.1 Escrever os testes em `tests/test_exportar.py`. Uma fixture de módulo exporta `--temporadas 2021` para uma pasta temporária, com `processos=4`. Testes:
    - `test_versao_e_marca`: `api/versao.json` tem `versao` no formato `\d{8}T\d{4}`; `index.html` contém `<meta name="nfl-dados" content="estatico">`; `css/app.css` e `js/api.js` existem.
    - `test_meta_igual_ao_servidor`: `meta.json` é igual a `NFLData.meta()`.
    - `test_semanas_iguais_ao_servidor`: toda semana de 2021 é igual a `games_list(2021, semana)`.
    - `test_jogos_iguais_ao_servidor`: em 20 jogos de 2021, o `.gz` descompactado tem `game`, `plays` e `broadcast` iguais aos do `NFLData`, e as pranchetas iguais a `play_tracking` lance a lance.
    - `test_jogadores_e_perfis`: `jogadores.json` igual a `players_list(2021, rated_only=False, limit=10**6)`; 50 perfis iguais a `player(id, 2021)`; o número de arquivos em `jogadores/` é igual a `len(t.jogadores.index)`.
    - `test_noticias_e_resumo`: `noticias.json`, cada `noticias/{semana}.json` e `resumo.json` iguais a `news` e `summary`.
    - `test_jogo_futuro_exportado`: exportando `--temporadas 2026`, um jogo com `status == "agendado"` tem `plays == []`, `broadcast is None` e pranchetas `{}`. Com o foco de revisão 5, esse vale a espera.
    - `test_verificar_acusa_problemas`: `verificar` numa cópia sem `meta.json` e com `limite_bytes=1` devolve dois problemas; na exportação boa, `[]`.
    - `test_gravacao_atomica`: depois de exportar, nenhum `*.tmp` sobra em `saida`.
    - Os campos `status` e `currentWeek` são comparados com o `NFLData` criado com o mesmo `hoje` passado ao exportar (`agora`).
  - [x] 2.2 Rodar `pytest tests/test_exportar.py -v`. Esperado: FAIL (`ModuleNotFoundError: exportar`).
  - [x] 2.3 Implementar `tools/exportar.py`.
    - Os jogos são divididos em `processos` fatias, com `concurrent.futures.ProcessPoolExecutor`. Cada processo cria o próprio `NFLData`.
    - O processo principal copia `app/` (sem `__pycache__`), injeta a marca antes de `</head>` e grava `meta`, `versao`, semanas, jogadores, perfis, notícias e resumo.
    - Com `temporadas`, o `meta.json` continua completo.
  - [x] 2.4 Rodar `pytest tests/test_exportar.py -v`. Esperado: PASS.
  - [x] 2.5 Exportar tudo (`python tools/exportar.py --saida site`) e anotar aqui o tempo e o tamanho total, contra ~6 min e ~200 MB do design. `verificar` tem de sair sem problemas.
  - [x] 2.6 Commit: `Exportador do site: respostas da API em arquivos, com os jogos em gzip (site-publico, tarefa 2)`.
  - **Feito (2026-09-27):** `tests/test_exportar.py`, 10 testes. Exportação completa: **272 s com 4 processos, 156 MB, 15.607 arquivos** (design: ~6 min e ~200 MB); verificação sem problemas.
    - O `meta.json` é comparado sem a `ultimaAtualizacao`: ela vem do `dados/manifest.json` lido na hora, e um app aberto que sincroniza durante o teste a muda.
    - O `versao.json` é gravado por último, para só apontar para uma exportação completa.
  - _Requisitos: 1.3, 2.1, 3.2 (base), RNF 1, segurança 1_

- [ ] 3. Fonte estática no navegador
  - **Arquivos:**
    - criar `app/js/fonte-estatica.js`;
    - modificar `app/js/api.js` (a troca de fonte e o leitor opcional no `get`);
    - modificar `app/js/main.js` (a mensagem de abertura);
    - criar `tools/servidor_estatico.py`;
    - `tests/conftest.py` ganha as fixtures `site_exportado` e `site`;
    - testes em `tests/test_fonte_estatica.py`.
  - **Consome:** a pasta gerada por `exportar(...)` (tarefa 2).
  - **Produz:**
    - Em `api.js`:
      - `export const ESTATICO: boolean`;
      - `get(path, ler = (res) => res.json())`: o mesmo cache de sessão, com a chave `path`;
      - `api`, com as mesmas 11 funções de hoje.
    - Em `fonte-estatica.js`:
      - `export function fonteEstatica({ get, buscar = fetch, agora = () => Date.now(), recarregar = () => location.reload() })`: devolve o objeto `api`.
      - Funções puras exportadas para teste:
        - `semanaAtual(semanas, agoraMs) -> number | null`, com a Regra A;
        - `statusDoJogo(card, agoraMs) -> string`, com a Regra B;
        - `filtrarJogadores(lista, {q, position, role, team, rated, limit}) -> lista`, com a Regra C;
        - `juntarComparacao(pa, pb, ano) -> objeto`, com a Regra D;
        - `lerGz(resposta: Response) -> Promise<any>`: descompacta só se começar com `1f 8b` e lança a mensagem 4.2 se faltar `DecompressionStream`.
    - Em `tools/servidor_estatico.py`: `site_local(raiz: Path, prefixo: str = "/NFL-Games/", gz_como_encoding: bool = False) -> ContextManager[str]`. Devolve a URL base sem barra final (`http://127.0.0.1:{porta}/NFL-Games`). Com `gz_como_encoding=True`, serve os `.gz` com `Content-Encoding: gzip`.
    - Em `tests/conftest.py`:
      - `site_exportado`, de sessão: devolve o `Path` de `build/site-testes/NFL-Games`, exportado com `processos=4`. A exportação é reaproveitada enquanto a chave (sha256 de `dados/manifest.json`, `tools/exportar.py`, `server/*.py`, `etl/ratings.py` e `app/**`) for a mesma, gravada em `build/site-testes/chave.txt`.
      - `site`, de sessão: a URL do `site_local(site_exportado.parent)`.
  - **Regras:** as quatro regras são as do componente 3 do design. A temporada ausente de `meta.seasons` lança 404 com a mensagem de temporada indisponível, antes de ler qualquer arquivo.
    - `plays` de um jogo inexistente devolve `[]`, como o servidor.
    - `game` de um jogo inexistente dá 404 `jogo {id} nao encontrado`.
    - `broadcast` dá 404 quando o bundle não existe ou quando traz `null`.
  - [ ] 3.1 Escrever `tests/test_fonte_estatica.py`. Cada teste abre `site` no Edge e chama a fonte pela página:
    - chamada: `await (await import(new URL('js/api.js', document.baseURI).href)).api.X(...)`;
    - comparação: com o `NFLData(dados, hoje=H)`, sendo `H` o mesmo instante do `page.clock.set_fixed_time(H)`.

    Testes:
    - `test_meta_semana_atual`: `H` em três momentos. Antes do 1º jogo de 2026, a primeira semana. Numa quinta de rodada, 21h em Nova York, a semana da quinta. Numa terça, a semana anterior. `meta().currentWeek` e o de cada temporada iguais aos do servidor.
    - `test_status_antes_durante_depois`: para uma semana de 2026 com jogos sem placar, `games(2026, s)` e `game(id)` iguais ao servidor com `H` uma hora antes do início e uma hora depois.
    - `test_busca_igual_ao_servidor`: para 2021 e 2025, a lista de ids igual a `players_list` com:
      - `{q:'ma', limit:8}`, `{q:"ja'marr"}`, `{q:'JOSÉ'}`, `{q:'é'}`, `{q:'smith '}`;
      - `{position:'QB', limit:60}`, `{position:'WR,TE', q:'a', limit:60}`;
      - `{role:'EDGE', limit:60}`, `{team:'kc'}`, `{rated:0, limit:300}`, `{limit:500}` (máximo 300).
    - `test_comparacao_igual_ao_servidor`: dois QBs, um QB com um WR, e um id inexistente (404 com a mensagem exata). Sem `b`, 400 com a mensagem exata.
    - `test_404_iguais_ao_servidor`:
      - `game(123)`, `tracking(jogo, 999999)`, `player('00-0000000', 2021)`, `games(2019, 1)` e `broadcast` de um jogo futuro dão o mesmo `status` e a mesma mensagem do servidor;
      - `plays(123)` devolve `[]`.
    - `test_jogo_futuro_igual_ao_servidor`: `game`, `plays` e `broadcast` de um jogo `agendado` de 2026 iguais ao servidor, ou com o mesmo erro.
    - `test_jogo_e_pranchetas_iguais`: para 3 jogos de 2025, `game`, `plays`, `broadcast` e 5 `tracking` iguais ao servidor. O arquivo de pranchetas é pedido uma vez só (contar os pedidos com `page.on("request")`).
    - `test_gz_com_content_encoding`: com `site_local(..., gz_como_encoding=True)`, `plays(id)` igual ao servidor.
    - `test_sem_decompressionstream`: com `add_init_script("delete window.DecompressionStream")`, `plays(id)` rejeita com a mensagem 4.2, e `meta()` e `players(...)` funcionam.
    - `test_fuso_do_aparelho_nao_muda_semana_nem_status`: contexto com `timezone_id="America/Sao_Paulo"` e `H` = quinta de rodada às 23h30 em Brasília. `meta().currentWeek` e o `status` iguais aos do servidor com o mesmo `H`.
    - `test_caminhos_relativos`: nenhum pedido da página vai para fora de `/NFL-Games/`, exceto as fontes do Google e a ESPN (conferido com `page.on("request")`).
    - `test_mensagem_de_abertura`: com `api/versao.json` respondendo 404 (via `route`), a tela mostra exatamente a mensagem 4.3.
  - [ ] 3.2 Rodar `pytest tests/test_fonte_estatica.py -v`. Esperado: FAIL, porque ainda não existe fonte estática. A primeira execução exporta o site, o que leva alguns minutos.
  - [ ] 3.3 Implementar `tools/servidor_estatico.py`, com `ThreadingHTTPServer` numa thread e porta livre de `servidor_local.porta_livre`, e as fixtures do conftest.
  - [ ] 3.4 Implementar `fonte-estatica.js`, a troca em `api.js` e a mensagem em `main.js`.
    - A fonte lê `api/versao.json` com `buscar(url, {cache: 'no-store'})` e guarda a promessa da versão. Todo caminho é `api/{versao}/...`.
    - Os bundles de jogo e de pranchetas passam pelo `get(path, lerGz)`, o que dá o cache de sessão de graça.
    - Na mensagem da abertura, `main.js` usa `ESTATICO` para escolher o texto. A espera por 503 segue só para `!ESTATICO`.
  - [ ] 3.5 Rodar `pytest tests/test_fonte_estatica.py -v`. Esperado: PASS.
  - [ ] 3.6 Rodar a bateria atual no PC: `pytest tests/test_ui.py tests/test_ui_dados.py tests/test_ui_novo.py -q`. Esperado: os 155 passam, porque nada mudou para a fonte `servidor`.
  - [ ] 3.7 Regenerar o `.exe` da raiz e conferir que ele sobe.
  - [ ] 3.8 Commit: `Fonte estática: a interface lê os arquivos exportados quando está no site (site-publico, tarefa 3)`.
  - _Requisitos: 1.2, 2.1–2.6, 4.2, 4.3, segurança 3 e 4_

- [ ] 4. Troca de versão no meio do uso
  - **Arquivos:** modificar `app/js/fonte-estatica.js`; teste em `tests/test_fonte_estatica.py`.
  - **Consome:** `fonteEstatica({ ..., recarregar })` e `site_local` (tarefa 3).
  - **Produz:** comportamento. Num 404, relê `api/versao.json` com `cache: 'no-store'`. Se a versão mudou, chama `recarregar()` e devolve uma promessa que não resolve, para a tela não piscar um erro. Senão, lança o 404 com a mensagem da rota.
  - [ ] 4.1 Escrever `test_versao_nova_recarrega_no_mesmo_lugar`:
    - copia o site exportado para uma pasta temporária e abre `?screen=jogo&season=2025&week=1&game={id}`;
    - com a página aberta, renomeia `api/{v}` para `api/{v2}` e grava `versao.json` com `v2`;
    - troca de aba para "jogadas" e espera o `load` de uma navegação nova;
    - confere que a URL é a mesma, que as jogadas aparecem e que todos os pedidos depois da recarga usam `api/{v2}/`.
  - [ ] 4.2 Escrever `test_404_de_verdade_nao_recarrega`: `player('00-0000000', 2021)` rejeita com `jogador sem dados na temporada`, e `recarregar` não é chamado. Conferir com `fonteEstatica({get, recarregar: () => window.__recarregou = true})`, montada na página.
  - [ ] 4.3 Rodar os dois testes. Esperado: FAIL no 4.1.
  - [ ] 4.4 Implementar a checagem de versão no caminho de erro da fonte.
  - [ ] 4.5 Rodar `pytest tests/test_fonte_estatica.py -v`. Esperado: PASS.
  - [ ] 4.6 Regenerar o `.exe` da raiz e conferir que ele sobe.
  - [ ] 4.7 Commit: `Site recarrega sozinho quando sai uma versão nova dos dados, sem misturar dias (site-publico, tarefa 4)`.
  - _Requisitos: 3.5, 4.4_

- [ ] 5. A bateria de interface nas duas fontes
  - **Arquivos:**
    - modificar `tests/test_ui.py`, `tests/test_ui_dados.py` e `tests/test_ui_novo.py`;
    - `tests/conftest.py` ganha `Alvo` e `simular_api`;
    - `pytest.ini` registra a marca `so_servidor`.
  - **Consome:** as fixtures `servidor` (de hoje), `site_exportado` e `site` (tarefa 3).
  - **Produz:**
    - Nos três módulos, a fixture `servidor` passa a ser parametrizada com `["servidor", "estatico"]`. Ela devolve `Alvo(url: str, api: str, fonte: str)`:
      - `url` é a base da página (o servidor ou o site);
      - `api` é sempre a URL do servidor real, a referência dos dados.
    - Os ids dos testes ganham o sufixo `[servidor]` ou `[estatico]`.
    - `simular_api(pg, alvo, rotas: dict[str, object])`:
      - cada chave é uma rota da API como a interface a pede (`"/api/games?season=2021&week=1"`, ou com `*` como os `route` de hoje);
      - cada valor é o corpo JSON ou um status HTTP;
      - na fonte `servidor`, vira `pg.route` como hoje;
      - na `estatico`, traduz para o arquivo do Data Model. Nos jogos, junta as sobrescritas de `game` e `plays` sobre o bundle real, gzipado.
    - A marca `so_servidor(motivo: str)` pula o teste na fonte `estatico`.
  - [ ] 5.1 Trocar nos três módulos:
    - `api(servidor.url, ...)` e `urlopen(f"{base}/api...")` por `servidor.api`;
    - todo `pg.route("**/api/...")` por `simular_api`;
    - `fetch('/api/meta')` e `import('/js/...')` dentro de `evaluate` pela API da página, com URL relativa a `document.baseURI`.
  - [ ] 5.2 Trocar em `test_ui_busca_corta_em_100_caracteres` a observação do pedido de rede por um espião em `api.players`: substituir a função no objeto `api` importado e guardar o `q`. Assim o teste vale nas duas fontes.
  - [ ] 5.3 Marcar `so_servidor`, cada um com o motivo na marca, e listar aqui ao terminar:
    - os testes da tela de carregamento (`_simular_carga`);
    - `test_ui_troca_rapida_mostra_so_a_ultima_jogada`, `test_ui_prefetch_falho_carrega_normal`, `test_ui_prefetch_so_depois_da_jogada_escolhida` e `test_ui_busca_resposta_antiga_descartada`, que dependem de um pedido por prancheta ou por busca.
  - [ ] 5.4 Rodar `pytest tests/test_ui.py tests/test_ui_dados.py tests/test_ui_novo.py -q`.
    - Esperado: todos passam nas duas fontes, e os pulados são só os de 5.3.
    - Qualquer outra falha em `[estatico]` é defeito do site: corrigir na `fonte-estatica.js`, com teste na `test_fonte_estatica.py`, e nunca marcar `so_servidor` para esconder.
  - [ ] 5.5 Rodar a suíte inteira: `pytest -q`. Esperado: tudo passa.
  - [ ] 5.6 Regenerar o `.exe` da raiz, se alguma correção tocou `app/`.
  - [ ] 5.7 Commit: `Testes de interface rodam contra o PC e contra o site (site-publico, tarefa 5)`.
  - _Requisitos: 1.6, 1.7, 2.1_

- [ ] 6. Publicação diária no Pages
  - **Arquivos:**
    - criar `.github/workflows/pages.yml`;
    - modificar `README.md`: seção "Abrir no celular", com o link, como adicionar à tela inicial, a atualização diária e o que fazer se o GitHub pausar o agendamento; também a árvore de pastas, com `tools/exportar.py` e `site/`;
    - `requirements-dev.txt` ganha `pyyaml>=6` (para o teste ler o workflow);
    - teste em `tests/test_infra.py`.
  - **Consome:** a CLI da tarefa 2 (`python tools/exportar.py --saida site --processos 4`).
  - **Produz:** o workflow do componente 6 do design, exatamente com os gatilhos, as permissões, o `concurrency` e os passos listados lá.
  - [ ] 6.1 Escrever `test_workflow_pages` em `tests/test_infra.py`, lendo o YAML com `yaml.safe_load` (instalar antes: `python -m pip install -r requirements-dev.txt`). Confere:
    - o cron `0 10 * * *`;
    - o `push` na `main` com os `paths` do design;
    - o `workflow_dispatch`;
    - `permissions == {contents: read, pages: write, id-token: write}`;
    - `concurrency.group == "pages"`;
    - os passos em ordem: `montar.py`, `exportar.py`, `upload-pages-artifact` com `path: site` e `deploy-pages`;
    - nenhum passo com `git push` ou `contents: write`.
  - [ ] 6.2 Rodar `pytest tests/test_infra.py -k pages -v`. Esperado: FAIL.
  - [ ] 6.3 Escrever o workflow e a seção do README.
  - [ ] 6.4 Rodar `pytest tests/test_infra.py -v`. Esperado: PASS.
  - [ ] 6.5 Commit: `Workflow de publicação diária no GitHub Pages e instruções para abrir no celular (site-publico, tarefa 6)`.
  - [ ] 6.6 Avisar o José que a branch está pronta para a PR. O deploy só roda depois do merge na `main`, porque o ambiente `github-pages` só aceita a branch padrão.
  - _Requisitos: 1.1, 1.4, 3.1–3.4, 3.6, RNF 4, RNF 5, segurança 1 e 2_

- [ ] 7. Primeiro deploy e medições
  - _Depende de: merge da PR na `main` (feito pelo José)_
  - [ ] 7.1 Acompanhar a primeira execução do workflow, disparada pelo push do merge, com `gh run watch`. Anotar aqui o tempo total, contra o limite de 30 min (RNF 4).
  - [ ] 7.2 Abrir `https://zero-kng.github.io/NFL-Games/` no navegador em 375 × 812, com o cache vazio. Medir, pela `performance.getEntriesByType('resource')` (`transferSize`):
    - o total até a Início pronta, contra 1 MB (RNF 2);
    - o total ao abrir um jogo e tocar num lance, contra 400 KB (RNF 3).
  - [ ] 7.3 No site publicado, conferir se os `.gz` chegam com `Content-Encoding`, e anotar. As duas formas funcionam (foco de revisão 1).
  - [ ] 7.4 Percorrer as telas no site publicado: trocar semana, abrir jogo, prancheta, replay, perfil, comparação, busca, notícias, configurações e "Sobre os dados". Tirar capturas.
  - [ ] 7.5 Gerar um QR code do link para o José e pedir que ele teste no celular.
  - [ ] 7.6 Se algum RNF falhar: registrar aqui, corrigir numa tarefa nova e voltar a 7.1.
  - _Requisitos: 1.1, 1.4, RNF 1–4_

---

## Ordem de execução

```
1 ── 2 ── 3 ── 4 ── 5 ── 6 ─(merge)─ 7
```

Cada tarefa depende da anterior. A 1 vem primeiro porque o exportador grava a lista de jogadores na ordem estável.

---

## Mapa de cobertura

| Requisito | Tarefas |
|---|---|
| 1.1, 1.4 | 6, 7 |
| 1.2 | 3 |
| 1.3 | 2 |
| 1.5 | 3 (3.6), 5 |
| 1.6, 1.7 | 5 |
| 2.1 | 2, 3, 5 |
| 2.2 | 1, 3 |
| 2.3 | 3 |
| 2.4, 2.5 | 3 |
| 2.6 | 3, 5 |
| 3.1–3.4 | 6 |
| 3.5 | 4 |
| 3.6 | 2 (o `meta.json` traz `ultimaAtualizacao`), 5 (o teste da tela "Sobre os dados" roda no site) |
| 4.1 | 5 (os testes de erro da bateria rodam no site) |
| 4.2, 4.3 | 3 |
| 4.4 | 4 |
| RNF 1 | 2, 7 |
| RNF 2, RNF 3 | 7 |
| RNF 4 | 2 (medição local), 7 |
| RNF 5 | 6 |
| Segurança 1 | 2, 6 |
| Segurança 2 | 6 |
| Segurança 3 | 5 (o teste de XSS roda no site) |
| Segurança 4 | 3 |

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente
- [x] Mapa de cobertura preenchido, incluindo segurança
- [x] Branch `spec/site-publico` criada antes da execução
- [ ] Revisado e aprovado pelo José
