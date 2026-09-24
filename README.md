# NFL Games — Treinador · Olheiro · Comentarista

Protótipo de UI ligado aos dados reais do **NFL Big Data Bowl 2023** (semanas 1 a 8 da
temporada 2021). Nenhum número da interface é fictício: tudo vem dos CSVs oficiais do
dataset — 122 jogos, 8.557 jogadas e 810 MB de tracking a 10 quadros por segundo.

**Autoria:** José Cota · Alan Souza · Nilo Reis · José Johnata

---

## Como executar

### Opção 1 — duplo clique (Windows)

```
RODAR.bat
```

Na primeira execução o servidor prepara o cache (~50 s, com o progresso no terminal) e
o navegador abre sozinho quando o app estiver no ar. Nas próximas, sobe em ~3 s.

### Opção 2 — linha de comando

```powershell
# 1. dependência (uma vez)
python -m pip install pandas

# 2. sobe o app (na 1a vez ele mesmo prepara o cache)
python server/serve.py
```

Depois abra **<http://127.0.0.1:8000>**.

O cache é **incremental**: se um CSV de tracking mudar ou uma partida nova for
adicionada, só aquele jogo é reprocessado. Para refazer tudo:
`python etl/build_metrics.py --force`.

Para trocar a porta: `python server/serve.py --port 9000`.

### Por que o `index.html` precisa do servidor

Abrir `app/index.html` com duplo clique **não funciona**. Dois motivos:

1. O dataset tem 810 MB em 122 arquivos CSV — o navegador não consegue ler e cruzar
   isso sozinho; quem faz o trabalho pesado é o Python.
2. Em `file://` o navegador bloqueia as chamadas `fetch()` por política de CORS.

O `server/serve.py` resolve os dois: serve a página e a API JSON no mesmo endereço.
A página em si é um HTML comum, sem build, sem npm, sem framework.

> O servidor escuta só em `127.0.0.1` (sua máquina), é somente leitura e não tem
> autenticação. Se usar `--host 0.0.0.0` para abrir no celular, faça isso apenas em
> rede confiável.

---

## As quatro telas

| Tela | O que mostra | De onde vem |
|---|---|---|
| **Jogos** | Partidas da semana, leituras táticas, jogadores a observar, bastidores | `games.csv`, `plays.csv`, `pffScoutingData.csv` + métricas do tracking |
| **Treinador** | Prancheta com as posições reais dos 22 jogadores, animação quadro a quadro, lista de jogadas, estatísticas e tendências | `tracking_<gameId>.csv` (x, y, velocidade, eventos) |
| **Olheiro** | Busca de jogadores, rating 40–99, radar de atributos por percentil, jogo a jogo, comparação | `players.csv`, `pffScoutingData.csv` + velocidade/deslocamento do tracking |
| **Comentarista** | Replay cronológico com placar, narração e estatísticas acumuladas | `plays.csv` em ordem de `playId` |

Deep link opcional: `?week=3&game=2021092300&screen=coach`.

### Sobre a prancheta do Treinador

O eixo `x` do dataset (0–120 jardas) vai na vertical e o `y` (0–53,3) na horizontal.
Quando `playDirection` é `left`, os dois eixos são espelhados para o **ataque sempre
jogar para cima**. Círculos são ataque, quadrados são defesa, o número é a camisa real.
A linha azul é a linha de scrimmage e a amarela tracejada é a linha da 1ª descida.

---

## Estrutura

```
Projeto/
├─ RODAR.bat                  inicia tudo (Windows)
├─ app/                       a página
│  ├─ index.html              markup
│  ├─ css/app.css             design system do protótipo + componentes novos
│  └─ js/app.js               toda a lógica (JS puro, sem dependências)
├─ etl/
│  └─ build_metrics.py        prepara o cache de forma incremental (ensure_cache)
├─ server/
│  ├─ serve.py                servidor HTTP + API JSON (só stdlib + pandas)
│  ├─ data_layer.py           consultas, ratings e geração de insights
│  ├─ response_cache.py       respostas prontas da API em memória (calcula cada uma 1 vez)
│  ├─ tracking_npz.py         formato binário do tracking de um jogo
│  ├─ teams.py                nomes e cores das 32 franquias
│  ├─ smoke_test.py           testa a camada de dados
│  ├─ ui_test.py              testa a home num navegador headless
│  └─ ui_test_all.py          testa as 4 telas num navegador headless
├─ tools/                     golden (regressão), bench (1 usuário), carga (N usuários)
├─ tests/                     pytest + testes de navegador (Playwright com o Edge)
├─ .kiro/specs/               specs SDD (requirements, design, tasks)
├─ cache/                     gerado automaticamente, ~120 MB (não versionar)
└─ nfl-big-data-bowl-regional-event-data-main/data/    dataset original
```

