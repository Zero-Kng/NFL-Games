# Design Document

**Feature:** sem-terminal
**Workflow:** requirements-first
**Status:** em revisão
**Data:** 2026-10-01

---

## Overview

O `NFL-Games.exe` do Windows passa a abrir sem console, com a tela de abertura nativa do PyInstaller mostrando a logo. Sem terminal, o ciclo de vida do app muda em três pontos:

- **Uma cópia só:** antes de subir, o `rodar.py` procura um NFL Games já rodando e, se achar, só abre o navegador nele.
- **Encerrar:** o menu lateral ganha "Encerrar o app", que chama uma rota protegida do servidor (`POST /api/encerrar`). A rota aciona o mesmo sinal de parada do Ctrl+C.
- **Encerrar sozinho:** cada aba do app dá sinal de presença a cada 30 s (`POST /api/presenca`). Sem sinal de nenhuma aba, o servidor do `.exe` se encerra: em 3 min, ou em 15 s depois que a última aba avisar a saída.

As mensagens que hoje vão para o terminal passam a ir para `nfl-games.log`, ao lado dos dados. Erros que impedem o app de abrir aparecem numa janela de aviso do Windows.

O que fica igual:
- o `rodar.py` a partir do código e o executável de Linux, com terminal;
- o site público;
- as telas, exceto o item novo do menu, a confirmação e a tela final.

---

## Architecture

### Visão de alto nível

```
duplo clique ─► NFL-Games.exe (--windowed, --splash tools/abertura.png)
                 │  logo na tela enquanto descompacta
                 ▼
               rodar.py  (MODO_JANELA = executável no Windows)
                 ├─ stdout/stderr ─► dados/nfl-games.log (recomeçado a cada abertura)
                 ├─ procurar_copia(8000..8019) ─ achou? ─► abre o navegador, fecha a logo, sai
                 ├─ escolher_porta (como hoje)
                 ├─ vigiar_e_abrir ─► abre o navegador ─► fecha a logo
                 └─ serve.main(--encerrar-sozinho)
                       ├─ GET  /api/estado        {"app": "NFL Games", ...}
                       ├─ POST /api/presenca      {aba, saiu}  ─► Presenca
                       ├─ POST /api/encerrar                    ─► PARAR.set()
                       └─ vigia (5 s): Presenca.verificar() ─ motivo? ─► log + PARAR.set()

navegador (app do PC)
   presenca.js: a cada 30 s POST /api/presenca; ao fechar (pagehide) POST {saiu: true}, keepalive
   menu: "Encerrar o app" ─► confirmação ─► POST /api/encerrar ─► tela final
```

### Fluxo: encerrar pelo menu (Requisito 4)

1. A pessoa toca em "Encerrar o app". Abre um `<dialog>` com "Encerrar o NFL Games? As abas abertas param de funcionar." e os botões **Encerrar** e **Cancelar**.
2. **Encerrar** manda `POST /api/encerrar`, com `X-NFL-App: 1`.
3. **Resposta 200, ou falha de rede** (o servidor já tinha parado): a página para os próprios timers (presença, placar ao vivo, carrossel, replay) e troca o conteúdo pela tela final.
4. **Resposta 403 ou outro erro:** aparece o aviso "Não foi possível encerrar o app", e a página segue.
5. **No servidor:** responde 200 e, logo depois de enviar a resposta, aciona `PARAR`. O laço principal sai do `parar.wait(...)`, chama `httpd.shutdown()`, e `main()` devolve 0.
6. **Se o servidor estiver no meio de uma carga longa** (o download da 1ª vez não olha o `PARAR`), uma thread `encerrar_em(5, terminou)` força a saída do processo (`os._exit(0)`, depois do flush do log) se o `main()` não terminar em 5 s (RNF 2). Os arquivos de dados são gravados de forma atômica (`.tmp` e depois `os.replace`), então a saída forçada não deixa arquivo pela metade.

### Fluxo: encerrar sozinho (Requisito 5)

