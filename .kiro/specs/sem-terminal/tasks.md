# Implementation Plan

**Feature:** sem-terminal
**Status:** em revisão
**Data:** 2026-10-01

> **Para agentes:** sub-skill obrigatória: superpowers:subagent-driven-development (recomendada) ou superpowers:executing-plans, tarefa por tarefa. Os passos usam caixas (`- [ ]`) para acompanhar.

**Objetivo:** o `NFL-Games.exe` do Windows abre sem terminal, com a logo na hora, e o app termina pelo menu ("Encerrar o app") ou sozinho quando a última aba fecha; abrir de novo reaproveita a cópia aberta.

**Arquitetura:**
- `rodar.py` ganha um `MODO_JANELA`, só para o executável do Windows, com log, janela de aviso, reaproveitamento da cópia aberta e fechamento da tela de abertura.
- `serve.py` ganha `do_POST`, com duas rotas protegidas (`/api/encerrar` e `/api/presenca`) e uma vigia que usa a classe `Presenca` (`server/presenca.py`).
- A interface dá sinal de presença (`presenca.js`) e tem o item "Encerrar o app".
- O `empacotar.py` gera o `.exe` com `--windowed --splash`.

**Tecnologia:** Python 3.12+ (biblioteca padrão: `http.server`, `ctypes`, `threading`), JS de módulos ES sem build, PyInstaller (`--windowed`, `--splash`), pytest com Playwright e Edge.

**Spec:** `.kiro/specs/sem-terminal/requirements.md` e `design.md`. Leia os dois antes de cada tarefa.

## Restrições globais

- **Escopo:** só o `NFL-Games.exe` do Windows muda de comportamento (`MODO_JANELA = CONGELADO and os.name == "nt"`). O `rodar.py` a partir do código e o executável de Linux ficam exatamente como hoje.
- **Site público:** nada de presença nem de "Encerrar o app" quando `ESTATICO`.
- **Proteção das rotas novas:**
  - cabeçalho `X-NFL-App: 1`;
  - IP em `("127.0.0.1", "::1", "::ffff:127.0.0.1")`;
  - `Origin` ausente ou igual a `http://127.0.0.1:{porta}` / `http://localhost:{porta}`.

  Se falhar: 403 `{"error": "pedido recusado"}`.
- **Tempos:**
  - sinal da página a cada 30 s;
  - encerra com 180 s sem sinal;
  - encerra 15 s depois da saída da última aba;
  - salto de relógio a partir de 60 s zera a contagem;
  - a vigia verifica a cada 5 s;
  - o processo termina em até 5 s depois de "Encerrar" (RNF 2).
- **Textos exatos:**
  - confirmação: `Encerrar o NFL Games? As abas abertas param de funcionar.`, com os botões `Encerrar` e `Cancelar`;
  - tela final: `O NFL Games foi encerrado. Pode fechar esta aba.`;
  - recusa: `Não foi possível encerrar o app`;
  - item do menu: `Encerrar o app`;
  - janela de aviso: título `NFL Games` e texto `O NFL Games não conseguiu abrir.\n\n{motivo}\n\nDetalhes em: {caminho do log}` (sem log: `Detalhes em: sem arquivo de log`).
- **Log:** `dados/nfl-games.log` (UTF-8), recomeçado a cada abertura do `.exe`.
- **Testes:** `NFL_SEM_AVISO=1` faz o `avisar()` escrever no log em vez de abrir a janela, para nenhum teste travar esperando um clique.
- **Dependências e visual:** nenhuma biblioteca nova (RNF 4). Nenhuma cor ou componente novo no CSS: só os tokens e classes que existem.
- **Commits:** um por tarefa, em português, **sem linha de coautoria**. Push e PR só quando o José pedir.
- **Executável:** ao fim de toda tarefa que mexe em `app/`, `server/` ou `rodar.py`, regenerar o `NFL-Games.exe` da raiz e conferir que ele sobe. Se o Windows não deixar trocar o arquivo (app aberto), deixar como `NFL-Games-novo.exe` e avisar.