---

## Métricas derivadas do tracking

O ETL (`etl/build_metrics.py`) percorre os 122 arquivos em ~20 s e calcula:

- **Tempo para lançar** — do snap até o release. Média 3,10 s, mediana 2,80 s.
  Por resultado: completo 2,80 s, incompleto 3,19 s, sack 4,42 s.
- **Tempo até a pressão** — quando o primeiro pass rusher chega a 2 jardas do QB.
  Acontece em 34,5% dos dropbacks; concorda com as flags do PFF em 82% dos casos.
- **Velocidade de pico** por jogador. Líderes: Brandin Cooks 22,9 mph, Quez Watkins
  22,1, Henry Ruggs 21,8, Tyreek Hill 21,3.
- **Profundidade de rota** — deslocamento entre snap e release. Rotas 9,2 jd,
  pass set 4,0 jd, dropback do QB 3,6 jd.

### Como o rating é calculado

Não é nota inventada. Para cada função (`pff_role`) os jogadores são comparados
**entre si** em 5 eixos, cada um virando um percentil de 0 a 100:

| Função | Eixos |
|---|---|
| Quarterback | Precisão · Produção · Rapidez · Cuidado · Sob pressão |
| Pass rusher | Pressão · Finalização · Chegada · Explosão · Velocidade |
| Protetor | Proteção · Sacks cedidos · Consistência · Recuo · Volume |
| Recebedor | Velocidade · Profundidade · Explosão · Volume · Versatilidade |
| Cobertura | Velocidade · Alcance · Blitz · Volume · Versatilidade |

O rating é `40 + média dos percentis × 0,59`, o que dá a escala 40–99. Quem não bate o
mínimo de snaps (75 para QB, 50 para as demais, 30 para rotas) aparece como `n/d` em
vez de receber uma nota com amostra fraca.

Conferência de sanidade: Myles Garrett 97, Tom Brady 87, Brian Burns 91,
Sam Darnold 59 — coerente com a temporada 2021.

---

## Limites do dataset (a interface avisa isso na tela)

- **Só existem jogadas de passe.** O Big Data Bowl 2023 é sobre proteção e pressão,
  então não há corridas, chutes nem retornos. Por isso a tela de estatísticas fala em
  "dropbacks", e não em jardas totais do jogo.
- **O placar é aproximado.** O `plays.csv` só traz o placar *antes* de cada dropback.
  Pontos marcados depois do último dropback (field goal decisivo, TD terrestre) não
  aparecem. Exemplo: TB × DAL na semana 1 fecha em 28–29 no app, quando o oficial foi
  31–29.
- **O tracking termina pouco depois do lançamento.** Os eventos de recepção são raros,
  então não há métrica confiável de alvos, recepções ou separação do recebedor.

---

## API

Todos os endpoints são `GET` e devolvem JSON.

| Rota | Retorno |
|---|---|
| `/api/meta` | temporada, semanas, 32 times, médias da liga, limitações |
| `/api/games?week=3` | partidas da semana |
| `/api/games/{id}` | detalhe + estatísticas + insights + bastidores + destaques |
| `/api/games/{id}/plays` | todas as jogadas do jogo |
| `/api/games/{id}/plays/{pid}/tracking` | quadros de todos os 22 jogadores + bola |
| `/api/games/{id}/plays/{pid}/formation` | posições no instante do snap |
| `/api/games/{id}/broadcast` | feed cronológico narrado |
| `/api/players?q=&position=&role=&limit=` | busca de jogadores |
| `/api/players/{nflId}` | perfil completo com radar e jogo a jogo |
| `/api/compare?a=&b=` | comparação entre dois jogadores |
| `/api/leaders?metric=&role=` | ranking por métrica |

Exemplo:

```powershell
curl http://127.0.0.1:8000/api/leaders?metric=pressureRate&role=Pass+Rush&limit=5
```

---

## Verificação