- **Sinal de presença:** cada aba gera um id ao carregar (`crypto.randomUUID()`). Ela manda `{aba, saiu: false}` na abertura e a cada 30 s. No `pagehide`, manda `{aba, saiu: true}` com `fetch(..., {keepalive: true})`. O `sendBeacon` não serve, porque não manda o cabeçalho `X-NFL-App`.
- **Registro:** a classe `Presenca` guarda o último sinal de cada aba.
- **Vigia:** uma thread do servidor chama `verificar()` a cada 5 s. Com `--encerrar-sozinho` e um motivo devolvido, grava o motivo no log e aciona `PARAR`.

---

## Components and Interfaces

### 1. `tools/logo.py` e `tools/abertura.png`

- **Geração:** o `tools/logo.py` passa a gerar também `tools/abertura.png`, a imagem da tela de abertura. É um cartão de 360 × 240 px no fundo do app (`--surface`, com cantos arredondados), com a logo no centro a 120 px de altura. Fica em `tools/`, porque não faz parte da interface servida.
- **Versionamento:** o arquivo vai para o Git, como os outros gerados pelo `logo.py`.

### 2. `tools/empacotar.py`

- `argumentos(dist, trabalho)`: no Windows, `--console` vira `--windowed`, e entra `--splash tools/abertura.png`.
- No Linux, continua `--console` e sem a tela de abertura.
- Nenhuma biblioteca nova. A tela de abertura usa o Tcl/Tk que o próprio PyInstaller embute (conferido: o Python do PC tem o Tk 9.0, e o do GitHub Actions também).

### 3. `rodar.py`

```python
MODO_JANELA = CONGELADO and os.name == "nt"           # o .exe do Windows, sem console

def preparar_saida(dados: Path) -> Path | None
    # MODO_JANELA: sys.stdout e sys.stderr passam para dados/nfl-games.log (modo "w", utf-8,
    # buffer de linha). Cria a pasta dados/ se faltar. OSError: devolve None e segue sem log.

def avisar(mensagem: str, mostrar=None) -> None
    # janela de aviso do Windows (ctypes.windll.user32.MessageBoxW, título "NFL Games",
    # ícone de erro). `mostrar` injetável nos testes.
    # Com NFL_SEM_AVISO=1 (testes e GitHub Actions), só grava a mensagem no log: uma janela
    # de aviso travaria o teste esperando um clique.

def fechar_abertura() -> None
    # fecha a tela de abertura (pyi_splash.close()); sem tela de abertura, não faz nada

def procurar_copia(host: str, portas: range, perguntar=None) -> int | None
    # GET http://127.0.0.1:{p}/api/estado com timeout de 0,5 s; a 1ª porta cuja resposta for
    # JSON com "app" == "NFL Games". `perguntar` injetável nos testes.
```

Mudanças no `main()`, só com `MODO_JANELA`:

1. `preparar_saida(dados)` antes de tudo.
2. `procurar_copia(args.host, range(8000, 8020))`, só quando `--port` não foi dado. Achou: abre o navegador, chama `fechar_abertura()` e devolve 0.
3. Passa `--encerrar-sozinho` ao servidor.
4. `vigiar_e_abrir` chama `fechar_abertura()` depois de pedir ao navegador para abrir.
5. **Servidor que devolve código ≠ 0, ou exceção inesperada** (com o traceback no log): `fechar_abertura()` e depois `avisar("O NFL Games não conseguiu abrir.\n\n<motivo>\n\nDetalhes em: <caminho do log>")`.
6. O `_esperar_enter()` deixa de ser chamado nesse modo, porque não há terminal.

Fora do `MODO_JANELA`, o `main()` fica exatamente como hoje.

### 4. `server/presenca.py` (novo)

```python
class Presenca:
    def __init__(self, agora=time.monotonic, limite_s=180.0, saida_s=15.0, salto_s=60.0): ...
    def sinal(self, aba: str) -> None       # registra/atualiza a aba e cancela uma saída pendente
    def saiu(self, aba: str) -> None        # tira a aba; se não sobrou nenhuma, marca o instante da saída
    def verificar(self) -> str | None       # motivo para encerrar, ou None
```

