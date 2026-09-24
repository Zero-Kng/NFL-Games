# Requirements Document

**Feature:** otimizacao-desempenho
**Status:** aprovado
**Data:** 2026-09-24 (v0.2: perguntas em aberto respondidas)
**Autores:** José Cota (com Claude)

---

## Introduction

O NFL Games nasceu no hackathon AWS × NFL como protótipo sobre o dataset do Big Data Bowl 2023. Com **um único usuário na máquina local** ele já responde rápido: a tela inicial fica pronta em cerca de 340 ms e trocar de jogada leva cerca de 65 ms. O problema aparece quando **várias pessoas usam o app ao mesmo tempo**. Com 10 usuários simultâneos o tempo de resposta no p95 sobe de 115 ms para 1,6 s, cerca de 14 vezes mais lento. Com 25 usuários o servidor **recusa conexões**. O cenário-alvo é uma **banca de 10 pessoas usando o app ao mesmo tempo**, e hoje ele não aguenta esse cenário.

Esta feature torna o app rápido e estável sob uso simultâneo e reduz a espera nos três fluxos mais usados: abrir o app, abrir uma jogada na prancheta e navegar entre jogadas. Nenhuma tela, número ou texto muda para o usuário: o que muda é quanto tempo ele espera.

Restrições de contexto que o implementador precisa respeitar:

- **Os dados exibidos são o contrato.** Todo valor que a interface mostra hoje (ratings, percentis, insights, placares, posições do tracking) deve continuar idêntico. Otimização que muda um número é regressão.
- **O app continua sem etapa de build** no navegador e continua subindo com um único comando (ou duplo clique no `RODAR.bat`).
- O dataset original é somente leitura: não se edita nem se apaga nada nele.
- **O dataset não será a única fonte para sempre.** A equipe pretende trazer partidas de outras APIs no futuro. Nenhuma otimização pode depender de o conjunto de partidas ser fixo: acrescentar uma partida nova não pode exigir reprocessar todas as outras.

### Linha de base (medida em 2026-09-24, nesta máquina, dados reais)

| Medida | Hoje | Observação |
|---|---|---|
| Inicialização do servidor | 2,2 s | carga + pré-cálculos |
| Tela inicial pronta (1 usuário) | ~340 ms | 3 chamadas em sequência; o detalhe do jogo sozinho leva 110–230 ms |
| Abrir jogada, primeiro acesso ao jogo | ~150 ms no servidor, ~200 ms no navegador | |
| Abrir jogada, jogo já acessado | ~50 ms no servidor | |
| Trocar para a próxima jogada | ~65 ms | nada é pré-carregado |
| 1 usuário simultâneo (sessão típica) | p50 49 ms · p95 115 ms | |
| 10 usuários simultâneos | p50 403 ms · **p95 1.578 ms** | tracking p95 1.783 ms |
| 25 usuários simultâneos | **conexões recusadas** | o servidor continua de pé, mas rejeita as conexões |
| Memória do servidor | 261 MB, pico de 434 MB | |
| Arquivos da página (CSS/JS) | baixados de novo a cada visita | nunca reaproveitados |

"Sessão típica" = abrir um jogo, listar as jogadas, abrir 3 jogadas na prancheta, abrir o comentarista e a lista do olheiro (7 requisições).

---

## Fora de escopo

- **Mudanças visuais ou de conteúdo.** Nenhuma tela, texto ou layout novo. Redesign é outra spec.
- **Novas funcionalidades** (novas métricas, novos endpoints de negócio, filtros novos).
- **Publicar na nuvem.** Esta spec deixa o app *pronto* para suportar vários usuários; o deploy em si (infraestrutura, domínio, HTTPS) é outra spec.
- **Autenticação e contas de usuário.**
- **Reorganizar o código por estética.** Só se reestrutura o que for necessário para atingir uma meta desta spec.
- **Recalcular as métricas do ETL com outra metodologia.** A forma de calcular tempo para lançar, pressão etc. não muda.
- **Suporte a mais de uma instância do servidor** (balanceamento). A meta é uma instância aguentar a carga-alvo.
- **Carga acima de 10 usuários simultâneos.** Acima disso, só se exige falhar de forma explícita (Requisito 1.4), não manter o tempo de resposta.
- **Animação mais fluida da prancheta** (interpolar entre os quadros de 10 fps). Fica para a spec de UX.
- **Integração com APIs de outras partidas.** Fica para uma spec futura. Esta spec só não pode impedi-la (ver restrições acima).
- **O protótipo `ui_kiro/`.** Foi só o esboço inicial e não é usado pelo app.

---

## Requirements

### Requisito 1: Atender vários usuários ao mesmo tempo

