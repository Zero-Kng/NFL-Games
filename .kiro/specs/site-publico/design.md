# Design Document

**Feature:** site-publico
**Workflow:** requirements-first
**Status:** em revisão
**Data:** 2026-09-27

---

## Overview

O app passa a ter um segundo endereço, **público**: `https://zero-kng.github.io/NFL-Games/`. É a **mesma interface** de `app/`, que já é a versão de celular, lendo **arquivos** no lugar da API do servidor Python.

- **Exportação:** um script novo (`tools/exportar.py`) carrega a mesma camada de dados do servidor (`NFLData`) e grava cada resposta que a interface usa num arquivo JSON, dentro de `site/`. Os arquivos de jogo, que são o grosso, vão com gzip.
- **Fonte de dados no navegador:** o `api.js` ganha uma segunda fonte (`app/js/fonte-estatica.js`), com as mesmas funções e os mesmos formatos. Ela lê os arquivos e refaz no navegador só o que não dá para gravar pronto: busca e filtro de jogadores, comparação, status dos jogos sem placar e semana atual.
- **Publicação:** um workflow do GitHub Actions roda todo dia, a cada push que mexa no app ou nos dados e com um botão manual. Ele sincroniza as fontes, monta, exporta e publica no Pages. Os dados não passam pelo Git.
- **Nada muda para o PC:** o `serve.py`, o `rodar.py` e o executável continuam iguais. A única mudança no servidor é tornar estável a ordenação da lista de jogadores (Decisão 5).

**Tão funcional quanto o PC:** a bateria inteira de testes de interface roda contra as duas fontes (Testing Strategy). A única diferença aceita é que o site precisa de internet.

Medições que dimensionam o design (2026-09-27, cópia local de 2021–2026):

| Item | Quantidade | Tamanho |
|---|---|---|
| Jogos | 1.696 | ~30 KB (jogo + jogadas + transmissão) + ~40 KB (pranchetas), com gzip |
| Perfis de jogador (temporada × jogador) | 11.939 | ~6 KB cada, sem gzip |
| Lista de jogadores por temporada | 6 | ~700 KB sem gzip, ~60 KB com gzip do Pages |
| Exportar um jogo completo | — | ~0,6 s |
| Exportar 200 perfis | — | ~3,4 s |
| Interface (`app/`) | — | 260 KB |

Total estimado no Pages: **~200 MB** (limite: 1 GB). Exportação completa: **~20 min num processo, ~6 min com 4**.

---

## Architecture

### Visão de alto nível

```
  PC (como hoje)                                  Celular / qualquer navegador
  ─────────────                                   ────────────────────────────
  app/ ──fetch /api/...──► serve.py ─► NFLData    site/ (GitHub Pages)
                                          ▲         ├─ index.html (+ <meta nfl-dados=estatico>)
                                          │         ├─ css/ js/ img/  (cópia de app/)
                                          │         └─ api/versao.json
                                          │            api/{versao}/...  (arquivos exportados)
  GitHub Actions (todo dia, push, manual) │                 ▲
  ───────────────────────────────────────  │                 │ fetch relativo
  etl/montar.py ─► dados/ ─► tools/exportar.py ─► site/ ─► deploy-pages
                              (NFLData)
```

### Fluxo: abrir o site

1. O navegador carrega `index.html`, que tem a marca `<meta name="nfl-dados" content="estatico">`.
2. O `api.js` vê a marca e passa a usar a `fonte-estatica.js`.
3. A fonte lê `api/versao.json` sem cache (`cache: 'no-store'`, ~100 bytes) e fica sabendo a versão publicada, por exemplo `20260927T1004`.
4. Todas as leituras seguintes vão para `api/20260927T1004/...`.
5. `meta()` lê `meta.json` e recalcula a `currentWeek` de cada temporada com a data de hoje em Nova York. A tela Início segue como hoje.

### Fluxo: publicação nova no meio do uso (critério 4.4)

O Pages publica o site inteiro de uma vez, e a versão antiga some. Uma sessão aberta antes da publicação ainda aponta para `api/{antiga}/` e passa a receber 404.

1. Quando uma leitura dá 404, a fonte relê `api/versao.json` sem cache.
2. Se a versão mudou, a página recarrega. O estado está todo na URL (tela, temporada, semana, jogo, jogada, jogador), então o usuário volta ao mesmo lugar, já com os dados novos.
3. Se a versão não mudou, o 404 é de verdade (jogador sem aquela temporada, lance sem prancheta) e vira o mesmo erro "não encontrado" do servidor.

Assim uma tela nunca mistura arquivos de dois dias. O cache de 10 min do Pages também deixa de ser problema, porque cada versão tem caminhos próprios.