Regras do `verificar()`, em ordem:

1. **Salto de relógio:** se o intervalo desde a última chamada passou de `salto_s` (o PC dormiu, ou o processo ficou parado), recomeça tudo: todas as abas contam como vistas agora, a saída pendente é cancelada, e devolve `None`.
2. **Nenhuma aba deu sinal desde a abertura:** devolve `None`.
3. **Não sobrou aba e a saída tem pelo menos `saida_s`:** devolve `"a última aba do app foi fechada"`.
4. **Todas as abas estão sem sinal há pelo menos `limite_s`:** devolve `"nenhuma aba do app deu sinal em 3 min"`.

Os limites podem ser trocados por variáveis de ambiente (`NFL_PRESENCA_LIMITE_S`, `NFL_PRESENCA_SAIDA_S`, e `NFL_VIGIA_S` para o intervalo da vigia) para os testes de integração. O id da aba é cortado em 64 caracteres, e há no máximo 100 abas guardadas: uma página não consegue encher a memória.

### 5. `server/serve.py`

- **Identificação:** `ESTADO` ganha `"app": "NFL Games"` e passa a sair no `/api/estado`.
- **Sinal de parada:** o `parar` local do `main()` vira o `PARAR = threading.Event()` do módulo, para a rota de encerrar alcançá-lo.
- **`--encerrar-sozinho`:** opção nova. Liga a thread vigia descrita no Fluxo.
- **`do_POST`** (o handler só tinha `do_GET`). Atende duas rotas; qualquer outra dá 404:
  - `POST /api/encerrar` → `{"encerrando": true}`. O `PARAR.set()` acontece depois de enviar a resposta.
  - `POST /api/presenca` com o corpo `{"aba": str, "saiu": bool}` (até 1 KB) → 204. Corpo inválido dá 400.
- **Proteção** das duas rotas, numa função testável à parte:

  ```python
  def pedido_confiavel(ip: str, cabecalhos, porta: int) -> bool
      # ip em ("127.0.0.1", "::1", "::ffff:127.0.0.1")
      # e cabecalhos["X-NFL-App"] == "1"
      # e (sem Origin, ou Origin em {http://127.0.0.1:{porta}, http://localhost:{porta}})
  ```

  Falhou: 403 `{"error": "pedido recusado"}`.
- **CORS:** nenhuma resposta manda `Access-Control-Allow-*`, e `OPTIONS` continua sem tratamento (501). Com isso, uma página de fora não consegue mandar o `X-NFL-App`: o pedido de checagem prévia do navegador (preflight) falha.
- **Log no encerramento:** a mensagem final no terminal ou no log diz o motivo: "encerrado pelo app", "encerrado: a última aba do app foi fechada" ou "encerrado: nenhuma aba do app deu sinal em 3 min".

### 6. `app/js/presenca.js` (novo) e `app/js/main.js`

```js
export function iniciarPresenca({ buscar = fetch, intervaloMs = 30000 } = {})   // devolve parar()
```

- **Quando roda:** só fora do site (`!ESTATICO`). O `main.js` chama `iniciarPresenca()` no carregamento do módulo, antes do `boot()`, para a tela de carregamento também contar.
- **Falhas:** um sinal que falha (servidor ainda subindo ou já parado) é ignorado em silêncio.

**Menu e encerramento:**
- **No `index.html`:** depois de "Configurações", entra um separador e o botão `#btnEncerrar`, oculto por padrão, com ícone de desligar e o texto "Encerrar o app". Entra também o `<dialog id="dlgEncerrar">`.
- **No `main.js`:**
  - mostra o botão quando `!ESTATICO`;
  - abre o diálogo;
  - no "Encerrar", chama `encerrarApp()`:
    1. `POST`;
    2. para a presença e o `sair()` da tela atual;
    3. troca o `<body>` pela tela final: a logo e "O NFL Games foi encerrado. Pode fechar esta aba.".