## Foco de revisão

Situações que a spec implica e que um usuário real vai encontrar. Cada uma tem teste na tarefa dona:

1. **Duas abas do app abertas e uma fecha:** o app continua (a outra segue dando sinal). Teste na tarefa 1 (`test_fechar_uma_de_duas_abas_nao_encerra`).
2. **Abrir o `.exe` de novo enquanto a primeira cópia ainda baixa os dados** (servidor no ar, `pronto: false`): reaproveita, não sobe outra. Teste na tarefa 4 (`test_procurar_copia_acha_copia_ainda_carregando`).
3. **"Encerrar" no meio da primeira carga** (download em andamento): o processo termina em até 5 s, sem esperar a carga. Teste na tarefa 2 (`test_encerrar_forca_a_saida_se_a_carga_nao_terminar`).
4. **`.exe` sem dados e sem internet** (antes: mensagem no terminal e "Pressione Enter"): sai com código 1, com a mensagem no log, sem travar. Teste na tarefa 5 (`test_executavel_sem_dados_explica_no_log_e_sai`).
5. **Corpo estranho no sinal de presença** (vazio, não-JSON, id gigante, mais de 1 KB): 400 ou id cortado, nunca erro 500 nem memória crescendo. Teste na tarefa 2 (`test_presenca_corpo_invalido`) e na 1 (`test_limite_de_abas_e_id_cortado`).

---

## Tarefas

- [x] 1. Regra de presença (`server/presenca.py`)
  - **Arquivos:** criar `server/presenca.py`; testes em `tests/test_presenca.py`.
  - **Produz:**
    - `class Presenca(agora=time.monotonic, limite_s=180.0, saida_s=15.0, salto_s=60.0)`, com os métodos `sinal(aba: str) -> None`, `saiu(aba: str) -> None` e `verificar() -> str | None`;
    - constantes `MAX_ABAS = 100` e `MAX_ID = 64`;
    - os motivos exatos `"a última aba do app foi fechada"` e `"nenhuma aba do app deu sinal em 3 min"`.

    As regras do `verificar()`, e a ordem delas, são as do design (componente 4).
  - [x] 1.1 Escrever os testes, com um relógio falso (`agora` é uma lista mutável lida por uma lambda):
    - `test_nao_encerra_antes_da_primeira_aba`: 1 h sem nada → `verificar() is None`. Com verificações a cada 5 s, para não acionar o salto.
    - `test_encerra_sem_sinal_em_3_min`: sinal em t=0. Em t=179, `None`; em t=180, o motivo dos 3 min.
    - `test_encerra_15_s_depois_da_ultima_saida`: sinal de "a" e saída de "a" em t=10. Em t=24, `None`; em t=25, o motivo da última aba.
    - `test_recarregar_nao_encerra`: saída de "a" em t=10, sinal de "b" em t=12. Em t=40, `None`.
    - `test_fechar_uma_de_duas_abas_nao_encerra`: sinais de "a" e "b"; saída de "a"; sinais de "b" a cada 30 s até t=600 → sempre `None`.
    - `test_salto_de_relogio_recomeca`: sinal em t=0, verificação em t=5, depois t=7205 (o PC dormiu 2 h) → `None`. Sem sinal novo, em t=7205+180, o motivo dos 3 min.
    - `test_limite_de_abas_e_id_cortado`: 150 abas diferentes → no máximo 100 guardadas (as mais antigas saem). Um id de 1.000 caracteres é guardado com 64.
  - [x] 1.2 Rodar `pytest tests/test_presenca.py -v`. Esperado: FAIL (`ModuleNotFoundError: presenca`).
  - [x] 1.3 Implementar `server/presenca.py`. Com um `threading.Lock`, porque a vigia e o handler HTTP rodam em threads diferentes.
  - [x] 1.4 Rodar `pytest tests/test_presenca.py -v`. Esperado: PASS.
  - [x] 1.5 Commit: `Regra de presença das abas para o app se encerrar sozinho (sem-terminal, tarefa 1)`.
  - _Requisitos: 5.3–5.6_