### O que já existe e será reusado

- **`NFLData`** (`server/data_layer.py`): toda resposta exportada sai dela. Nenhum cálculo é duplicado, exceto os quatro pequenos da fonte estática (componente 3).
- **`api.js`**: a interface já só fala com os dados por ele. O cache da sessão (LRU e deduplicação) vale para as duas fontes.
- **`etl/montar.py`**: roda igual no Actions.
- **`tools/servidor_local.py`** e os testes Playwright com o Edge: base para rodar a bateria contra o site.

---

## Components and Interfaces

### 1. `tools/exportar.py` (novo)

```
python tools/exportar.py [--saida site] [--dados dados] [--processos 4] [--temporadas 2025,2026]
```

1. Carrega `NFLData(dados)`.
2. Copia `app/` para `site/` e acrescenta ao `index.html` a marca `<meta name="nfl-dados" content="estatico">`.
3. Grava `api/versao.json` com `{"versao": "<AAAAMMDDTHHMM UTC>"}` e os dados em `api/{versao}/` (Data Model).
4. Divide os jogos entre N processos. Cada processo carrega o próprio `NFLData`, em ~7 s, e grava os seus jogos. A lista de jogos e os perfis ficam no processo principal.
5. Grava cada arquivo de forma atômica: escreve um `.tmp` e renomeia.
6. Termina com a verificação de `--verificar`: tamanho total abaixo de 1 GB, `meta.json` e um jogo por temporada legíveis, marca presente no `index.html`. Se algo falhar, sai com código diferente de zero.

`--temporadas` limita a exportação às temporadas dadas, para testes e para medir. O `meta.json` continua completo.

### 2. `app/js/api.js` (alterado)

```js
const ESTATICO = document.querySelector('meta[name="nfl-dados"]')?.content === 'estatico';
export const api = ESTATICO ? fonteEstatica(get) : { /* as 11 funções de hoje */ };
```

- A interface continua chamando `api.meta()`, `api.games(...)` e as demais, sem saber qual é a fonte.
- O `get(path)` de hoje, com o cache da sessão, é reusado pela fonte estática com caminhos relativos (`api/...`). Por isso o site funciona no subcaminho `/NFL-Games/`.
- Um erro continua sendo um `Error` com `.status`, como hoje. As telas tratam os dois casos igualmente.

### 3. `app/js/fonte-estatica.js` (novo)

| Função | Lê | Calcula no navegador |
|---|---|---|
| `meta()` | `meta.json` | `currentWeek` de cada temporada e a de topo (Regra A) |
| `games(ano, semana)` | `{ano}/semanas/{semana}.json` | `status` dos jogos sem placar (Regra B) |
| `game(id)` | `jogos/{id}.json.gz` → `.game` | `status` (Regra B) |
| `plays(id)` | `jogos/{id}.json.gz` → `.plays` | — |
| `broadcast(id)` | `jogos/{id}.json.gz` → `.broadcast` | `null` vira 404 "jogo nao encontrado ou ainda sem jogadas" |
| `tracking(id, lance)` | `jogos/{id}.pranchetas.json.gz` → `[lance]` | ausente vira 404 "formacao indisponivel para esta jogada" |
| `players(ano, filtros)` | `{ano}/jogadores.json` | filtro e limite (Regra C) |
| `player(id, ano)` | `{ano}/jogadores/{id}.json` | 404 vira "jogador sem dados na temporada" |
| `compare(a, b, ano)` | os dois perfis | junção (Regra D) |
| `news(ano, semana?)` | `{ano}/noticias.json` ou `{ano}/noticias/{semana}.json` | — |
| `summary(ano)` | `{ano}/resumo.json` | — |

Sem `ano`, vale a temporada atual (`meta.season`), como no servidor.

**Descompressão:** os `.json.gz` são lidos com `fetch` e `DecompressionStream('gzip')`, mas só quando os dois primeiros bytes são os do gzip (`1f 8b`). Se o servidor tiver mandado o arquivo com `Content-Encoding: gzip`, o navegador já o descompactou, e o texto é lido direto. Se o navegador não tiver a `DecompressionStream`, a leitura lança um erro com a mensagem do critério 4.2, que a tela Jogo mostra no seu estado de erro.

**Regra A, semana atual** (espelha `_semana_atual`): `hoje` é a data em `America/New_York` (`Intl.DateTimeFormat('en-CA', {timeZone})`). A semana atual é a maior semana com alguma data `<= hoje`. Se nenhuma tiver começado, é a primeira semana.

