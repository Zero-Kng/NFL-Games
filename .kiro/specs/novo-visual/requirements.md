# Requirements Document

**Feature:** novo-visual
**Status:** aprovado (v0.4, retomada sobre os dados do nflverse)
**Data:** 2026-09-26 (v0.2: perguntas Q1–Q5 respondidas · v0.3: notícia de placar adiada para `dados-externos` · **v0.4: retomada depois da `dados-externos`; Q6–Q9 respondidas**)
**Autores:** José Cota (com Claude)

---

## Introduction

> **v0.4 (2026-09-26):** a spec foi escrita sobre o dataset do Big Data Bowl e pausada para os dados virem primeiro. Com a `dados-externos` na `main`, o app tem 2021 até a temporada atual (com playoffs), placar oficial e ao vivo, a matéria da ESPN, a prancheta como **esquema ilustrativo** (sem tracking) e ratings por grupo de posição. Esta revisão ajusta os requisitos a isso: notícias com tipos novos (Q6), **sem prancheta animada** (Q7, o antigo Requisito 10 saiu), Configurações enxutas (Q8) e a matéria no topo da página Jogo (Q9).

Hoje o app tem quatro telas: **Jogos** (home), **Treinador** (prancheta com o esquema da formação, lista de jogadas, estatísticas e playbook), **Olheiro** (busca e avaliação de jogadores) e **Comentarista** (replay narrado com placar). O visual é o do protótipo do hackathon. A equipe desenhou um novo visual no `rascunho/`: fundo escuro, cartões em camadas, ícones em traço, cabeçalho com menu lateral e busca, filtros de temporada e semana, carrossel de notícias e barra inferior flutuante.

Esta feature aplica esse visual a **todo** o app e reorganiza as telas:

- **Treinador + Comentarista viram uma página só, "Jogo"**, organizada em abas. Ela fica na barra inferior, junto com Início, Jogadores e Notícias.
- **O menu lateral ganha "Configurações"**, com preferências de exibição.
- **Olheiro passa a se chamar Jogadores**, e recebe os "jogadores a observar" do jogo selecionado, que hoje ficam na home.
- **"Sugestões de tática" e "Bastidores" deixam de existir.**
- **Notícias** passam a existir, **geradas a partir dos dados reais**. Não há texto inventado.

Restrições de contexto que o implementador precisa respeitar:

- **Os dados continuam sendo o contrato.** Todo número exibido vem dos dados (nflverse, e a ESPN no navegador), como hoje. A tela muda; os valores não. Nenhuma notícia pode conter fato ou número que não esteja nos dados.
- **O rascunho é a referência visual, não o conteúdo.** Os dados de exemplo dele (temporadas 2018–2020, notícias escritas à mão, ratings inventados) não entram no app.
- **As conquistas da spec `dados-externos` não podem regredir:** temporadas e rodadas de playoff, estados do cartão de jogo (a jogar, sem resultado, encerrado, **AO VIVO**), matéria da ESPN só com link `*.espn.com`, prancheta ilustrativa com aviso, "formação indisponível", blocos sem dado ocultos e "Sobre os dados" com os créditos.
- **As conquistas da spec `otimizacao-desempenho` não podem regredir:** tempos de resposta, descarte de respostas atrasadas, pré-carga de jogadas e as metas do teste de carga.
- **O app continua sem etapa de build** e sobe com o `RODAR.bat`.

---

## Fora de escopo

- **Novas fontes de dados.** Ficam as da `dados-externos` (nflverse no servidor, ESPN no navegador).
- **Mudar o que a API calcula.** Ratings, percentis, esquema da prancheta e narração continuam como estão; informação nova entra por rotas novas.
- **Prancheta animada.** Não há tracking nas fontes públicas: a prancheta é o esquema ilustrativo de um quadro (Q7).
- **Versão desktop própria.** Continua o layout de celular, centralizado em telas grandes, como no rascunho.
- **Contas e favoritos.** As configurações do Requisito 11 valem só para o aparelho em que foram feitas; não há login nem sincronização.
- **Tradução para outros idiomas.**

---

## Requirements

### Requisito 1: Identidade visual do rascunho em todas as telas

**História de usuário:** Como usuário, quero que o app inteiro tenha o visual novo, para que ele pareça um produto só e não um protótipo remendado.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir todas as telas com as cores, tipografia, cantos arredondados, ícones e espaçamentos definidos no rascunho aprovado.
2. O SISTEMA DEVE exibir no topo de todas as telas o botão de menu, o escudo com o título da tela atual e o botão de busca.
3. ENQUANTO a tela for mais larga que um celular, O SISTEMA DEVE exibir o app centralizado numa moldura de celular.
4. SE o usuário tiver pedido redução de movimento no sistema operacional, ENTÃO O SISTEMA DEVE exibir as telas sem animações de transição.
5. SE as fontes externas não carregarem, ENTÃO O SISTEMA DEVE exibir o conteúdo com a fonte do sistema, sem atrasar a primeira exibição.

