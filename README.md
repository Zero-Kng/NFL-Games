# NFL Games — Início · Jogo · Jogadores · Notícias

Protótipo de UI ligado a dados reais e públicos da NFL, da **temporada 2021 em diante**
(temporada regular e playoffs, com todas as jogadas: passes, corridas, chutes e retornos).
Nenhum número da interface é fictício: tudo vem dos arquivos do
[nflverse](https://github.com/nflverse/nflverse-data), baixados e atualizados pelo
próprio servidor.

**Autoria:** José Cota · Alan Souza · Nilo Reis · José Johnata

---

## Como executar

### Opção 1 — executável (sem instalar Python)

Baixe o arquivo do seu sistema na página
[Releases](https://github.com/Zero-Kng/NFL-Games/releases) do repositório e coloque-o
numa pasta só dele (os dados ficam numa pasta `dados/` ao lado do executável):

| Sistema | Arquivo | Como abrir |
|---|---|---|
| Windows | `NFL-Games.exe` | duplo clique. Se o Windows avisar que o app não é reconhecido (ele não tem assinatura digital), clique em **Mais informações → Executar assim mesmo**. |
| Linux | `nfl-games` | `chmod +x nfl-games` (uma vez) e `./nfl-games` |

### Opção 2 — a partir do código (Windows, Linux e macOS)

```bash
# 1. dependências (uma vez)
python -m pip install pandas numpy

# 2. sobe o app e abre o navegador (na 1a vez ele mesmo baixa e monta os dados)
python rodar.py
```

No Linux e no macOS, `./rodar.sh` faz o mesmo (usa o `python3`).

### O que acontece ao abrir

Na **primeira execução** o servidor baixa e monta os dados do nflverse: **~330 MB**,
alguns minutos, com o progresso no terminal. Precisa de internet. O navegador abre
sozinho quando o app estiver no ar, em **<http://127.0.0.1:8000>**. Nas próximas, sobe
em ~4 s com a cópia local (o executável leva ~7 s, porque se descompacta antes). A
janela do terminal fica aberta enquanto o app roda: feche-a (ou Ctrl+C) para parar.

As opções valem para o executável, o `rodar.py` e o `rodar.sh`:

| Opção | Para quê |
|---|---|
| (nenhuma) | uso normal: sobe com a cópia local e busca o que mudou em segundo plano |
| `--offline` | não acessa a internet, usa só a cópia em `dados/` (testes, medições, apresentação sem rede) |
| `--port 9000` | outra porta |
| `--sem-navegador` | não abre o navegador; só mostra o endereço |
| `--host 0.0.0.0` | abre para a rede local (ver o aviso abaixo) |

`python server/serve.py` (só o servidor, sem abrir o navegador) e `python etl/montar.py`
(sincroniza as fontes e monta o que mudou, sem subir o servidor) continuam valendo.

### Gerar os executáveis

```bash
python -m pip install -r requirements-dev.txt   # traz o PyInstaller (uma vez)
python tools/empacotar.py                        # gera dist/NFL-Games.exe (ou dist/nfl-games no Linux)
```

Cada sistema gera o seu. Para publicar os dois numa versão, marque-a: `git tag v1.0` e
`git push origin v1.0`. O GitHub Actions (`.github/workflows/executaveis.yml`) gera
os executáveis em Windows e em Linux, confere que sobem e os anexa à página da versão.
O executável de Linux é gerado no Ubuntu 22.04 e roda nas distribuições mais novas.

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

## As telas

Layout de celular (centralizado numa moldura em telas largas), fundo escuro, com o
visual do `rascunho/`. Uma barra inferior leva aos quatro destinos; o menu lateral
repete os quatro e traz **Sobre os dados** e **Configurações**. A lupa do cabeçalho
abre a busca em qualquer tela.

| Tela | O que mostra | De onde vem |
|---|---|---|
| **Início** | Carrossel com as 4 principais notícias da semana, os cartões "partidas na semana" e "jogadores avaliados" e os jogos da semana (a jogar, sem resultado, encerrado ou **AO VIVO**) | calendário e placar do nflverse + notícias + ESPN no navegador |
| **Jogo** | Placar da partida, matéria da ESPN e 5 abas: **Prancheta** (formação da jogada), **Jogadas** (por quarto), **Replay** (narração com o placar de cada momento e estatísticas acumuladas), **Estatísticas** e **Playbook** (formações, coberturas e pessoal) | play-by-play + participação + FTN |
| **Jogadores** | Os destaques ("a observar") da partida selecionada, busca, filtro por posição, lista por rating 40–99, perfil com radar de percentis e jogo a jogo, comparação | estatísticas por jogador e jogo + PFR + snaps |
| **Notícias** | Os fatos marcantes da semana, do mais incomum ao menos | geradas no servidor a partir dos dados (abaixo) |
| **Configurações** | Avanço automático das notícias e velocidade do Replay (0,5×, 1× ou 2×), salvos no aparelho | `localStorage` |
| **Sobre os dados** | Fontes, créditos das licenças e a hora da última atualização | `/api/meta` |

Tocar numa partida, numa notícia ou num resultado de busca abre a página Jogo;
tocar numa jogada (em Jogadas ou no Replay) abre a Prancheta com ela.

### Mapa de rotas

Cada tela tem link próprio, e a URL acompanha o que está na tela:

```
/?season=2021&week=1&game=2021090900&screen=jogo&aba=replay
/?season=2021&week=1&game=2021090900&screen=jogo&play=55
/?season=2021&screen=jogadores&jogador=00-0019596
```

| Parâmetro | Valores |
|---|---|
| `screen` | `inicio` (padrão), `jogo`, `jogadores`, `noticias`, `config`, `sobre` |
| `aba` | `prancheta` (padrão), `jogadas`, `replay`, `estatisticas`, `playbook` |
| `season`, `week`, `game`, `play`, `jogador` | temporada, semana, partida, jogada e jogador (id gsis) |

Sem `season`, abre a temporada atual; sem `week`, a semana mais recente já começada
(numa temporada encerrada, o Super Bowl). Na página Jogo sem `game`, abre a primeira
partida da semana.

**Os links antigos continuam funcionando:** `?screen=coach` abre a Prancheta,
`?screen=commentator` abre o Replay e `?screen=scout` abre Jogadores, com a mesma
temporada, semana e partida.

### Notícias geradas dos dados

Não há texto livre: cada notícia é montada só com números do dado (placar oficial,
jardas, TDs, sacks) e aponta para a partida. Tipos e limiares (medidos em 2021–2025):

| Tipo | Quando vira notícia |
|---|---|
| Resultado | todo jogo disputado ("X vence Y por A–B", com a prorrogação) |
| Virada | o vencedor reverteu 10+ pontos de desvantagem |
| Prorrogação | jogo decidido na prorrogação |
| Goleada | margem de 28+ pontos |
| Maior jogada | a jogada de mais jardas da semana |
| Atuação | 400+ jd de passe, 5+ TD de passe, 175+ jd correndo ou recebendo, 4+ TD ou 3,5+ sacks |
| Defesa | time com 6+ sacks ou 3+ interceptações |

A ordem é pelo quanto o fato foge do comum na temporada (percentil), então o
carrossel mostra primeiro o que é raro, e a lista traz também os resultados. Dá ~21
notícias por semana; semana ainda sem jogos mostra "Sem notícias para esta semana".

### Detalhes

- **Temporada e rodadas:** chips de 2021 até a atual; nos playoffs, as rodadas
  aparecem pelo nome (Wild Card, Divisional, Final de Conferência, Super Bowl).
  Jogadores segue a temporada escolhida.
- **Cartão do jogo:** "A JOGAR" com dia e hora no seu fuso, "resultado ainda não
  disponível" (o jogo começou e o nflverse ainda não publicou), placar final (com
  prorrogação) ou **AO VIVO**.
- **Placar ao vivo:** enquanto a semana exibida no Início tem jogo em andamento, o
  navegador consulta a ESPN a cada 30 s e mostra placar, quarto e relógio. Começa
  sozinho na hora do jogo, para quando ele termina e não consulta nada quando não há
  jogo rolando. Se a ESPN falhar, fica o último placar com o aviso "atualização ao
  vivo indisponível".
- **Matéria do jogo:** logo abaixo do placar da página Jogo, a matéria da ESPN
  (título, resumo, data, fonte e link). Só links de `*.espn.com` são exibidos. Jogos
  muito recentes ainda não têm matéria: nesse caso o bloco não aparece.
- **Busca:** Times (sigla, nome ou apelido), Jogadores (pela API, até 8) e Notícias da
  temporada (também pelo nome dos times). O time abre o Início só com os jogos dele,
  com um chip para tirar o filtro.
- **Acessibilidade:** alvos de toque de 44 px, texto com contraste de 4,5:1 (inclusive
  sobre as cores dos times), uso completo pelo teclado com o foco visível, e sem
  animação quando o sistema pede menos movimento.

### Sobre a prancheta

Não há tracking nas fontes públicas, então a prancheta é um **esquema ilustrativo**
da formação, com um quadro só: os 22 jogadores reais da jogada (nome, número e
posição) em posições-modelo da formação informada. O ataque joga sempre no mesmo
sentido e usa a cor do seu time (círculos); a defesa, a do dela (quadrados), ou a
secundária quando as duas cores se parecem. O QB fica mais fundo no shotgun do que
sob o center; a defesa se distribui pelo número de defensores no box. Quando a jogada
não tem a lista de jogadores (caso de 2026), o esquema é genérico, sem nomes. Sem
formação, aparecem os dados da jogada e "formação indisponível para esta jogada".

---

## Estrutura

```
Projeto/
├─ rodar.py                   inicia tudo: servidor + navegador (Windows, Linux, macOS); é o que vira o executável
├─ rodar.sh                   atalho do rodar.py no Linux e no macOS
├─ app/                       a página
│  ├─ index.html              cabeçalho, filtros, barra inferior, menu lateral e as 6 telas
│  ├─ css/app.css             tokens e componentes do visual novo
│  └─ js/                     módulos ES, sem build e sem dependências
│     ├─ main.js              estado, roteador, filtros, menu e busca
│     ├─ api.js · ui.js       cache de respostas, "só o último vence", formatadores e HTML seguro
│     ├─ config.js            Configurações (localStorage, com padrões)
│     ├─ prancheta.js         o campo com a formação
│     └─ telas/               inicio · jogo · jogadores · noticias · extras (Configurações e Sobre)
├─ etl/
│  ├─ fontes.py               baixa e valida os arquivos do nflverse (só o que mudou)
│  ├─ montar.py               monta as tabelas do servidor a partir dos brutos
│  └─ ratings.py              ratings por grupo de posição e temporada
├─ server/
│  ├─ serve.py                servidor HTTP + API JSON + atualização diária
│  ├─ data_layer.py           consultas sobre as tabelas montadas
│  ├─ noticias.py             notícias geradas dos dados, ordenadas pelo "incomum"
│  ├─ prancheta.py            esquema ilustrativo da formação
│  ├─ response_cache.py       respostas prontas da API em memória (calcula cada uma 1 vez)
│  ├─ tabela_npz.py           formato binário das tabelas
│  ├─ teams.py                nomes e cores das 32 franquias
│  └─ smoke_test.py           roda todas as consultas e imprime amostras
├─ tools/                     golden (regressão), bench (1 usuário), carga (N usuários), empacotar (executável)
├─ .github/workflows/         executáveis de Windows e Linux nas versões (Releases)
├─ tests/                     pytest + testes de navegador (Playwright com o Edge)
├─ rascunho/                  o protótipo do visual (referência, não é servido)
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

**Edge × linha defensiva × linebacker** vem do depth chart do elenco (DE × DT,
OLB × ILB/MLB). Como "OLB" também cobre o linebacker de cobertura do 4-3, um OLB só
entra em Edge se teve mais pressões do que alvos permitidos na temporada.

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
- **Leituras táticas e bastidores** da primeira versão dependiam do dataset antigo:
  a API os devolve vazios (`insights` e `notes`, para não mudar as respostas) e a
  interface não tem mais essas seções. Os fatos que os bastidores traziam viraram
  as notícias.

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
| `/api/news?season=&week=` | notícias da semana (sem `week`, da temporada inteira), da mais incomum para a menos |
| `/api/summary?season=` | `{ratedPlayers, season}`: jogadores com rating na temporada |

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

Meta das specs `.kiro/specs/otimizacao-desempenho/`, `dados-externos/` e
`novo-visual/`: uma banca de 10 pessoas usando ao mesmo tempo. Medido nesta máquina,
na semana mais recente disputada:

| Medida | Resultado |
|---|---|
| 10 usuários, pausa de 1–2 s entre cliques, p95 | 28 ms (meta 300) |
| Início pronta (partidas, carrossel e cartões) | ≤ 200 ms (teste de navegador) |
| Próxima jogada na prancheta | ≤ 50 ms (teste de navegador) |
| Subida com a cópia local | ~4 s (meta 10) |
| Primeira carga completa (download + montagem) | 103 s (meta 5 min) |
| Disco em `dados/` | ~50 MB (meta 1 GB) |
| Pico de memória no teste de carga | ~495 MB (meta 1 GB) |

Detalhes em `tests/golden/resultado_dados_externos.txt`.

Como: respostas prontas em memória (cada uma calculada uma vez, pré-aquecidas ao
subir), tabelas em formato binário com texto como categoria, pré-carga das jogadas
vizinhas no navegador e descarte de respostas atrasadas.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| A página abre com o aviso "API indisponível" | O servidor não está de pé. Abra o executável ou rode `python rodar.py`. |
| O Windows diz que protegeu o computador ao abrir o `.exe` | O executável não tem assinatura digital. **Mais informações → Executar assim mesmo.** |
| `permission denied` ao abrir o `nfl-games` ou o `rodar.sh` | Falta a permissão de execução: `chmod +x nfl-games` (ou `rodar.sh`). |
| Primeira subida demora alguns minutos | É o download e a montagem dos dados (~330 MB). O progresso aparece no terminal. |
| `[erro] Sem dados para subir o app` | Primeira subida sem internet. Conecte-se e rode de novo. |
| `[erro] dados locais ilegiveis` | A cópia em `dados/` corrompeu. Apague a pasta e rode de novo (com internet). |
| `503 servidor ocupado` | Mais de 64 requisições simultâneas. O navegador pode tentar de novo em 2 s. |
| `ModuleNotFoundError: pandas` | `python -m pip install pandas numpy` |
| Tela em branco abrindo o arquivo direto | É o caso do `file://`. Acesse por `http://127.0.0.1:8000`. |
| Porta 8000 ocupada | `--port 9000` (no executável, no `rodar.py` ou no `rodar.sh`) |
| Acentos quebrados no terminal do Windows | `$env:PYTHONIOENCODING='utf-8'` antes do comando. |

---

## Requisitos

- Pelo executável: nada (ele traz o Python e as bibliotecas)
- Pelo código: Python 3.10 ou superior (testado no 3.14) com **pandas** e **numpy**
- Um navegador atual
- Internet na primeira execução (depois, opcional)

Sem Node, sem npm, sem etapa de build para rodar a partir do código (o executável é opcional).

---

**Fontes dos dados:** [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY-4.0);
charting de [FTN Data](https://ftndata.com) via nflverse (CC-BY-SA-4.0); estatísticas
avançadas e snaps de [Pro Football Reference](https://www.pro-football-reference.com)
via nflverse; placar ao vivo e matérias da [ESPN](https://www.espn.com/nfl/),
consultados no navegador.