**Regra B, status** (espelha `_status`): com placar, fica `"encerrado"`, que já vem no arquivo. Sem placar: `kickoffUtc` nulo ou no futuro dá `"agendado"`; no passado, `"sem_resultado"`.

**Regra C, jogadores** (espelha `players_list`): `jogadores.json` já vem ordenado por rating e volume (ordenação estável, Decisão 5). O filtro mantém a ordem e aplica, nesta ordem:
- `rated` (padrão: só avaliados);
- `q`: o nome contém o termo, sem diferenciar maiúsculas, com `toUpperCase` nos dois lados (o mesmo que o pandas faz em `str.contains(case=False, regex=False)`: compara em `upper()`);
- `position`: lista separada por vírgula, comparada em maiúsculas;
- `role` e `team`, em maiúsculas;
- limite: padrão 40, máximo 300.

**Regra D, comparação** (espelha `compare`): lê os dois perfis. Se um faltar, dá 404 "um dos jogadores nao tem dados na temporada"; sem `a` ou `b`, dá 400. `sameRole` compara o grupo de `roles[0]` dos dois. As linhas só entram quando os grupos são iguais, pelos rótulos das estatísticas.

**Relógio:** as regras A e B usam `Date.now()`. Os testes controlam a hora com o relógio do Playwright, que já é usado hoje.

### 4. `app/js/main.js` (alterado, mínimo)

- **Mensagem de erro da abertura:** no site, "Não foi possível carregar os dados. Verifique a conexão e tente de novo." (critério 4.3). No PC, continua a mensagem de hoje.
- **Tela de carregamento:** a espera por 503 com a tela de carregamento continua só no PC. A fonte estática nunca devolve 503.

### 5. `server/data_layer.py` (alterado, uma linha)

`players_list` passa a ordenar com `kind="stable"`. Em empates de rating e volume, a ordem vira a da tabela, igual à da lista exportada (Decisão 5).

### 6. `.github/workflows/pages.yml` (novo)

```yaml
on:
  schedule: [{cron: "0 10 * * *"}]          # 7h de Brasília
  push: {branches: [main], paths: ["app/**", "server/**", "etl/**", "tools/exportar.py", ".github/workflows/pages.yml"]}
  workflow_dispatch: {}
permissions: {contents: read, pages: write, id-token: write}
concurrency: {group: pages, cancel-in-progress: false}
```

Um job `publicar` (ubuntu-latest):
1. `actions/checkout` e `actions/setup-python` (3.12), depois `pip install pandas numpy`.
2. `actions/cache` da pasta `dados/`: `key: dados-${{ github.run_id }}` e `restore-keys: dados-`. Assim restaura sempre a cópia mais recente e salva a nova.
3. `python etl/montar.py --estrito`: sai com erro se alguma fonte falhar, para não republicar sem aviso (critério 3.4). Sem `--estrito`, que é o uso no PC, ele segue com a cópia local.
4. `python tools/exportar.py --saida site --processos 4`, que termina verificando o resultado.
5. `actions/upload-pages-artifact` (`path: site`) e `actions/deploy-pages`.

Se qualquer passo falhar, o deploy não acontece e o site fica com a versão anterior. O GitHub avisa por e-mail quem é dono do workflow (critério 3.4). O `concurrency` impede duas publicações ao mesmo tempo.

---

## Data Model

```
site/
├─ index.html                      cópia de app/index.html + <meta name="nfl-dados" content="estatico">
├─ css/ js/ img/                   cópia de app/
└─ api/
   ├─ versao.json                  {"versao": "20260927T1004"}
   └─ 20260927T1004/
      ├─ meta.json                 = /api/meta
      ├─ jogos/{gameId}.json.gz    {"game": /api/games/{id}, "plays": /api/games/{id}/plays,
      │                             "broadcast": /api/games/{id}/broadcast ou null}
      ├─ jogos/{gameId}.pranchetas.json.gz
      │                            {"<playId>": /api/games/{id}/plays/{playId}/tracking, ...}
      │                            (só os lances que têm prancheta)
      └─ {ano}/
         ├─ semanas/{semana}.json  = /api/games?season={ano}&week={semana}
         ├─ jogadores.json         todos os cartões da temporada (avaliados e não avaliados), já ordenados
         ├─ jogadores/{nflId}.json = /api/players/{nflId}?season={ano}
         ├─ noticias.json          = /api/news?season={ano}
         ├─ noticias/{semana}.json = /api/news?season={ano}&week={semana}
         └─ resumo.json            = /api/summary?season={ano}
```