- **CSS:** o diálogo e a tela final usam os tokens e componentes que já existem (`.card`, `.chip`, `.state`). Nenhuma cor nova.

---

## Data Model

Nada persistente, além do log:

| Arquivo | Conteúdo | Ciclo de vida |
|---|---|---|
| `dados/nfl-games.log` | o que hoje sai no terminal: progresso da carga, avisos, erros, tracebacks e o motivo do encerramento | recomeçado a cada abertura do `.exe` |

`Presenca` fica só em memória: `{aba: último sinal}`, o instante da saída e o da última verificação.

---

## Error Handling

| Falha | Detecção | Resposta | Requisito |
|---|---|---|---|
| Nenhuma porta livre (8000–8019) e nenhuma cópia aberta | `escolher_porta` | `avisar` com a mensagem e o log; sai com 1 | 3.3 |
| Exceção inesperada no `rodar.py` | `except Exception` no `main()` (só `MODO_JANELA`) | traceback no log, `avisar`, sai com 1 | 3.3 |
| Servidor devolve ≠ 0 (porta tomada no meio, erro de carga) | código de `rodar_servidor` | `avisar`; o erro da carga já apareceu na tela de carregamento | 3.3, 3.4 |
| `dados/` sem permissão de escrita | `OSError` no `preparar_saida` | segue sem log; as janelas de aviso continuam | 3.5 |
| "Encerrar" com o servidor já parado | `fetch` rejeita | tela final do mesmo jeito | 4.5 |
| "Encerrar" recusado | 403 | aviso "Não foi possível encerrar o app" | 4.6 |
| Sinal de presença falha | `fetch` rejeita | ignorado; a contagem do servidor é folgada (3 min) | 5.1 |
| PC dormiu | salto > 60 s entre verificações | recomeça a contagem | 5.6 |
| Pedido de fora da máquina, sem cabeçalho ou de outra origem | `pedido_confiavel` | 403, nada muda | Seg. 1–3 |

---

## Segurança

- **As duas rotas novas mudam o estado do servidor.** A defesa tem três camadas:
  - IP da própria máquina;
  - cabeçalho próprio, que obriga a checagem prévia de CORS para qualquer origem de fora, e o servidor nunca a autoriza;
  - `Origin` igual ao do app.
- **Com `--host 0.0.0.0`:** o resto da API continua acessível na rede, como hoje, mas encerrar e dar presença só valem da própria máquina.
- **Limites do corpo:** o pedido de presença aceita no máximo 1 KB, e o id da aba vai cortado. Nenhum texto do pedido vai para o log.

---

## Testing Strategy

1. **`tests/test_presenca.py`** (unitário, relógio falso):
   - não encerra antes da 1ª aba;
   - encerra com 3 min sem sinal;
   - encerra 15 s depois que a última aba sai;
   - recarregar a página (sai uma aba, entra outra em menos de 15 s) não encerra;
   - um salto de 2 h recomeça a contagem;
   - o limite de 100 abas e o corte do id funcionam.
2. **`tests/test_encerrar.py`** (servidor real via `servidor_local`):
   - `POST /api/encerrar` com `X-NFL-App: 1` responde 200, e o processo termina com código 0 em até 5 s (RNF 2);
   - sem o cabeçalho, com `Origin: https://exemplo.com`, com `GET`, e com um `OPTIONS` de outra origem, a resposta é 403 (ou 501/405) e o servidor continua respondendo `/api/meta`;
   - `pedido_confiavel` tem casos unitários para IP de rede, IPv6 local e as origens;
   - `/api/estado` traz `"app": "NFL Games"`;
   - com `--encerrar-sozinho` e limites curtos por variável de ambiente, um sinal seguido de uma saída termina o processo, e sem nenhum sinal ele continua rodando.
3. **`tests/test_rodar.py`** (dublês, sem janela de verdade):
   - `procurar_copia` acha a cópia num servidor de teste que responde `"app": "NFL Games"` e ignora outro programa na porta;
   - no `MODO_JANELA`, `main()` com uma cópia achada só abre o navegador;
   - erro fatal chama `avisar` com o caminho do log;
   - `preparar_saida` grava no log e segue sem ele quando a pasta é somente leitura.