- [x] 2. Rotas de encerrar e de presença no servidor
  - **Arquivos:** modificar `server/serve.py`; testes em `tests/test_encerrar.py`.
  - **Consome:** `Presenca` (tarefa 1).
  - **Produz:**
    - `pedido_confiavel(ip: str, cabecalhos, porta: int) -> bool`;
    - `PARAR = threading.Event()` (o antigo `parar` local do `main()`);
    - `ESTADO["app"] = "NFL Games"`;
    - a opção `--encerrar-sozinho`;
    - `Handler.do_POST` com `POST /api/encerrar` → 200 `{"encerrando": true}` e `POST /api/presenca` → 204;
    - `encerrar_em(segundos: float, terminou: threading.Event, sair=os._exit) -> None`: espera `segundos` pelo `terminou`; se não vier, faz flush do stdout e do stderr e chama `sair(0)`.
    - Variáveis de ambiente lidas na subida: `NFL_PRESENCA_LIMITE_S` e `NFL_PRESENCA_SAIDA_S` (os tempos da `Presenca`) e `NFL_VIGIA_S` (o intervalo da vigia, padrão 5).
  - [x] 2.1 Escrever os testes:
    - `test_pedido_confiavel`, parametrizado: `("127.0.0.1", {"X-NFL-App": "1"})` → True; com `Origin: http://127.0.0.1:{porta}` → True; com `Origin: http://localhost:{porta}` → True; `"::1"` → True; `"192.168.0.10"` → False; sem cabeçalho → False; `Origin: https://exemplo.com` → False; `Origin` em outra porta → False.
    - `test_estado_identifica_o_app`: o `/api/estado` do `servidor_real` traz `"app": "NFL Games"`.
    - `test_rotas_que_mudam_estado_recusam_pedidos_de_fora` (no `servidor_real`, sem derrubar): `POST /api/encerrar` sem o cabeçalho → 403; com o cabeçalho e `Origin: https://exemplo.com` → 403; `GET /api/encerrar` → 404; `OPTIONS /api/encerrar` com `Origin` de fora → não 2xx e sem `Access-Control-Allow-Origin`. Depois, `/api/meta` ainda responde 200.
    - `test_presenca_corpo_invalido`: vazio, `"x"`, `[]` e 2 KB → 400; `{"aba": "t", "saiu": false}` → 204.
    - `test_encerrar_termina_o_processo`: `servidor_local.servidor()` próprio (não o compartilhado) e `POST` com o cabeçalho → 200 `{"encerrando": true}`; o processo sai com 0 em até 5 s.
    - `test_encerra_sozinho_depois_da_ultima_aba`: servidor próprio com `--encerrar-sozinho` e `NFL_PRESENCA_SAIDA_S=1`, `NFL_PRESENCA_LIMITE_S=3`, `NFL_VIGIA_S=0.2`. Um sinal e depois a saída → sai com 0 em até 5 s, e a saída do processo contém `encerrado: a última aba do app foi fechada`.
    - `test_sem_aba_nao_encerra_sozinho`: o mesmo servidor, sem nenhum sinal, continua respondendo depois de 4 s.
    - `test_sem_a_opcao_nao_encerra_sozinho`: sem `--encerrar-sozinho`, com sinal e saída, continua respondendo depois de 4 s.
    - `test_encerrar_forca_a_saida_se_a_carga_nao_terminar`: `encerrar_em(0.2, threading.Event(), sair=lista.append)` → depois de ~0,2 s, `lista == [0]`. Com o evento já setado → `lista == []`.
  - [x] 2.2 Rodar `pytest tests/test_encerrar.py -v`. Esperado: FAIL.
  - [x] 2.3 Implementar no `serve.py`, como no design (componente 5). Detalhes:
    - O `servidor_local` precisa aceitar variáveis de ambiente extras. Ver o parâmetro existente; se não houver, acrescentar `env: dict | None = None`.
    - O corpo do `/api/presenca` é lido com `Content-Length` de no máximo 1024.
    - Depois de responder ao encerrar, `PARAR.set()` e uma thread com `encerrar_em(5, terminou)`. O `terminou` é setado no fim do `main()`.
    - A mensagem final de encerramento é impressa no `main()`.
  - [x] 2.4 Rodar `pytest tests/test_encerrar.py tests/test_servidor_dados.py tests/test_borda_http.py -v` e `python tools/golden.py check`. Esperado: PASS e 2116/2116.
  - [x] 2.5 Regenerar o `.exe` da raiz e conferir que ele sobe.
  - [x] 2.6 Commit: `Servidor: rotas protegidas para encerrar o app e para o sinal das abas, e encerramento sozinho (sem-terminal, tarefa 2)`.
  - **Feito (2026-10-01):** `tests/test_encerrar.py`, 17 testes; golden 2116/2116. O `servidor_local.Servidor` ganhou o campo `proc`, para os testes conferirem a saída do processo.
  - _Requisitos: 2.3, 4.4, 5.3–5.8, RNF 2, segurança 1–4_

