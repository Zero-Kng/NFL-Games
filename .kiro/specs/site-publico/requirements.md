# Requirements Document

**Feature:** site-publico
**Status:** em revisão
**Data:** 2026-09-27
**Autores:** José Cota (com Claude)

---

## Introduction

Hoje o NFL Games só abre onde o servidor Python roda: no PC, pelo `NFL-Games.exe` ou pelo `rodar.py`. Um celular só o acessa na mesma rede do PC, com `--host 0.0.0.0` e com o IP da máquina descoberto à mão. O time quer **abrir o app pelo celular em qualquer lugar, sem o PC ligado**, por um link público.

Esta feature publica o app no **GitHub Pages** (`https://zero-kng.github.io/NFL-Games/`), com os dados exportados em arquivos e atualizados **uma vez por dia** pelo GitHub Actions. Todas as telas continuam disponíveis, com os mesmos números do app do PC, para as temporadas de 2021 a 2026.

**O link tem de ser tão funcional quanto o app do PC** (pedido do José). Toda função do PC funciona no link, e a prova é a mesma bateria de testes de interface rodando contra os dois (critérios 1.6 e 1.7). A única diferença aceita é que o celular precisa de internet: a cópia local offline continua sendo do PC.

Restrições de contexto:

- **A interface atual já é a versão de celular.** Ela foi desenhada para celular (spec `novo-visual`) e é exatamente ela que vai para o Pages. Esta spec **não muda nada do visual**: layout, telas, CSS e textos continuam como estão, exceto a mensagem de erro de abertura (critério 4.3), que hoje manda rodar o servidor. No futuro, o PC ganha um visual próprio (outra spec), e o atual segue como o do celular.
- **Os dados são o contrato.** Cada número mostrado no Pages é igual ao que o servidor mostra para a mesma tela, na mesma data.
- **O app do PC continua igual.** O `serve.py`, o `rodar.py` e o `NFL-Games.exe` seguem funcionando como hoje, inclusive sem internet.
- **O Pages só serve arquivos.** Não roda Python e tem limite de 1 GB por site. Os dados somados passam de 1,9 GB sem compressão.
- **Os dados não entram no Git.** O repositório não pode voltar a crescer com dados (o dataset antigo, 826 MB, ainda pesa no histórico).
- **O repositório é público.** O Pages e os minutos do Actions são gratuitos.

---

## Fora de escopo

- **Mudar o visual, as telas ou os textos** (exceto o critério 4.3). O visual separado do PC é outra spec.
- **Instalar como app na tela inicial (PWA) e funcionar sem internet no celular.** O celular precisa de conexão; a cópia local offline continua sendo do app do PC.
- **Domínio próprio.** O endereço é o do GitHub Pages.
- **Atualização mais de uma vez por dia.** Durante os jogos, o placar ao vivo continua vindo da ESPN pelo navegador, como hoje.
- **A rota `/api/leaders`**, que a interface não usa.
- **Contas de usuário, estatísticas de acesso e notificações.**

---

## Requirements

### Requisito 1: Link público

**História de usuário:** Como usuário, quero abrir o NFL Games no celular por um link, em qualquer lugar, para consultar jogos e jogadores sem depender do PC ligado.

**Critérios de aceitação:**

1. O SISTEMA DEVE estar disponível em `https://zero-kng.github.io/NFL-Games/`.
2. QUANDO o usuário abrir o link, O SISTEMA DEVE mostrar a mesma interface do app do PC, com as mesmas telas e o mesmo menu.
3. O SISTEMA DEVE oferecer no link as temporadas de 2021 a 2026, com temporada regular e playoffs.
4. O SISTEMA DEVE funcionar no link sem que nenhum computador da equipe esteja ligado.
5. O SISTEMA DEVE continuar funcionando no PC (executável, `rodar.py` e `serve.py`) como antes desta feature, inclusive com `--offline`.
6. O SISTEMA DEVE oferecer no link todas as funções do app do PC: trocar temporada e semana, jogos da semana com placar ao vivo, filtro por time, carrossel e tela de notícias, busca geral, tela Jogo (resumo, jogadas, prancheta, replay e matéria da ESPN), jogadores (lista, filtros, perfil, comparação), configurações salvas no aparelho, "Sobre os dados" e links diretos para uma tela, temporada, semana, jogo, jogada ou jogador.
7. O SISTEMA DEVE passar no link a mesma bateria de testes de interface do app do PC, exceto os testes das funções que só existem no PC (tela de carregamento do servidor e respostas simuladas do servidor), listados no design.

### Requisito 2: Mesmos dados do PC

**História de usuário:** Como usuário, quero ver no celular os mesmos números que vejo no PC, para confiar no que o app mostra em qualquer um dos dois.

**Critérios de aceitação:**