- **Mesmos bytes do servidor:** o JSON sai com `ensure_ascii=False`. Ele é igual, campo a campo, à resposta do servidor na mesma data. As exceções são o `status` e a `currentWeek` gravados, que a fonte recalcula.
- **Nomes de arquivo:** `gameId` é só dígitos, e `nflId` segue `00-0012345` (a mesma validação da rota `/api/players/`). Nenhum nome vem de texto livre.
- **O que fica de fora:** `/api/leaders`, as rotas `/plays/{id}` e `/formation`, e os parâmetros `quarter`/`team` de `/plays`. A interface não usa nenhum deles.

---

## Error Handling

| Falha | Detecção | Resposta | Requisito |
|---|---|---|---|
| Arquivo inexistente numa versão válida | 404 com `versao.json` igual | Erro 404 com a mensagem do servidor para aquela rota | 2.6 |
| Versão publicada mudou no meio do uso | 404 com `versao.json` diferente | Recarrega a página, que volta ao mesmo lugar pela URL | 4.4 |
| Sem conexão ou queda | `fetch` rejeita | O estado de erro da tela, com "tentar de novo" | 4.1 |
| Falha na abertura (`versao.json` ou `meta.json`) | `boot()` pega o erro | "Não foi possível carregar os dados. Verifique a conexão e tente de novo." | 4.3 |
| Navegador sem `DecompressionStream` | `typeof DecompressionStream` | Erro na tela Jogo com o aviso de atualizar o navegador; as outras telas não usam `.gz` | 4.2 |
| `.gz` corrompido | a descompressão ou o `JSON.parse` lança | O estado de erro da tela Jogo | 4.1 |
| nflverse fora do ar ou arquivo inválido no Actions | `montar.py` sai com erro | O workflow falha, não publica e o GitHub avisa | 3.4 |
| Exportação passa de 1 GB ou fica incompleta | verificação final do `exportar.py` | Sai com erro e não publica | 3.4, RNF 1 |

---

## Segurança

- **Só o necessário vai para o Pages:** o `upload-pages-artifact` publica apenas `site/`, que tem só a cópia de `app/` e `api/`. Código do servidor, `dados/`, testes e configurações nunca entram (segurança 1).
- **Permissões mínimas:** `contents: read`, `pages: write` e `id-token: write`. O workflow não escreve no repositório (segurança 2).
- **Textos dos dados:** continuam passando pelo `esc()` da interface, como hoje (segurança 3).
- **Endereços acessados:** a fonte estática só lê caminhos relativos do próprio site. A ESPN continua como hoje (segurança 4).

---

## Testing Strategy

1. **`tests/test_exportar.py` (pytest):**
   - Exporta uma temporada encerrada (`--temporadas 2021`) para uma pasta temporária.
   - Confere que cada arquivo é igual à resposta do servidor para a rota equivalente (meta, semanas, jogo, jogadas, transmissão, pranchetas, lista, perfis, notícias e resumo). A exceção é o `status` e a `currentWeek`, que dependem do relógio.
   - Confere a marca no `index.html`, os `.gz` legíveis, a escrita atômica e a verificação de tamanho.
2. **Fonte estática contra o servidor (Playwright + Edge):**
   - Serve o `site/` exportado num subcaminho `/NFL-Games/`, com um servidor de arquivos simples, como no Pages.
   - Com o relógio fixado nos dois lados (`NFLData(hoje=...)` no Python e `page.clock` no navegador), compara as respostas da fonte estática com as do servidor. Casos:
     - buscas e filtros de jogadores (termos com acento, maiúsculas, posições múltiplas, grupos, times, `rated=0`, limites);
     - comparações do mesmo grupo e de grupos diferentes, e com jogador inexistente;
     - status e semana atual antes, durante e depois de uma rodada;
     - todos os 404 com as mensagens do servidor.
3. **A bateria de interface nas duas fontes (critério 1.7):**
   - As fixtures de `test_ui.py`, `test_ui_dados.py` e `test_ui_novo.py` ganham o parâmetro `fonte`, com os valores `servidor` e `estatico`.
   - Em `estatico`, o `site/` é exportado uma vez por sessão de testes e reaproveitado enquanto a cópia de `dados/` e o código não mudarem.
   - Os testes que simulam respostas da API com `route()` passam a usar um auxiliar, `simular_api(pg, rota, resposta)`, que traduz a rota para o arquivo equivalente do site.
   - **Só rodam na fonte `servidor`** (marca `so_servidor`, cada uso com o motivo):
     - os testes da tela de carregamento do servidor (`_simular_carga`, respostas 503 e `/api/estado`), que é função exclusiva do PC;
     - `tests/test_carregamento.py`;
     - os testes do `test_ui.py` que atrasam ou derrubam **um pedido específico** ao servidor: a prancheta de um lance (`/plays/{id}/tracking`) ou uma busca (`q=...`). No site, as pranchetas de um jogo chegam num arquivo só e a busca não faz pedido. A regra que eles protegem ("só a última resposta vale") continua no código comum às duas fontes.
   - Qualquer outro teste que falhe na fonte `estatico` é defeito do site, e não motivo para marcar `so_servidor`.