- [x] 3. Interface: presença e "Encerrar o app"
  - **Arquivos:**
    - criar `app/js/presenca.js`;
    - modificar `app/index.html` (item `#btnEncerrar` depois de "Configurações", com um `.side-sep` antes, e o `<dialog id="dlgEncerrar">`), `app/js/main.js` e `app/css/app.css`;
    - testes em `tests/test_ui_novo.py`.
  - **Consome:** as rotas da tarefa 2 e `ESTATICO` (`api.js`).
  - **Produz:**
    - `iniciarPresenca({ buscar = fetch, intervaloMs = 30000 } = {}) -> parar()`, que manda `POST /api/presenca` com `X-NFL-App: 1` e `{aba, saiu}`;
    - `encerrarApp()` em `main.js`;
    - o ícone de desligar como SVG em traço, no mesmo estilo dos outros itens do menu (`viewBox 0 0 24 24`, `path` com `M12 4v8` e um arco).
  - [x] 3.1 Escrever os testes, nas duas fontes, com a fixture `servidor` parametrizada que já existe:
    - `test_ui_encerrar_so_no_pc`: em `[servidor]`, `#btnEncerrar` visível no menu; em `[estatico]`, oculto.
    - `test_ui_encerrar_cancelar`, marcado `so_servidor("encerrar o app só existe no PC")`: abre o diálogo com o texto exato; "Cancelar" fecha, e nenhum `POST /api/encerrar` é feito (contado com `page.on("request")`).
    - `test_ui_encerrar_confirmado` (`so_servidor`): `route("**/api/encerrar")` responde 200 `{"encerrando": true}`. Confirmar manda o `POST` com `X-NFL-App: 1`, e a página mostra a tela final com o texto exato. Depois, com `clock.fast_forward(120000)`, nenhum pedido a `/api/` é feito.
    - `test_ui_encerrar_com_o_servidor_ja_parado` (`so_servidor`): `route(...).abort()` → mostra a tela final.
    - `test_ui_encerrar_recusado` (`so_servidor`): `route` responde 403 → aparece o aviso `Não foi possível encerrar o app`, e a tela atual continua.
    - `test_ui_presenca`: em `[servidor]`, há um `POST /api/presenca` logo na abertura e mais um depois de `clock.fast_forward(30000)`, com o mesmo `aba` e `saiu: false`. Em `[estatico]`, nenhum pedido de presença em 60 s.
  - [x] 3.2 Rodar `pytest tests/test_ui_novo.py -k "encerrar or presenca" -v`. Esperado: FAIL.
  - [x] 3.3 Implementar como no design (componente 6).
    - **Presença:** começa no carregamento do `main.js`, antes do `boot()`, para a tela de carregamento também contar. A saída usa `fetch(..., {keepalive: true})` no `pagehide`.
    - **Tela final:** troca o `body.innerHTML` por uma `<main class="encerrado">` com `img/logo.png` e o texto. O CSS centraliza o conteúdo na tela e usa `--text-2`.
    - **Antes de trocar a tela:** chama `TELAS[S.tela].sair?.()` e o `parar()` da presença.
  - [x] 3.4 Rodar `pytest tests/test_ui_novo.py tests/test_ui_dados.py tests/test_ui.py -q`. Esperado: tudo passa nas duas fontes, e os pulados são os `so_servidor` de antes mais os novos.
  - [x] 3.5 Rodar o detector de design do Impeccable nos arquivos de `app/` alterados. Esperado: nenhum achado novo.
  - [x] 3.6 Regenerar o `.exe` da raiz e conferir que ele sobe.
  - [x] 3.7 Commit: `Interface: sinal de presença das abas e "Encerrar o app" no menu (sem-terminal, tarefa 3)`.
  - **Feito (2026-10-01):** 6 testes novos, mais o `test_ui_menu_lateral_itens`, atualizado para considerar só os itens visíveis e esperar "Encerrar o app" no PC. Bateria nas duas fontes verde (315 + 2 corrigidos), sem achados do detector de design.
    - A tela final reaproveita a tela de carregamento (`.carregando.encerrado`), e o aviso de recusa fica dentro do diálogo (`.aviso`): nenhum componente novo.
    - Conferido no app local: encerrar pelo menu terminou o servidor com código 0 ("encerrado pelo app").
    - O `.exe` não foi regenerado nesta tarefa: o da raiz está aberto, e a tarefa 5 o regenera sem console.
  - _Requisitos: 4.1–4.6, 5.1, 5.2_