1. QUANDO o site e o servidor usarem a mesma cópia dos dados e a mesma data, O SISTEMA DEVE mostrar no site as mesmas respostas do servidor para meta, jogos da semana, jogo, jogadas, transmissão, prancheta, jogadores, perfil, comparação, notícias e resumo.
2. QUANDO o usuário buscar ou filtrar jogadores (nome, posição, grupo, time, só avaliados e limite), O SISTEMA DEVE devolver os mesmos jogadores, na mesma ordem, que o servidor.
3. QUANDO o usuário comparar dois jogadores, O SISTEMA DEVE aplicar a mesma regra do servidor: só comparar estatísticas de jogadores do mesmo grupo.
4. O SISTEMA DEVE calcular o status de cada jogo sem placar ("a jogar" antes do início, "resultado ainda não disponível" depois) pela hora do aparelho, e não pela hora da exportação.
5. O SISTEMA DEVE calcular a semana atual de cada temporada pela data de hoje no horário de Nova York, e não pela data da exportação.
6. SE o usuário pedir um jogo, uma jogada, uma prancheta ou um jogador que não existe, ENTÃO O SISTEMA DEVE mostrar a mesma mensagem de "não encontrado" que o app do PC mostra.

### Requisito 3: Atualização diária

**História de usuário:** Como usuário, quero que o site tenha os jogos e as estatísticas de ontem, para acompanhar a temporada atual pelo celular.

**Critérios de aceitação:**

1. O SISTEMA DEVE atualizar os dados do site uma vez por dia, a partir das fontes do nflverse.
2. QUANDO houver mudança na interface ou no cálculo dos dados na branch principal, O SISTEMA DEVE publicar o site de novo, sem esperar a atualização do dia.
3. O SISTEMA DEVE permitir que a equipe dispare uma publicação manual.
4. SE a atualização ou a exportação falhar, ENTÃO O SISTEMA DEVE manter o site com a última versão publicada e avisar a equipe.
5. ENQUANTO uma nova versão estiver sendo publicada, O SISTEMA DEVE continuar servindo a versão anterior completa, nunca uma mistura das duas.
6. O SISTEMA DEVE mostrar na tela "Sobre os dados" a data da última atualização dos dados publicados.

### Requisito 4: Erros no celular

**História de usuário:** Como usuário no celular, quero entender o que houve quando algo não carrega, para saber se tento de novo ou se o problema é do meu aparelho.

**Critérios de aceitação:**

1. SE a conexão cair enquanto uma tela carrega, ENTÃO O SISTEMA DEVE mostrar o estado de erro da tela com a opção de tentar de novo, como no app do PC.
2. SE o navegador não conseguir descompactar os dados de um jogo, ENTÃO O SISTEMA DEVE mostrar na tela Jogo que o navegador precisa ser atualizado, e as outras telas DEVEM continuar funcionando. <!-- critério composto de propósito: a segunda parte é a garantia de isolamento da falha -->
3. SE os dados não puderem ser carregados na abertura, ENTÃO O SISTEMA DEVE mostrar no site "Não foi possível carregar os dados. Verifique a conexão e tente de novo.", sem mencionar o servidor ou o `rodar.py`.
4. QUANDO uma nova versão for publicada enquanto o usuário navega, O SISTEMA DEVE ler os arquivos seguintes de uma única versão, sem misturar dados de dias diferentes na mesma tela.

---

## Requisitos não funcionais

1. O SISTEMA DEVE ocupar no máximo 1 GB no GitHub Pages, com as 6 temporadas.
2. O SISTEMA DEVE transferir no máximo 1 MB até a tela Início ficar pronta, com o cache do navegador vazio (interface, fontes e dados).
3. O SISTEMA DEVE transferir no máximo 400 KB ao abrir um jogo, incluindo a primeira prancheta.
4. O SISTEMA DEVE concluir a publicação diária (sincronizar, montar, exportar e publicar) em até 30 minutos.
5. O SISTEMA DEVE usar só recursos gratuitos do GitHub para um repositório público.

---

## Requisitos de segurança

A feature torna o app **público na internet**. Os dados continuam sendo só dados públicos do nflverse e da ESPN, sem nada pessoal.

1. O SISTEMA DEVE publicar somente a interface e os dados exportados, nunca código do servidor, `dados/brutos/`, testes ou arquivos de configuração.
2. O SISTEMA DEVE dar ao processo de publicação só as permissões necessárias para publicar no Pages (sem escrita no repositório).
3. SE um texto vindo dos dados contiver marcação HTML ou script, ENTÃO O SISTEMA DEVE exibi-lo como texto literal, como já faz no PC.
4. O SISTEMA DEVE ler dados somente de arquivos do próprio site e dos endereços da ESPN já usados hoje.

---

## Perguntas em aberto

- [x] **Q1. Onde publicar?** Resposta: **GitHub Pages** ("por enquanto, pode ser pelo github").
- [x] **Q2. Com que frequência atualizar?** Resposta: **uma vez por dia**.
- [x] **Q3. Quais telas e temporadas?** Resposta: **tudo igual ao PC**, com as 6 temporadas. A interface atual já é a do celular.
- [x] **Q4. Abordagem?** Resposta: **exportar as respostas da API em arquivos** (abordagem A do design).

---

## Aprovação

- [x] Cada critério tem exatamente um DEVE (exceto o 4.2, composto de propósito)
- [x] Cada critério nomeia um teste possível
- [x] Todo requisito tem pelo menos um SE...ENTÃO
- [x] Nenhuma tecnologia mencionada neste arquivo, exceto GitHub Pages e GitHub Actions, que são a plataforma escolhida pelo José (Q1)
- [x] Seção de fora de escopo preenchida
- [x] Perguntas em aberto respondidas
- [ ] Revisado e aprovado pelo José