```powershell
python -m pip install -r requirements-dev.txt   # pytest + playwright (uma vez)

python -m pytest                  # 39 testes (~80 s); cada um sobe seu próprio servidor
python -m pytest -m lento         # preparo completo do cache do zero (~50 s)
python tools/golden.py check      # prova que nenhuma resposta da API mudou (2.159 URLs)
python tools/bench.py --check     # tempo por rota com 1 usuário, contra as metas
python tools/carga.py --usuarios 10 --check   # 10 usuários ao mesmo tempo
```

Os testes de navegador usam o **Edge já instalado** (não rode `playwright install`).
O `tests/golden/hashes.json` é a "foto" das respostas da versão original: se uma
mudança alterar qualquer número da API, o `golden.py check` aponta a URL. Só refaça a
foto (`capture`) quando a mudança de dados for intencional, como ao trocar o dataset.

Os testes de fumaça antigos continuam valendo (esses precisam do servidor rodando):

```powershell
python server/smoke_test.py      # camada de dados
python server/ui_test.py         # home renderizada num navegador headless
python server/ui_test_all.py     # as 4 telas
```

---

## Desempenho

Otimizado pela spec `.kiro/specs/otimizacao-desempenho/` (meta: uma banca de 10
pessoas usando ao mesmo tempo). Medido nesta máquina, com os mesmos números na tela:

| Medida | Antes | Depois |
|---|---|---|
| 10 usuários simultâneos, p95 | 1.502 ms | 263–393 ms; mediana 289 (meta 300; ver abaixo) |
| 10 usuários simultâneos, p50 | 457 ms | 24–29 ms |
| 25 usuários simultâneos | 5 conexões recusadas | 0 recusadas, p95 ~650 ms |
| Tela inicial pronta | ~340 ms | ~40 ms |
| Abrir jogada, 1º acesso ao jogo | 144 ms | 30–38 ms |
| Abrir jogada, jogo já aberto | 52 ms | 8–10 ms |
| Avançar para a próxima jogada | ~65 ms | 5–6 ms (pré-carregada) |
| Detalhe do jogo | 111 ms | 0 ms (em cache) |
| Busca de 300 jogadores | 25 ms | 17–21 ms |

Como: respostas prontas em memória (cada uma calculada uma vez, pré-aquecidas ao
subir), tracking em formato binário por jogo, montagem das jogadas com numpy,
pré-carga das jogadas vizinhas no navegador e descarte de respostas atrasadas.

O cache binário ocupa **~111 MB** em `cache/tracking/` (1 arquivo por jogo).

**Sobre a meta de 10 usuários:** o teste de carga dispara as requisições sem pausa
entre cliques (mais agressivo que pessoas reais), e o p95 oscila entre rodadas em
torno da meta de 300 ms. O custo que sobra é descomprimir o tracking de cada jogo aberto
pela primeira vez (~25 ms). Detalhes e opções em
`.kiro/specs/otimizacao-desempenho/tasks.md` (tarefa 9).

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| A página abre com o aviso "API indisponível" | O servidor não está de pé. Rode `python server/serve.py`. |
| Primeira subida demora ~50 s | É o preparo do cache (só na 1ª vez ou quando o dataset muda). O progresso aparece no terminal. |
| `[aviso] <jogo>.npz ilegivel` no terminal | O arquivo do cache daquele jogo corrompeu. O app segue funcionando (lê o CSV original); ele é regenerado ao reiniciar o servidor. |
| `503 servidor ocupado` | Mais de 64 requisições simultâneas. O navegador pode tentar de novo em 2 s. |
| `ModuleNotFoundError: pandas` | `python -m pip install pandas` |
| Tela em branco abrindo o arquivo direto | É o caso do `file://`. Acesse por `http://127.0.0.1:8000`. |
| Porta 8000 ocupada | `python server/serve.py --port 9000` |
| Acentos quebrados no terminal do Windows | `$env:PYTHONIOENCODING='utf-8'` antes do comando. |

---

## Requisitos

- Python 3.10 ou superior (testado no 3.14) com **pandas**
- Um navegador atual
- O dataset em `nfl-big-data-bowl-regional-event-data-main/data/`

Sem Node, sem npm, sem etapa de build.

---

**Fonte dos dados:** NFL Big Data Bowl 2023 — tracking do NFL Next Gen Stats,
avaliações de [Pro Football Focus](https://www.pff.com/).