- [x] 4. `rodar.py` no modo janela
  - **Arquivos:** modificar `rodar.py`; testes em `tests/test_rodar.py`.
  - **Consome:** `/api/estado` com `"app"` (tarefa 2) e `--encerrar-sozinho` (tarefa 2).
  - **Produz:**
    - `MODO_JANELA: bool`;
    - `preparar_saida(dados: Path) -> Path | None`;
    - `avisar(mensagem: str, mostrar=None) -> None`. Com `NFL_SEM_AVISO=1`, só grava `[aviso] {mensagem}` no stdout, que no modo janela é o log;
    - `fechar_abertura() -> None`;
    - `procurar_copia(host: str, portas: range, perguntar=None) -> int | None`;
    - `main(argv=None, modo_janela: bool | None = None) -> int`: `modo_janela=None` usa `MODO_JANELA`, e os testes passam `True`.
  - [x] 4.1 Escrever os testes, com dublês para o navegador, o servidor e a janela de aviso:
    - `test_procurar_copia_acha_o_app`: um `ThreadingHTTPServer` de teste respondendo `{"app": "NFL Games", "pronto": true}` em `/api/estado` → devolve a porta dele.
    - `test_procurar_copia_acha_copia_ainda_carregando`: o mesmo com `"pronto": false` → devolve a porta.
    - `test_procurar_copia_ignora_outro_programa`: um servidor que responde HTML (ou 404) → `None`.
    - `test_modo_janela_reaproveita_a_copia`: `main([], modo_janela=True)` com `procurar_copia` achando 8000 → abre o navegador em `http://127.0.0.1:8000`, não chama `rodar_servidor`, devolve 0 e chama `fechar_abertura`.
    - `test_modo_janela_com_porta_dada_nao_procura`: `main(["--port", "9000"], modo_janela=True)` → `procurar_copia` não é chamado.
    - `test_modo_janela_passa_encerrar_sozinho`: as opções recebidas por `rodar_servidor` contêm `--encerrar-sozinho`. Fora do modo janela, não contêm.
    - `test_modo_janela_erro_avisa_com_o_log`: `rodar_servidor` devolve 1 → `avisar` recebe um texto que começa com `O NFL Games não conseguiu abrir.` e contém o caminho do log. `_esperar_enter` não é chamado.
    - `test_modo_janela_excecao_inesperada`: `rodar_servidor` lança `RuntimeError("x")` → o traceback vai para o log, `avisar` é chamado, e o retorno é 1.
    - `test_preparar_saida_grava_e_recomeca`: grava "a", chama de novo e grava "b" → o arquivo tem só "b".
    - `test_preparar_saida_sem_permissao`: `dados` é um arquivo (não uma pasta) → devolve `None`, sem exceção.
    - `test_avisar_sem_aviso_nos_testes`: com `NFL_SEM_AVISO=1`, o `mostrar` não é chamado, e o stdout recebe a mensagem.
    - Os testes existentes (fora do modo janela) continuam sem mudança.
  - [x] 4.2 Rodar `pytest tests/test_rodar.py -v`. Esperado: FAIL nos testes novos.
  - [x] 4.3 Implementar como no design (componente 3). Detalhes:
    - `fechar_abertura` faz `import pyi_splash` dentro de um `try` e ignora o `ImportError`;
    - `avisar` usa `ctypes.windll.user32.MessageBoxW(None, mensagem, "NFL Games", 0x10)`;
    - `procurar_copia` usa `urllib.request` com timeout de 0,5 s e ignora qualquer exceção.
  - [x] 4.4 Rodar `pytest tests/test_rodar.py -v`. Esperado: PASS.
  - [x] 4.5 Regenerar o `.exe` da raiz e conferir que ele sobe (ainda com console, até a tarefa 5).
  - [x] 4.6 Commit: `rodar.py: no executável do Windows, log, janela de aviso, cópia única e encerramento sozinho (sem-terminal, tarefa 4)`.
  - **Feito (2026-10-01):** `tests/test_rodar.py`, 11 testes novos (32 no total). O `main()` virou um invólucro: no modo janela, ele prepara o log e transforma qualquer exceção numa janela de aviso; o corpo de antes ficou em `_main()`.
    - No modo janela, a mensagem de abertura troca "Ctrl+C para parar" pelo jeito de fechar.
    - O `.exe` não foi regenerado: ver a tarefa 3.
  - _Requisitos: 1.3, 1.4, 2.1–2.3, 3.1–3.5, 5.7_