4. **Troca de versão:** um teste publica duas versões seguidas no servidor de arquivos e confere que uma sessão aberta recarrega no mesmo lugar, sem misturar dados.
5. **`golden.py check`:** deve continuar passando. Se a ordenação estável mudar alguma resposta, a diferença é só de ordem entre empatados, conferida à mão e registrada, e a foto é recapturada.
6. **Depois do primeiro deploy:**
   - abrir o link no navegador em largura de celular;
   - medir o volume até a tela Início ficar pronta (RNF 2) e ao abrir um jogo (RNF 3);
   - anotar o tempo do workflow (RNF 4);
   - passar o link para o José testar no celular dele.

---

## Decisões e alternativas descartadas

### Decisão 1: exportar as respostas, não reescrever a camada de dados
- **Alternativas descartadas:**
  - Reescrever em JavaScript: duas implementações dos ratings, das notícias e da prancheta para manter iguais.
  - Rodar o Python no navegador (Pyodide): ~25 MB de Python com pandas mais ~50 MB de dados, o que é lento no 4G.
- **Escolhida:** exportar reusa a `NFLData`, e o que fica em JS são quatro regras pequenas, testadas contra o servidor.

### Decisão 2: um arquivo por jogo, e as pranchetas separadas
- **Por que agrupar:** um arquivo por lance daria ~280 mil arquivos e ~1,4 GB.
- **Como fica:** o jogo, as jogadas e a transmissão ficam num arquivo de ~30 KB, que a tela Jogo sempre usa. As pranchetas de todos os lances ficam em outro, de ~40 KB, baixado quando o primeiro lance é aberto.

### Decisão 3: gzip feito pelo exportador e aberto pelo navegador
- **O problema:** o limite de 1 GB do Pages conta os arquivos como estão gravados. O gzip que o Pages aplica na transferência não diminui esse número.
- **A saída:** gravar os arquivos de jogo comprimidos derruba ~1,9 GB para ~120 MB.
- **O custo:** exige `DecompressionStream`, presente no Chrome 80+, no Safari 16.4+ e no Firefox 113+. Os JSON pequenos ficam sem compressão própria, e o Pages os comprime na transferência.

### Decisão 4: versão no caminho, não parâmetro `?v=`
- **Por que não o parâmetro:** o `?v=` só evita o cache. Depois de uma publicação, os arquivos novos continuam no mesmo caminho, e uma sessão aberta misturaria dias.
- **Como fica:** com a versão no caminho, uma sessão antiga recebe 404 e recarrega na versão nova.

### Decisão 5: ordenação estável da lista de jogadores no servidor
- **O problema:** o `sort_values` padrão do pandas não garante a ordem entre empatados em rating e volume. Com isso, o filtro no navegador, feito sobre a lista completa ordenada, poderia divergir do servidor, que ordena o subconjunto filtrado.
- **A saída:** com `kind="stable"` nos dois lados, os empatados ficam na ordem da tabela, e as duas fontes coincidem.

### Decisão 6: dados publicados por artefato do Actions, não por branch
- Publicar numa branch `gh-pages` poria ~200 MB por dia no histórico do Git. O artefato do Pages não passa pelo Git.

---

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| iPhone com iOS anterior ao 16.4 (sem `DecompressionStream`) | A tela Jogo não abre | Mensagem clara (4.2). As outras telas funcionam. |
| O GitHub desliga o agendamento depois de 60 dias sem atividade no repositório | O site para de atualizar | O GitHub avisa por e-mail. A reativação é um clique no Actions. Anotado no README. |
| O cache do Actions some depois de 7 dias sem uso | Uma execução baixa os ~330 MB de novo | Só custa tempo (alguns minutos) e cabe no RNF 4. |
| Limite de banda do Pages (100 GB/mês, limite flexível) | Site lento ou aviso do GitHub | Uma visita típica baixa menos de 1 MB. Precisaria de mais de 100 mil visitas por mês. |
| A exportação passa de 30 min com o crescimento da temporada | Viola o RNF 4 | Mais processos. Se ainda assim passar, reaproveitar do cache as temporadas encerradas. |

---

## Aprovação

- [ ] Revisado e aprovado pelo José