### Requisito 2: Navegação principal com quatro destinos

**História de usuário:** Como usuário, quero chegar em qualquer parte do app com um toque, para que eu não precise saber onde cada função ficava antes.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir uma barra inferior com quatro destinos: Início, Jogo, Jogadores e Notícias.
2. QUANDO o usuário tocar num destino da barra, O SISTEMA DEVE exibir a tela correspondente e destacar o destino ativo.
3. QUANDO o usuário abrir o menu lateral, O SISTEMA DEVE listar os mesmos quatro destinos e os itens "Sobre os dados" e "Configurações".
4. O SISTEMA DEVE deixar de exibir os nomes "Treinador", "Olheiro" e "Comentarista" em qualquer tela.
5. QUANDO o usuário tocar fora do menu lateral ou pressionar Esc, O SISTEMA DEVE fechar o menu.
6. SE o usuário abrir um link antigo que aponte para Treinador, Comentarista ou Olheiro, ENTÃO O SISTEMA DEVE abrir a tela nova equivalente, com o mesmo jogo e a mesma semana.

### Requisito 3: Filtros de temporada e semana só com dados reais

**História de usuário:** Como usuário, quero escolher a semana dos jogos, para que eu veja só o que aconteceu naquele período.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir no filtro de temporada somente as temporadas que existem nos dados.
2. O SISTEMA DEVE exibir no filtro de semana somente as semanas que existem na temporada escolhida, com o nome da rodada nos playoffs.
3. QUANDO o usuário escolher uma semana, O SISTEMA DEVE atualizar a lista de jogos, os cartões de resumo e as notícias para aquela semana.
4. SE os dados de uma semana não puderem ser carregados, ENTÃO O SISTEMA DEVE exibir uma mensagem de erro no lugar da lista, mantendo os filtros utilizáveis.
5. QUANDO o app abrir sem semana escolhida, O SISTEMA DEVE mostrar a semana mais recente já começada da temporada atual.

### Requisito 4: Início

**História de usuário:** Como usuário, quero ver de relance o que aconteceu na semana, para que eu decida o que explorar.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir no Início, nesta ordem: o carrossel de principais notícias da semana, os dois cartões de resumo e a lista de jogos da semana.
2. O SISTEMA DEVE exibir no cartão "Partidas na semana" a quantidade real de jogos da semana escolhida.
3. O SISTEMA DEVE exibir no cartão de jogadores a quantidade real de jogadores com avaliação na temporada escolhida.
4. QUANDO o usuário tocar numa partida, O SISTEMA DEVE abrir a página do jogo com aquela partida.
5. ENQUANTO o carrossel estiver visível e o usuário não estiver interagindo com ele, O SISTEMA DEVE avançar para a notícia seguinte a cada 5 segundos.
6. SE o usuário tiver pedido redução de movimento, ENTÃO O SISTEMA DEVE deixar de avançar o carrossel sozinho.
7. SE uma semana não tiver notícias geradas, ENTÃO O SISTEMA DEVE exibir no carrossel as notícias da semana anterior mais recente da mesma temporada que tiver notícias, com o nome dessa semana; e, se nenhuma tiver, ocultar o carrossel e manter o restante do Início. *(Revisto em 2026-10-01, a pedido do José: antes, a semana sem notícias só ocultava o carrossel.)*
8. O SISTEMA DEVE exibir na lista de jogos os mesmos estados de hoje: a jogar, resultado ainda não disponível, encerrado e AO VIVO (placar ao vivo da spec `dados-externos`).

### Requisito 5: Página "Jogo" (Treinador + Comentarista)

**História de usuário:** Como alguém analisando uma partida, quero a prancheta, as jogadas e o replay narrado na mesma página, para que eu não precise alternar entre dois modos para entender um jogo.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir no topo da página Jogo o placar, os dois times e a semana (ou rodada) da partida selecionada.
2. O SISTEMA DEVE organizar a página Jogo em cinco abas: Prancheta, Jogadas, Replay, Estatísticas e Playbook.
3. O SISTEMA DEVE oferecer nas abas Prancheta, Jogadas, Estatísticas e Playbook todas as funções que existiam no Treinador.
4. O SISTEMA DEVE oferecer na aba Replay todas as funções que existiam no Comentarista: replay cronológico com narração, placar do momento e estatísticas acumuladas.
5. QUANDO o usuário tocar numa jogada na aba Jogadas ou na aba Replay, O SISTEMA DEVE abrir a aba Prancheta com essa jogada.
6. QUANDO o usuário trocar de aba, O SISTEMA DEVE manter a partida e a jogada selecionadas.
7. SE o usuário abrir a página Jogo sem ter escolhido uma partida, ENTÃO O SISTEMA DEVE abrir a primeira partida da semana selecionada.
8. SE a jogada não tiver formação, ENTÃO O SISTEMA DEVE exibir os dados da jogada com o aviso "formação indisponível para esta jogada" no lugar da prancheta.
9. O SISTEMA DEVE exibir logo abaixo do placar da página Jogo a matéria do jogo da ESPN (título, resumo, data, fonte e link), com as regras da spec `dados-externos`: só link `*.espn.com`, e o bloco some se a matéria não existir ou falhar.