- [x] 5. Executável sem console, com a logo, e a documentação
  - **Arquivos:**
    - modificar `tools/logo.py` (gera `tools/abertura.png`), `tools/empacotar.py` (no Windows, `--windowed --splash tools/abertura.png`), `tests/test_executavel.py`, `.github/workflows/executaveis.yml` (no Windows, o passo "Conferir o executavel" lê o log) e `README.md`;
    - criar `tools/abertura.png`.
  - **Consome:** tudo das tarefas 1–4.
  - **Produz:**
    - `tools/abertura.png`: 360 × 240 px, RGBA, cartão `--surface` com cantos de 24 px e a logo centralizada a 120 px de altura;
    - `empacotar.argumentos(dist, trabalho)` com `--windowed` e `--splash` no Windows, e `--console` sem `--splash` no Linux.
  - [x] 5.1 Escrever os testes:
    - em `tests/test_infra.py` (rodam sempre, sem empacotar): `test_empacotar_windows_sem_console_com_logo`, que com `os.name` simulado em `"nt"` encontra `--windowed` e `--splash` apontando para `tools/abertura.png`, e não encontra `--console`. `test_empacotar_linux_com_console`: o contrário. `test_abertura_png`: 360 × 240 px e RGBA.
    - em `tests/test_executavel.py` (`NFL_EMPACOTAR=1`):
      - `test_executavel_e_janela`: o campo `Subsystem` do cabeçalho PE é 2 (GUI). Ler o offset em `0x3C`, e depois o subsistema em `offset_PE + 0x5C`.
      - `test_executavel_sem_dados_explica_no_log_e_sai`: substitui o teste antigo; com `NFL_SEM_AVISO=1`, sai com código 1, e `dados/nfl-games.log` contém `Sem dados para subir o app` e `O NFL Games não conseguiu abrir.`.
      - `test_executavel_encerra_pela_rota`: com dados, sobe e cria o log; `POST /api/encerrar` com o cabeçalho → sai com 0 em até 5 s.
      - `test_executavel_segunda_abertura_reaproveita`: com o primeiro no ar (sem `--port`, na porta escolhida por ele), uma segunda abertura sai com 0 em até 15 s, e nenhuma porta nova passa a responder `"app": "NFL Games"` nas portas 8000–8019.
      - O teste "sobe o app com os dados ao lado" passa a ler o caminho dos dados no log, e não no stdout.
  - [x] 5.2 Rodar `pytest tests/test_infra.py -v` e `NFL_EMPACOTAR=1 pytest tests/test_executavel.py -v`. Esperado: FAIL nos novos.
  - [x] 5.3 Implementar: `python tools/logo.py` gera os arquivos (inclusive o `abertura.png`), e mudar o `empacotar.py`. No workflow `executaveis.yml`, a conferência no Windows:
    - passa `NFL_SEM_AVISO=1`;
    - confere o código 1 e procura `Sem dados para subir o app` em `vazio/dados/nfl-games.log`;
    - no Linux, segue lendo a saída, como hoje.
  - [x] 5.4 Rodar `pytest tests/test_infra.py -v` e `NFL_EMPACOTAR=1 pytest tests/test_executavel.py -v`. Esperado: PASS.
  - [x] 5.5 README, em "Como executar → Opção 1":
    - o `.exe` abre sem janela de terminal, com a logo;
    - para fechar: "Encerrar o app" no menu, ou fechar as abas (encerra sozinho em ~15 s, ou em até 3 min);
    - abrir de novo reaproveita a cópia aberta;
    - as mensagens ficam em `dados/nfl-games.log`.

    Atualizar também a tabela de opções e a seção "O que acontece ao abrir", onde citam a janela do terminal.
  - [x] 5.6 Suíte inteira: `pytest -q`. Esperado: tudo passa.
  - [x] 5.7 Regenerar o `.exe` da raiz e conferir que ele sobe, agora sem console.
  - [x] 5.8 Commit: `Executável do Windows sem console e com a logo na abertura; README (sem-terminal, tarefa 5)`.
  - **Feito (2026-10-01):**
    - `test_infra.py`: 3 testes novos. `test_executavel.py` (`NFL_EMPACOTAR=1`): 12 passaram, incluindo o `.exe` de tipo GUI, o log, o encerramento pela rota em menos de 5 s e a segunda abertura reaproveitando a primeira.
    - A logo entrou no pacote (`Splash-00.res` e `tcl9tk90.dll`), mesmo com o `tkinter` fora.
    - Suíte inteira: 575 passaram. Uma falha fora desta branch: `test_montar::test_formacao_e_jogadores_por_temporada` (`KeyError: 'ftn_pendente'`). O PR #14 grava uma coluna nova, e a `dados/` desta máquina foi montada antes dele; o teste passa quando os dados forem remontados.
    - O `argumentos()` ganhou `windows=`, e o `rodar.PORTA_PADRAO` lê `NFL_PORTA_PADRAO`, só para o teste da segunda abertura não achar o app aberto na 8000.
    - **Corrigido nesta tarefa:** o log era recomeçado antes de procurar a cópia aberta, então abrir de novo apagava o log da cópia em uso. Agora ele só recomeça quando o app vai subir de fato (`test_modo_janela_reaproveitar_nao_apaga_o_log_da_copia`).
    - `.exe` gerado: pronto em 4,5 s e encerrado pela rota com código 0. A raiz está travada pelo app aberto, então ele ficou como `NFL-Games-novo.exe`.
  - _Requisitos: 1.1–1.4, 3.1, 3.3, RNF 1, RNF 3, RNF 4_