**História de usuário:** Como apresentador do app para uma banca, quero que as 10 pessoas da banca naveguem juntas sem travar, para que a demonstração não dependa de só uma pessoa usar por vez.

**Critérios de aceitação:**

1. ENQUANTO 10 usuários executarem simultaneamente a sessão típica, O SISTEMA DEVE responder a todas as requisições com p95 de no máximo 300 ms.
2. ENQUANTO 10 usuários executarem simultaneamente a sessão típica, O SISTEMA DEVE aceitar 100% das conexões.
3. ENQUANTO 10 usuários executarem simultaneamente a sessão típica, O SISTEMA DEVE devolver exatamente as mesmas respostas que devolveria a um usuário sozinho.
4. SE a demanda ultrapassar a capacidade de atendimento, ENTÃO O SISTEMA DEVE responder com erro explícito de "serviço ocupado, tente novamente", em vez de recusar a conexão ou deixar a requisição sem resposta.
5. SE uma requisição falhar com erro interno, ENTÃO O SISTEMA DEVE continuar atendendo as demais requisições em andamento.

### Requisito 2: Abrir uma jogada na prancheta rapidamente

**História de usuário:** Como treinador, quero que a jogada apareça na prancheta assim que eu a escolho, para que eu estude várias jogadas sem ficar esperando.

**Critérios de aceitação:**

1. QUANDO o usuário abrir uma jogada de um jogo que ninguém acessou desde que o servidor subiu, O SISTEMA DEVE devolver os quadros do tracking em no máximo 60 ms no servidor.
2. QUANDO o usuário abrir uma jogada de um jogo já acessado, O SISTEMA DEVE devolver os quadros do tracking em no máximo 20 ms no servidor.
3. QUANDO o usuário abrir qualquer jogada, O SISTEMA DEVE exibir as mesmas posições, velocidades, orientações e eventos que exibe hoje, sem nenhuma diferença.
4. SE a jogada pedida não tiver tracking, ENTÃO O SISTEMA DEVE responder "tracking indisponível" em no máximo 20 ms, como faz hoje.
5. SE os dados de tracking de um jogo estiverem ausentes ou ilegíveis, ENTÃO O SISTEMA DEVE responder com erro explícito para aquele jogo e continuar servindo os demais.

### Requisito 3: Navegar entre jogadas sem espera

**História de usuário:** Como treinador, quero avançar e voltar entre jogadas sem nenhuma espera perceptível, para que a análise tenha o ritmo de assistir a um replay.

**Critérios de aceitação:**

1. QUANDO o usuário avançar ou voltar para a jogada vizinha, O SISTEMA DEVE exibi-la na prancheta em no máximo 50 ms.
2. QUANDO o usuário trocar de jogada várias vezes antes de a anterior terminar de carregar, O SISTEMA DEVE exibir somente a última jogada escolhida.
3. SE a antecipação de uma jogada vizinha falhar, ENTÃO O SISTEMA DEVE carregá-la normalmente quando o usuário a escolher, sem exibir erro.
4. SE a antecipação de jogadas vizinhas estiver em andamento, ENTÃO O SISTEMA DEVE atender primeiro a jogada que o usuário escolheu.

### Requisito 4: Abrir o app e trocar de jogo rapidamente

**História de usuário:** Como qualquer usuário, quero ver as partidas e as sugestões táticas logo ao abrir o app, para que a primeira impressão seja de um produto pronto.

**Critérios de aceitação:**

1. QUANDO o usuário abrir o app, O SISTEMA DEVE exibir a lista de partidas e as sugestões táticas do primeiro jogo em no máximo 200 ms na máquina local.
2. QUANDO o usuário selecionar outro jogo, O SISTEMA DEVE exibir sugestões táticas, destaques e bastidores em no máximo 60 ms no servidor.
3. QUANDO o usuário voltar a abrir o app em uma segunda visita, O SISTEMA DEVE reaproveitar a página, o estilo e o script já baixados, se não tiverem mudado.
4. SE a página, o estilo ou o script tiverem mudado desde a visita anterior, ENTÃO O SISTEMA DEVE entregar a versão nova na mesma visita.
5. SE a fonte externa de tipografia não carregar, ENTÃO O SISTEMA DEVE exibir o conteúdo com a fonte alternativa, sem atrasar a primeira exibição.

### Requisito 5: Busca do olheiro coerente

**História de usuário:** Como olheiro, quero que a lista mostre sempre o resultado do que eu digitei por último, para que eu não tome decisão olhando o resultado de uma busca antiga.

**Critérios de aceitação:**