### Requisito 6: Jogadores (antigo Olheiro)

**História de usuário:** Como olheiro, quero buscar, avaliar e comparar jogadores e ver os destaques do jogo que estou analisando, para que eu encontre quem merece atenção.

**Critérios de aceitação:**

1. O SISTEMA DEVE oferecer na tela Jogadores todas as funções do antigo Olheiro: busca, filtro por posição, lista por rating, perfil com radar de atributos, jogo a jogo e comparação, na temporada escolhida.
2. O SISTEMA DEVE exibir na tela Jogadores a seção "Jogadores a observar" referente à partida selecionada.
3. QUANDO o usuário trocar a partida selecionada, O SISTEMA DEVE atualizar os "Jogadores a observar".
4. SE nenhum jogador da partida tiver amostra suficiente para avaliação, ENTÃO O SISTEMA DEVE ocultar a seção "Jogadores a observar".

### Requisito 7: Notícias geradas a partir dos dados

**História de usuário:** Como torcedor, quero ler os fatos marcantes da semana em forma de manchete, para que eu saiba rápido o que foi notável sem abrir cada jogo.

**Critérios de aceitação:**

1. O SISTEMA DEVE gerar as notícias da semana exclusivamente a partir de fatos presentes nos dados, destes tipos: resultado, virada, prorrogação, goleada, maior jogada da semana, grande atuação individual e grande atuação defensiva de um time.

> **Histórico:** na v0.3 a notícia de resultado tinha saído, porque o placar do dataset antigo era o do último dropback (TB × DAL aparecia 28–29; o oficial foi 31–29 para o TB). Com o placar oficial do nflverse, ela volta na v0.4 e diz quem venceu. "Mais rápido" e "pocket mais longo" saíram: vinham do tracking.
2. O SISTEMA DEVE exibir em cada notícia o jogo a que ela se refere.
3. O SISTEMA DEVE ordenar as notícias da semana pelo quanto o fato foge da média da liga, do mais incomum para o menos incomum.
4. O SISTEMA DEVE exibir no carrossel do Início as 4 primeiras notícias da semana.
5. QUANDO o usuário tocar numa notícia, O SISTEMA DEVE abrir a página Jogo da partida correspondente.
6. SE uma semana ainda não tiver jogos disputados, ENTÃO O SISTEMA DEVE exibir uma mensagem informando que não há notícias para a semana.

### Requisito 8: Busca geral

**História de usuário:** Como usuário, quero buscar um time, um jogador ou uma notícia a partir de qualquer tela, para que eu chegue direto ao que procuro.

**Critérios de aceitação:**

1. QUANDO o usuário tocar na lupa, O SISTEMA DEVE abrir o campo de busca por cima do cabeçalho, já com o cursor nele.
2. QUANDO o usuário digitar, O SISTEMA DEVE exibir os resultados agrupados em Times, Jogadores e Notícias.
3. QUANDO o usuário tocar num resultado, O SISTEMA DEVE abrir o time (seus jogos na semana), o perfil do jogador ou a página do jogo da notícia.
4. SE a busca não tiver resultados, ENTÃO O SISTEMA DEVE exibir a mensagem "Nada encontrado" com o termo buscado.
5. SE a resposta de uma busca anterior chegar depois da busca atual, ENTÃO O SISTEMA DEVE descartá-la sem exibir.
6. QUANDO o usuário tocar em Cancelar ou pressionar Esc, O SISTEMA DEVE fechar a busca e limpar o termo.

### Requisito 9: Seções que deixam de existir

**História de usuário:** Como equipe, queremos remover o que não entra no novo produto, para que a interface fique enxuta.

**Critérios de aceitação:**

1. O SISTEMA DEVE deixar de exibir a seção "Sugestões de tática" em qualquer tela.
2. O SISTEMA DEVE deixar de exibir a seção "Bastidores do jogo" em qualquer tela. (Os fatos que ela mostrava passam a aparecer como notícias, pelo Requisito 7.)