- [x] Revisão final da branch (revisor independente, 2026-10-02): pronta para merge, com correções. Corrigido, cada item com teste que falhou antes:
  - **Abertura ~10 s mais lenta (Critical):** no Windows, conectar numa porta local fechada leva ~2 s, e o `procurar_copia` tentava as 20 portas com 0,5 s de espera cada. Agora pula as portas livres sem conectar (`test_procurar_copia_rapido_em_portas_livres`).
  - **Sem log, o servidor do `.exe` não respondia a nada:** sem console, `sys.stderr` é `None` e o registro de cada pedido quebrava. Agora, sem log, a saída vai para o nada (`os.devnull`), e o `log_message` não escreve se não houver onde (`test_preparar_saida_sem_permissao_nao_deixa_saida_nula`, `test_servidor_responde_sem_stderr`).
  - **A tela de carregamento mandava olhar "a janela do terminal":** o `/api/estado` passa a dizer `semTerminal`, e a página aponta `dados/nfl-games.log` no `.exe` (`test_estado_diz_se_esta_sem_terminal` e dois testes de interface).
  - **A janela de aviso podia abrir atrás do navegador:** agora usa `MB_SETFOREGROUND | MB_TOPMOST` (`test_avisar_janela_na_frente`).
  - Ficaram para decidir depois os 10 itens Minor listados no relatório (ver o resumo da PR).
  - **Bloqueio do Windows (2026-10-02):** o Controle Inteligente de Aplicativos passou a barrar `pandas/_libs/testing.cp314-win_amd64.pyd`, sem mudança no arquivo (19/09). Os testes que sobem o servidor de verdade e o `.exe` novo ficaram para depois do desbloqueio. Os textos da tela de carregamento foram conferidos com o servidor de arquivos estático.