1. QUANDO o usuário digitar na busca, O SISTEMA DEVE exibir o resultado correspondente ao texto final digitado.
2. SE a resposta de uma busca anterior chegar depois da resposta da busca atual, ENTÃO O SISTEMA DEVE descartá-la sem exibir.
3. QUANDO o usuário buscar jogadores, O SISTEMA DEVE responder em no máximo 30 ms no servidor, para até 300 resultados.

### Requisito 6: Manter o que já funciona

**História de usuário:** Como autor do projeto, quero que a otimização não mude nenhum número nem piore nada que hoje é bom, para que eu confie no app depois da mudança.

**Critérios de aceitação:**

1. O SISTEMA DEVE devolver, em cada rota da API, o mesmo conteúdo que a versão atual devolve para as mesmas entradas.
2. O SISTEMA DEVE ficar pronto para atender em no máximo 5 s após ser iniciado, em uma máquina onde os dados pré-processados já existam.
3. QUANDO o app for iniciado pela primeira vez, sem dados pré-processados, O SISTEMA DEVE prepará-los automaticamente em no máximo 90 s e informar o progresso no terminal.
4. SE os dados pré-processados estiverem ausentes, incompletos ou desatualizados em relação ao dataset, ENTÃO O SISTEMA DEVE detectar isso ao iniciar e regerá-los, em vez de servir dados inconsistentes.
5. O SISTEMA DEVE manter o uso de memória do servidor em no máximo 600 MB durante a carga do Requisito 1.

---

## Requisitos não funcionais

1. O SISTEMA DEVE incluir um roteiro de medição reproduzível que gere a tabela de linha de base desta spec, para comparar antes e depois de cada tarefa.
2. O SISTEMA DEVE registrar, em cada resposta da API, o tempo gasto no servidor, como já faz hoje.
3. O SISTEMA DEVE continuar executando no Windows com duplo clique no `RODAR.bat`, sem passos manuais novos.

> Todas as metas de tempo valem para esta máquina de desenvolvimento (Windows 11, Python 3.14), medidas pelo roteiro do NFR 1. Em outra máquina, vale a proporção em relação à linha de base medida nela.

---

## Requisitos de segurança

A superfície de segurança é pequena: o app é somente leitura, não tem identidade, pagamento nem dado pessoal sensível. Mas a feature mexe em dois pontos de entrada externa: guardar arquivos no navegador e aceitar mais conexões. Por isso:

1. SE uma requisição pedir um arquivo fora da pasta pública do app, ENTÃO O SISTEMA DEVE recusá-la com status 403, inclusive quando a resposta viria de um cache.
2. SE uma requisição da API trouxer parâmetro fora do formato esperado, ENTÃO O SISTEMA DEVE rejeitá-la com status 400 antes de consultar os dados, como faz hoje.
3. SE o número de requisições pendentes ultrapassar o limite configurado, ENTÃO O SISTEMA DEVE rejeitar as excedentes com status 503, para que uma rajada não esgote a memória do servidor.
4. O SISTEMA DEVE continuar escutando apenas na máquina local por padrão.

---

## Perguntas em aberto

- [x] **Q1. Carga-alvo?** Resposta: **10 usuários simultâneos** (uma banca). Aplicado no Requisito 1 e no Fora de escopo.
- [x] **Q2. Dependências novas?** Resposta: **pode adicionar.** A equipe pretende consumir APIs de outras partidas no futuro. Isso virou uma restrição na Introdução.
- [x] **Q3. O pré-processamento pode ocupar mais disco?** Resposta: **ainda não decidido**, mas a percepção é que o cache atual ajuda mais do que atrapalha. A pergunta **passa para o design.md**, que vai comparar as opções com números (disco, tempo de preparo, ganho de tempo) e trazer uma recomendação para decisão. Os requisitos não dependem dessa escolha.
- [x] **Q4. Animação mais fluida?** Resposta: **fica para a spec de UX.** Movido para o Fora de escopo.
- [x] **Q5. O `ui_kiro/` é usado?** Resposta: **não**, foi só o protótipo inicial. Movido para o Fora de escopo.

---

## Aprovação

- [x] Cada critério tem exatamente um DEVE
- [x] Cada critério nomeia um teste possível
- [x] Todo requisito tem pelo menos um SE...ENTÃO
- [x] Nenhuma tecnologia mencionada neste arquivo (exceto `RODAR.bat`, que é o contrato de execução do usuário)
- [x] Seção de fora de escopo preenchida
- [x] Perguntas em aberto respondidas (Q3 transferida ao design com justificativa)

**Aprovado por:** José Cota em 2026-09-24. Os requisitos serão revistos numa spec futura, quando os dados passarem a vir de APIs.
