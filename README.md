# NFL Games — Treinador · Olheiro · Comentarista

Protótipo de UI ligado a dados reais e públicos da NFL, da **temporada 2021 em diante**
(temporada regular e playoffs, com todas as jogadas: passes, corridas, chutes e retornos).
Nenhum número da interface é fictício: tudo vem dos arquivos do
[nflverse](https://github.com/nflverse/nflverse-data), baixados e atualizados pelo
próprio servidor.

**Autoria:** José Cota · Alan Souza · Nilo Reis · José Johnata

---

## Como executar

### Opção 1 — duplo clique (Windows)

```
RODAR.bat
```

Na **primeira execução** o servidor baixa e monta os dados do nflverse: **~330 MB**,
alguns minutos, com o progresso no terminal. Precisa de internet. O navegador abre
sozinho quando o app estiver no ar. Nas próximas, sobe em ~4 s com a cópia local.

### Opção 2 — linha de comando

```powershell
# 1. dependências (uma vez)
python -m pip install pandas numpy

# 2. sobe o app (na 1a vez ele mesmo baixa e monta os dados)
python server/serve.py
```

Depois abra **<http://127.0.0.1:8000>**.

| Comando | Para quê |
|---|---|
| `python server/serve.py` | uso normal: sobe com a cópia local e busca o que mudou em segundo plano |
| `python server/serve.py --offline` | não acessa a internet, usa só a cópia em `dados/` (testes, medições, apresentação sem rede) |
| `python server/serve.py --port 9000` | outra porta |
| `python etl/montar.py` | sincroniza as fontes e monta o que mudou, sem subir o servidor |

### Atualização dos dados

- Com cópia local, o servidor **sobe na hora** e, 1 s depois, busca os dados novos em
  segundo plano. A partir daí, repete **uma vez por dia** e troca os dados sem reiniciar.
- Só baixa o que mudou: compara a data e o tamanho de cada arquivo com o
  `dados/manifest.json`.
- O download nunca estraga a cópia boa: vai para um `.tmp`, as colunas são conferidas
  e só então substitui o arquivo anterior.
- Depois que uma **temporada encerrada** é montada, os arquivos brutos dela são
  descartados (a pasta `dados/` fica com ~50 MB). Só são baixados de novo se o
  nflverse publicar uma correção.
- **Sem internet**, o app segue com a última cópia. Sem internet **e** sem cópia
  nenhuma, a primeira subida sai com uma mensagem e código 1.

### Por que o `index.html` precisa do servidor

Abrir `app/index.html` com duplo clique **não funciona**. Dois motivos:

1. São seis temporadas de jogadas e estatísticas por jogador. Quem cruza isso é o
   Python; o navegador só recebe as respostas prontas.
2. Em `file://` o navegador bloqueia as chamadas `fetch()` por política de CORS.

O `server/serve.py` resolve os dois: serve a página e a API JSON no mesmo endereço.
A página em si é um HTML comum, sem build, sem npm, sem framework.

> O servidor escuta só em `127.0.0.1` (sua máquina), é somente leitura e não tem
> autenticação. Se usar `--host 0.0.0.0` para abrir no celular, faça isso apenas em
> rede confiável. Os únicos endereços que o servidor acessa são os do nflverse no
> GitHub.

---

## Fontes e créditos

| Fonte | Licença | Usada para |
|---|---|---|
| [nflverse](https://github.com/nflverse/nflverse-data) | CC-BY-4.0 | calendário, placar oficial, jogadas, jogadores em campo, formação e estatísticas |
| [FTN Data](https://ftndata.com), via nflverse | CC-BY-SA-4.0 | posição do QB, backfield, box e rushers (2022 em diante) |
| [Pro Football Reference](https://www.pro-football-reference.com), via nflverse | via nflverse | pressões, tackles perdidos, drops, jardas após o contato e snaps |
| [ESPN](https://www.espn.com/nfl/) | consulta no navegador | placar ao vivo e matéria do jogo (título, resumo e link) |

O servidor só baixa arquivos do nflverse. A ESPN é consultada **direto pelo navegador**,
nunca pelo servidor; quando o placar dela diverge do nflverse, vale o nflverse. A
lista de fontes, os créditos e a hora da última atualização saem em `/api/meta`.

---

## As quatro telas

| Tela | O que mostra | De onde vem |
|---|---|---|
| **Jogos** | Partidas da semana (a jogar, sem resultado ou encerradas), destaques do jogo | calendário e placar do nflverse + ratings |
| **Treinador** | Prancheta com a formação da jogada, lista de jogadas, estatísticas e tendências (formação, pessoal, cobertura) | play-by-play + participação + FTN |
| **Olheiro** | Busca de jogadores, rating 40–99, radar de atributos por percentil, jogo a jogo, comparação | estatísticas por jogador e jogo + PFR + snaps |
| **Comentarista** | Replay cronológico com o placar oficial de cada momento, narração e estatísticas acumuladas | play-by-play em ordem |

Deep link opcional: `?week=3&game=<gameId>&screen=coach`.

As telas ainda estão sendo adaptadas aos dados novos (tarefa 7 da spec
`dados-externos`): seletor de temporada, nomes das rodadas de playoff, placar ao vivo
e matéria da ESPN entram nessa tarefa.

### Sobre a prancheta do Treinador

Não há tracking nas fontes públicas, então a prancheta é um **esquema ilustrativo**
da formação, com um quadro só: os 22 jogadores reais da jogada (nome, número e
posição) em posições-modelo da formação informada. O ataque joga sempre no mesmo
sentido; o QB fica mais fundo no shotgun do que sob o center; a defesa se distribui
pelo número de defensores no box. Quando a jogada não tem a lista de jogadores (caso
de 2026), o esquema é genérico, sem nomes. Sem formação, aparece "formação
indisponível".

---

## Estrutura

```
Projeto/
├─ RODAR.bat                  inicia tudo (Windows)
├─ app/                       a página
│  ├─ index.html              markup
│  ├─ css/app.css             design system do protótipo + componentes
│  └─ js/app.js               toda a lógica (JS puro, sem dependências)
├─ etl/
│  ├─ fontes.py               baixa e valida os arquivos do nflverse (só o que mudou)
│  ├─ montar.py               monta as tabelas do servidor a partir dos brutos
│  └─ ratings.py              ratings por grupo de posição e temporada
├─ server/
│  ├─ serve.py                servidor HTTP + API JSON + atualização diária
│  ├─ data_layer.py           consultas sobre as tabelas montadas
│  ├─ prancheta.py            esquema ilustrativo da formação
│  ├─ response_cache.py       respostas prontas da API em memória (calcula cada uma 1 vez)
│  ├─ tabela_npz.py           formato binário das tabelas
│  ├─ teams.py                nomes e cores das 32 franquias
│  └─ smoke_test.py           roda todas as consultas e imprime amostras
├─ tools/                     golden (regressão), bench (1 usuário), carga (N usuários)
├─ tests/                     pytest + testes de navegador (Playwright com o Edge)
├─ .kiro/specs/               specs SDD (requirements, design, tasks)
└─ dados/                     gerado automaticamente (não versionar)
   ├─ manifest.json           o que foi baixado, quando, e a última sincronização
   ├─ brutos/                 cópias validadas dos arquivos do nflverse
   ├─ jogos.npz               calendário e placar de todas as temporadas
   ├─ jogadores_bio.npz       bio, foto e posição dos jogadores
   └─ temporadas/{ano}/       jogadas · estatísticas por jogador e jogo · ratings
```

A pasta `nfl-big-data-bowl-regional-event-data-main/` (dataset do Big Data Bowl 2023,
usado pela primeira versão) e o `cache/` não são mais lidos. Tirar o dataset do
repositório é uma decisão pendente (Q-D1 na spec `dados-externos`).

---

## Como o rating é calculado

Não é nota inventada. Para cada **temporada** e **grupo de posição**, os jogadores
são comparados **entre si** em 4 a 6 eixos, cada um virando um percentil de 0 a 100:

| Grupo | Eixos |
|---|---|
| Quarterback | EPA por dropback · Precisão (CPOE) · Jardas por tentativa · Cuidado com a bola · Sob pressão · Corrida |
| Running back | EPA por corrida · Após o contato · Tackles quebrados · Recepção · Segurança |
| Recebedor (WR/TE) | Jardas por alvo · EPA por alvo · Aproveitamento · Alvos por jogo · Mãos |
| Linha ofensiva | Volume · Disciplina · Proteção do time · Corrida do time |
| Edge / Linha defensiva | Pressão · Sacks · QB hits · Tackles para perda · Tackles perdidos |
| Linebacker | Tackles · Tackles para perda · Pressão · Cobertura · Tackles perdidos |
| Secundária | Rating permitido · Passes completados · Jardas por alvo · Bolas na mão · Tackles perdidos |

O rating é `40 + média dos percentis × 0,59`, o que dá a escala 40–99. O volume
mínimo é **por jogo do time** (ex.: 15 dropbacks por jogo para QB), multiplicado pelos
jogos que o time já disputou; assim o rating funciona também no meio da temporada.
Quem não bate o mínimo aparece como `n/d`, em vez de receber uma nota com amostra
fraca. Um eixo sem dado na fonte fica fora da média, com o motivo.

A linha ofensiva não tem pressão cedida individual em fonte pública: 2 dos 4 eixos
dela são do time, nos jogos em que o jogador atuou (marcado como `baseReduzida`).

---

## Limites dos dados

- **Não há tracking.** A prancheta é ilustrativa e não anima; métricas de velocidade
  e de deslocamento da primeira versão deixaram de existir.
- **O nflverse publica o jogo no dia seguinte.** Durante a partida, o placar ao vivo
  vem da ESPN no navegador; depois, vale o placar oficial do nflverse.
- **Formação e charting do FTN existem de 2022 em diante.** Em 2021 a formação vem só
  da participação.
- **Leituras táticas e bastidores** da primeira versão dependiam do dataset antigo e
  estão vazios (`insights` e `notes` na API).

---

## API

Todos os endpoints são `GET` e devolvem JSON. Sem `season`, vale a temporada atual.

| Rota | Retorno |
|---|---|
| `/api/meta` | temporadas, semanas e rodadas, 32 times, médias da liga, fontes, créditos e última atualização |
| `/api/games?season=&week=&date=` | partidas, com status (`agendado`, `sem_resultado`, `encerrado`) |
| `/api/games/{id}` | detalhe + estatísticas + tendências + destaques |
| `/api/games/{id}/plays?quarter=&team=` | todas as jogadas do jogo |
| `/api/games/{id}/plays/{pid}` | uma jogada |
| `/api/games/{id}/plays/{pid}/tracking` | esquema ilustrativo da formação (1 quadro, `ilustrativo: true`) |
| `/api/games/{id}/plays/{pid}/formation` | o mesmo esquema, no formato da formação no snap |
| `/api/games/{id}/broadcast` | feed cronológico narrado com o placar de cada jogada |
| `/api/players?season=&q=&position=&role=&team=&rated=&limit=` | busca de jogadores |
| `/api/players/{id}?season=` | perfil completo com radar e jogo a jogo (id gsis, ex.: `00-0034857`) |
| `/api/compare?season=&a=&b=` | comparação entre dois jogadores do mesmo grupo e temporada |
| `/api/leaders?season=&metric=&role=&limit=` | ranking por eixo do rating (ex.: `metric=pressao_snap&role=EDGE`) |

Exemplo:

```powershell
curl "http://127.0.0.1:8000/api/leaders?season=2025&metric=epa_dropback&role=QB&limit=5"
```

---

## Verificação

```powershell
python -m pip install -r requirements-dev.txt   # pytest + playwright (uma vez)

python -m pytest tests -q         # sobe o servidor em --offline; precisa de dados/ montado
python server/smoke_test.py       # todas as consultas da camada de dados, sem servidor
python tools/golden.py check      # prova que nenhuma resposta da API mudou (2.116 URLs)
python tools/bench.py --check     # tempo por rota com 1 usuário, contra as metas
python tools/carga.py --usuarios 10 --check   # 10 usuários ao mesmo tempo
```

Os testes que leem `dados/` são pulados se a pasta ainda não tiver sido montada: suba
o servidor uma vez com internet antes. Os testes e as ferramentas usam `--offline`,
porque a API do GitHub permite só 60 chamadas por hora.

Os testes de navegador usam o **Edge já instalado** (não rode `playwright install`).
O `tests/golden/hashes.json` é a "foto" das respostas das temporadas **encerradas**
(2021–2025) e dos caminhos de erro; a temporada atual fica de fora, porque muda todo
dia. Só refaça a foto (`capture`) quando a mudança de dados for intencional.

---

## Desempenho

Meta das specs `.kiro/specs/otimizacao-desempenho/` e `dados-externos/`: uma banca de
10 pessoas usando ao mesmo tempo. Medido nesta máquina, na semana mais recente
disputada:

| Medida | Resultado |
|---|---|
| 10 usuários, pausa de 1–2 s entre cliques, p95 | 28 ms (meta 300) |
| Subida com a cópia local | ~4 s (meta 10) |
| Pico de memória no teste de carga | ~495 MB (meta 1 GB) |

Como: respostas prontas em memória (cada uma calculada uma vez, pré-aquecidas ao
subir), tabelas em formato binário com texto como categoria, pré-carga das jogadas
vizinhas no navegador e descarte de respostas atrasadas.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| A página abre com o aviso "API indisponível" | O servidor não está de pé. Rode `python server/serve.py`. |
| Primeira subida demora alguns minutos | É o download e a montagem dos dados (~330 MB). O progresso aparece no terminal. |
| `[erro] Sem dados para subir o app` | Primeira subida sem internet. Conecte-se e rode de novo. |
| `[erro] dados locais ilegiveis` | A cópia em `dados/` corrompeu. Apague a pasta e rode de novo (com internet). |
| `503 servidor ocupado` | Mais de 64 requisições simultâneas. O navegador pode tentar de novo em 2 s. |
| `ModuleNotFoundError: pandas` | `python -m pip install pandas numpy` |
| Tela em branco abrindo o arquivo direto | É o caso do `file://`. Acesse por `http://127.0.0.1:8000`. |
| Porta 8000 ocupada | `python server/serve.py --port 9000` |
| Acentos quebrados no terminal do Windows | `$env:PYTHONIOENCODING='utf-8'` antes do comando. |

---

## Requisitos

- Python 3.10 ou superior (testado no 3.14) com **pandas** e **numpy**
- Um navegador atual
- Internet na primeira execução (depois, opcional)

Sem Node, sem npm, sem etapa de build.

---

**Fontes dos dados:** [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY-4.0);
charting de [FTN Data](https://ftndata.com) via nflverse (CC-BY-SA-4.0); estatísticas
avançadas e snaps de [Pro Football Reference](https://www.pro-football-reference.com)
via nflverse; placar ao vivo e matérias da [ESPN](https://www.espn.com/nfl/),
consultados no navegador.