- [ ] 6. Conferência no PC do José
  - _Depende de: tarefa 5_
  - [ ] 6.1 Pedir ao José para conferir no PC dele, com o `NFL-Games.exe` da raiz:
    - a logo aparece em até ~1 s depois do duplo clique;
    - nenhuma janela preta;
    - o navegador abre no app;
    - "Encerrar o app" fecha de verdade: o processo `NFL-Games` some do Gerenciador de Tarefas;
    - fechar a aba encerra em ~15 s;
    - dois cliques com o app já aberto só abrem o navegador.
  - [ ] 6.2 Medir o tempo até o app ficar pronto e comparar com o de hoje (~7 s, RNF 3), com o `.exe` da raiz e `--sem-navegador`, cronometrando até o `/api/meta` responder 200.
  - [ ] 6.3 Anotar aqui o resultado e qualquer ajuste.
  - _Requisitos: 1.1, 1.2, 4.4, 5.4, RNF 1, RNF 3_

---

## Ordem de execução

```
1 ── 2 ──┬── 3 ──┐
         └── 4 ──┴── 5 ── 6
```

A 3 e a 4 dependem só da 2. A execução segue a numeração.

---

## Mapa de cobertura

| Requisito | Tarefas |
|---|---|
| 1.1, 1.2 | 5, 6 |
| 1.3 | 4, 5 |
| 1.4 | 4 (os testes fora do modo janela), 5 (Linux com console) |
| 2.1, 2.2 | 4, 5 |
| 2.3 | 2, 4 |
| 3.1, 3.2 | 4, 5 |
| 3.3 | 4, 5 |
| 3.4 | 2 (sem mudança na tela de carregamento), 5 |
| 3.5 | 4 |
| 4.1–4.6 | 3 |
| 4.4 (processo termina) | 2, 5 |
| 5.1, 5.2 | 3 |
| 5.3–5.6 | 1, 2 |
| 5.7 | 2, 4 |
| 5.8 | 2 |
| RNF 1 | 6 |
| RNF 2 | 2, 5 |
| RNF 3 | 6 |
| RNF 4 | 5 |
| Segurança 1–4 | 2 |
| Segurança 5 | 4 (o log só recebe o stdout e o stderr de hoje) |

---

## Aprovação

- [x] Toda tarefa referencia pelo menos um requisito
- [x] Todo requisito aparece em pelo menos uma tarefa
- [x] Toda tarefa é verificável isoladamente
- [x] Mapa de cobertura preenchido, incluindo segurança
- [x] Branch `spec/sem-terminal` criada antes da execução
- [ ] Revisado e aprovado pelo José