4. **`tests/test_ui_novo.py`** (Playwright, nas fontes `servidor` e `estatico`):
   - o item existe e está visível no PC, e não existe visível no site;
   - "Cancelar" fecha o diálogo sem pedido;
   - "Encerrar" manda o `POST` com o cabeçalho e mostra a tela final. O pedido é interceptado com `route()`, para não derrubar o servidor compartilhado;
   - recusa (403) mostra o aviso;
   - falha de rede mostra a tela final;
   - o sinal de presença sai na abertura e a cada 30 s (relógio do Playwright) no PC, e nunca no site;
   - depois da tela final, nenhum pedido ao servidor em 2 min.
5. **`tests/test_executavel.py`** (`NFL_EMPACOTAR=1`):
   - o `.exe` gerado tem o subsistema GUI no cabeçalho PE (valor 2);
   - sobe, cria o `nfl-games.log` e termina com `POST /api/encerrar`;
   - uma segunda abertura, com a primeira rodando, sai em poucos segundos sem subir outra porta.
6. **Conferência manual (José):**
   - logo na tela em até 1 s depois do duplo clique (RNF 1);
   - nenhuma janela preta;
   - "Encerrar o app" fecha de verdade (o processo some do Gerenciador de Tarefas);
   - fechar a aba encerra em ~15 s.

---

## Decisões e alternativas descartadas

### Decisão 1: tela de abertura do PyInstaller, sem linha de estado
- **O que não entra:** a linha de estado exigiria trocar a linha de comando do PyInstaller por um arquivo `.spec` gerado, e quase não apareceria: o navegador abre em ~1 s com a tela de carregamento, que já mostra o progresso.
- **O que fica:** só a logo.

### Decisão 2: batimento da página, e não "fechou o navegador"
- **O problema:** o servidor não tem como saber se o navegador foi fechado.
- **A saída:** o sinal periódico, com a saída avisada no `pagehide`. Ele cobre abas, janelas e o navegador inteiro.
- **Os tempos:** 3 min é folgado, porque o Chrome e o Edge reduzem timers de abas em segundo plano para cerca de 1 por minuto. 15 s depois da saída cobre o recarregar da página.

### Decisão 3: `fetch` com `keepalive`, e não `sendBeacon`
- O `sendBeacon` não manda cabeçalhos próprios e seria recusado pela proteção.
- O `fetch` com `keepalive` manda o `X-NFL-App` (é o mesmo endereço do app, então não há checagem prévia) e continua depois que a página fecha.

### Decisão 4: encerrar sozinho só no `.exe`
- A partir do código, quem roda o `rodar.py` está num terminal e espera que o servidor fique de pé até o Ctrl+C. O `--encerrar-sozinho` é passado só pelo `MODO_JANELA`.

### Decisão 5: reaproveitar a cópia só no `.exe` do Windows
- No Linux e no `rodar.py` o comportamento atual (subir na próxima porta livre) continua, como pede o critério 1.4.

---

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Antivírus implicando com executável "janela" feito pelo PyInstaller | O Windows bloqueia ou atrasa a abertura | É o mesmo empacotador de hoje. A assinatura do executável (outra ideia da lista) é a solução definitiva. |
| Navegador que não manda o aviso de saída (fechamento forçado) | O app leva 3 min, e não 15 s, para encerrar | Aceitável: o limite de 3 min encerra do mesmo jeito. |
| Aba em segundo plano congelada pelo navegador (economia de energia) | O app se encerra com a aba ainda aberta, mas parada | Ao voltar, a aba mostra o erro de conexão. Abrir o `.exe` de novo resolve. Registrado no log. |
| Mensagem de erro fatal sem log (pasta protegida) | A janela de aviso não tem o caminho do log | A mensagem diz "sem arquivo de log" no lugar do caminho. |

---

## Aprovação

- [ ] Revisado e aprovado pelo José