### Requisito 10: (removido na v0.4)

A prancheta com movimento contínuo dependia do tracking quadro a quadro do dataset antigo, que não existe nas fontes públicas. A prancheta segue como o esquema ilustrativo da spec `dados-externos`, só com o visual novo (Q7).

### Requisito 11: Configurações

**História de usuário:** Como usuário, quero ajustar como o app se comporta, para que ele se adapte ao meu jeito de usar.

**Critérios de aceitação:**

1. QUANDO o usuário tocar em "Configurações" no menu lateral, O SISTEMA DEVE exibir a tela de Configurações.
2. O SISTEMA DEVE oferecer nas Configurações: ligar ou desligar o avanço automático das notícias e escolher a velocidade do Replay narrado (0,5×, 1× ou 2×).
3. QUANDO o usuário mudar uma configuração, O SISTEMA DEVE aplicá-la imediatamente, sem recarregar a página.
4. QUANDO o usuário voltar ao app no mesmo aparelho, O SISTEMA DEVE manter as configurações que ele escolheu.
5. SE as configurações salvas não puderem ser lidas, ENTÃO O SISTEMA DEVE usar os valores padrão: avanço automático ligado e Replay em 1×.

---

## Requisitos não funcionais

1. O SISTEMA DEVE manter as metas da spec `otimizacao-desempenho`: tela inicial pronta em até 200 ms, próxima jogada em até 50 ms e p95 de até 300 ms com 10 usuários com pausa entre cliques.
2. O SISTEMA DEVE manter idênticas as respostas atuais da API (o golden de 2.116 URLs da spec `dados-externos` continua passando). Informação nova, como notícias, entra por caminhos novos.
3. O SISTEMA DEVE ter todos os alvos de toque com pelo menos 44 × 44 px.
4. O SISTEMA DEVE ter todo texto com contraste de pelo menos 4,5:1 sobre o fundo (WCAG AA).
5. O SISTEMA DEVE permitir usar todas as telas pelo teclado, com o foco sempre visível.

---

## Requisitos de segurança

A feature não toca identidade, pagamento nem dado pessoal. Ela toca **entrada externa**: textos que vêm dos dados (descrição de jogada, nomes) passam a ser exibidos em mais lugares (notícias, busca), e no futuro virão de APIs de terceiros.

1. SE um texto vindo dos dados contiver marcação HTML ou script, ENTÃO O SISTEMA DEVE exibi-lo como texto literal, sem executá-lo.
2. SE o termo de busca exceder 100 caracteres, ENTÃO O SISTEMA DEVE considerar só os 100 primeiros.

---

## Perguntas em aberto

- [x] **Q1. Nome da página nova:** **"Jogo"**.
- [x] **Q2. Como juntar Treinador e Comentarista:** **abas** (Prancheta · Jogadas · Replay · Estatísticas · Playbook). Aplicado no Requisito 5.
- [x] **Q3. Fatos que viram notícia:** aprovada a proposta (resultado, virada, prorrogação, maior jogada, mais rápido, pocket mais longo, sacks, interceptações), ordenados pelo quanto fogem da média da liga, com as 4 primeiras no carrossel. Aplicado no Requisito 7.
- [x] **Q4. Animação contínua da prancheta:** **entra**. Virou o Requisito 10.
- [x] **Q6 (v0.4). Notícias sem o tracking:** **fatos gerados dos dados do nflverse**, com os tipos do Requisito 7 (a matéria da ESPN fica na página Jogo). Os limiares foram medidos nos dados (design, componente 2).
- [x] **Q7 (v0.4). Prancheta com movimento:** **sai** (o antigo Requisito 10): sem tracking, não há trajetória.
- [x] **Q8 (v0.4). Configurações:** **enxutas**: avanço automático das notícias e velocidade do Replay narrado.
- [x] **Q9 (v0.4). Matéria da ESPN:** **no topo da página Jogo**, abaixo do placar.
- [x] **Q5. Configurações:** **entra no menu lateral**. O conteúdo do Requisito 11 (animação suave, avanço automático das notícias, velocidade padrão) é **proposta do Claude a partir do que o app já tem**, e precisa ser confirmado na aprovação.

---

## Aprovação

- [x] Cada critério tem exatamente um DEVE
- [x] Cada critério nomeia um teste possível
- [x] Todo requisito tem pelo menos um SE...ENTÃO (exceto o 9, que é só remoção)
- [x] Nenhuma tecnologia mencionada neste arquivo
- [x] Seção de fora de escopo preenchida
- [x] Perguntas em aberto respondidas (conteúdo de Configurações confirmado)

**Aprovado por:** José Cota em 2026-09-25 (v0.3) e em 2026-09-26 (v0.4).
