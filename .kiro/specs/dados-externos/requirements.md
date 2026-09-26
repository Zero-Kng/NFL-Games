# Requirements Document

**Feature:** dados-externos
**Status:** aprovado
**Data:** 2026-09-25 (v0.2: perguntas Q1–Q5 respondidas)
**Autores:** José Cota (com Claude)

---

## Introduction

O NFL Games nasceu sobre um único arquivo: o dataset do NFL Big Data Bowl 2023, que cobre só as semanas 1 a 8 da temporada 2021 e só jogadas de passe. Isso limita o app a um recorte de 122 jogos antigos, com placar aproximado (o placar do dataset é o do último dropback, e o TB × DAL aparece 28–29, quando o oficial foi 31–29). A meta do time é uma **repaginação total**: novo visual (spec `novo-visual`, pausada) e **todos os dados vindo de APIs**.

Esta feature troca a origem dos dados. O app passa a cobrir a **temporada atual (2026) e as cinco anteriores (2021–2025), incluindo os playoffs**, com placar oficial (**ao vivo** durante os jogos), todas as jogadas (inclusive corridas), estatísticas, notícias e avaliações de jogadores calculadas a partir de dados públicos. **O dataset do Big Data Bowl deixa de ser usado.** Isso tem dois efeitos:

- **A prancheta animada acaba.** A posição de cada jogador quadro a quadro não existe em nenhuma fonte pública. Ela vira uma **prancheta sem movimento**, montada com a formação e os jogadores de cada jogada (ver Q1).
- **Os ratings mudam de base.** As avaliações da PFF (pagas) dão lugar a estatísticas públicas. Os números 40–99 continuam existindo, mas com outra fórmula.

Fontes testadas em 2026-09-25 (detalhes no design):
- **nflverse:** licença CC-BY-4.0, atualizado diariamente. Tem calendário e placar oficial, play-by-play de todas as jogadas, jogadores em campo por jogada, formação, estatísticas por jogador e estatísticas avançadas.
- **API pública da ESPN:** matéria de cada jogo e placar ao vivo. Só responde a chamadas feitas pelo navegador.

Restrições de contexto:

- **Esta spec não faz o visual novo.** As telas atuais continuam, adaptadas o mínimo para funcionar com os dados novos; o visual vem na `novo-visual`, que é retomada depois.
- **Nenhum número inventado.** Todo valor exibido vem de uma fonte identificada. Quando a fonte não tem um dado, o app diz que não tem.
- **As metas de desempenho da spec `otimizacao-desempenho` continuam valendo** para uma banca de 10 pessoas.
- **O app continua subindo com o `RODAR.bat`** e continua funcionando sem internet com a última cópia dos dados que baixou.
- **A licença CC-BY-4.0 exige citar o nflverse** em algum lugar visível do app.

---

## Fora de escopo

- **O visual novo, a tela Notícias, a busca geral e as Configurações:** spec `novo-visual`.
- **Temporadas anteriores a 2021.**
- **Jogada a jogada ao vivo.** Durante o jogo, só o placar e o relógio são ao vivo (Requisito 10). As jogadas, estatísticas e formação entram na atualização diária.
- **Fontes pagas** (PFF, SportsDataIO, Sportradar).
- **Guardar o texto completo das matérias da ESPN.** Só título, resumo e link, por direito autoral.
- **Contas de usuário e notificações.**

---

## Requirements

### Requisito 1: Temporadas e semanas a partir das fontes externas

**História de usuário:** Como usuário, quero ver os jogos da temporada atual e das anteriores, para que o app sirva para acompanhar a NFL de hoje, e não só um recorte de 2021.

**Critérios de aceitação:**

1. O SISTEMA DEVE oferecer as temporadas de 2021 a 2026, com temporada regular e playoffs.
2. O SISTEMA DEVE oferecer, em cada temporada, todas as semanas da temporada regular e as rodadas dos playoffs (Wild Card, Divisional, Final de Conferência e Super Bowl), com os nomes das rodadas.
3. QUANDO o usuário escolher uma semana, O SISTEMA DEVE listar todos os jogos daquela semana com data, horário e times.
4. ENQUANTO um jogo não tiver começado, O SISTEMA DEVE exibi-lo como "a jogar", com data e horário.
5. SE a fonte ainda não tiver os dados de um jogo já disputado, ENTÃO O SISTEMA DEVE exibi-lo como "resultado ainda não disponível", sem placar.

### Requisito 2: Placar oficial

**História de usuário:** Como torcedor, quero ver o placar final oficial, para que o app nunca mostre um vencedor errado.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir o placar final oficial de cada jogo disputado.
2. O SISTEMA DEVE indicar quando um jogo foi decidido na prorrogação.
3. QUANDO o usuário abrir o replay de um jogo, O SISTEMA DEVE exibir, a cada jogada, o placar oficial daquele momento, incluindo os pontos de corridas e chutes.
4. SE a matéria do jogo e a base de jogadas divergirem no placar final, ENTÃO O SISTEMA DEVE exibir o placar da base de jogadas e registrar a divergência no log do servidor.

### Requisito 3: Jogadas completas

**História de usuário:** Como alguém analisando uma partida, quero ver todas as jogadas, e não só os passes, para que o replay e as estatísticas contem o jogo inteiro.

**Critérios de aceitação:**

1. O SISTEMA DEVE listar todas as jogadas de cada jogo disputado: passes, corridas, chutes e retornos, em ordem cronológica.
2. O SISTEMA DEVE exibir em cada jogada a situação (descida, distância, linha de jarda), o resultado em jardas e a descrição oficial.
3. O SISTEMA DEVE deixar de exibir os avisos "o dataset só tem jogadas de passe" e "o placar é aproximado".
4. SE uma jogada não tiver dados de formação ou de jogadores em campo, ENTÃO O SISTEMA DEVE exibi-la na lista com a indicação "sem dados de formação".

### Requisito 4: Prancheta sem movimento

**História de usuário:** Como treinador, quero ver quem estava em campo e em que formação em cada jogada, para que eu estude as escolhas táticas mesmo sem o tracking.

**Critérios de aceitação:**

1. QUANDO o usuário abrir uma jogada na prancheta, O SISTEMA DEVE desenhar os jogadores de ataque e de defesa daquela jogada, com número e posição.
2. O SISTEMA DEVE exibir junto da prancheta a formação, o pessoal em campo, o número de defensores no box e o número de jogadores que fizeram rush.
3. O SISTEMA DEVE indicar de forma visível que as posições no desenho são ilustrativas, e não o alinhamento real da jogada.
6. O SISTEMA DEVE usar a prancheta sem movimento em todas as temporadas, inclusive nos jogos de 2021 que tinham tracking no dataset antigo.
4. SE a fonte tiver a formação da jogada, mas não a lista de jogadores, ENTÃO O SISTEMA DEVE desenhar a formação com as posições genéricas, sem nomes.
5. SE a fonte não tiver nenhum dado de formação da jogada, ENTÃO O SISTEMA DEVE exibir a mensagem "formação indisponível para esta jogada" no lugar da prancheta.

### Requisito 5: Estatísticas e avaliação dos jogadores

**História de usuário:** Como olheiro, quero avaliar e comparar jogadores de qualquer temporada, para que a avaliação não fique presa a 2021.

**Critérios de aceitação:**

1. O SISTEMA DEVE calcular para cada jogador, por temporada, um rating de 40 a 99 a partir de estatísticas públicas, comparando-o apenas com jogadores do mesmo grupo de posição: QB, RB, WR/TE, linha ofensiva, linha defensiva, linebacker e secundária.
7. O SISTEMA DEVE indicar, no rating da linha ofensiva, que ele se baseia em menos estatísticas que os demais grupos.
2. O SISTEMA DEVE exibir no perfil do jogador o radar de atributos da função, com o percentil de cada eixo e o valor bruto correspondente.
3. O SISTEMA DEVE exibir no perfil do jogador as estatísticas da temporada e o jogo a jogo.
4. SE o jogador não atingir o volume mínimo de jogadas da função na temporada, ENTÃO O SISTEMA DEVE exibir o rating como "n/d", sem calcular.
5. SE uma estatística usada num eixo do radar não existir para a temporada escolhida, ENTÃO O SISTEMA DEVE omitir o eixo e indicar por quê.
6. QUANDO o usuário comparar dois jogadores, O SISTEMA DEVE comparar apenas jogadores da mesma função e da mesma temporada.

### Requisito 6: Matéria do jogo

**História de usuário:** Como torcedor, quero ler a manchete e o resumo de cada partida, para que eu entenda o jogo sem abrir outro site.

**Critérios de aceitação:**

1. QUANDO o usuário abrir um jogo disputado, O SISTEMA DEVE exibir o título, o resumo e a data da matéria desse jogo, com link para a matéria completa na fonte.
2. O SISTEMA DEVE exibir a fonte da matéria junto do título.
3. SE a matéria não puder ser obtida, ENTÃO O SISTEMA DEVE ocultar o bloco da matéria e manter o restante da página do jogo.

### Requisito 7: Atualização dos dados

**História de usuário:** Como usuário acompanhando a temporada atual, quero ver os resultados da última rodada, para que o app esteja sempre em dia.

**Critérios de aceitação:**

1. QUANDO o servidor for iniciado, O SISTEMA DEVE buscar nas fontes os dados novos desde a última atualização, baixando apenas o que mudou.
2. ENQUANTO o servidor estiver de pé, O SISTEMA DEVE verificar uma vez por dia se há dados novos da temporada atual (jogadas, estatísticas, formação).
3. QUANDO dados novos forem incorporados, O SISTEMA DEVE passar a responder com eles sem precisar ser reiniciado.
4. O SISTEMA DEVE exibir, em "Sobre os dados", a data e a hora da última atualização bem-sucedida.
5. SE a fonte estiver fora do ar ou sem internet, ENTÃO O SISTEMA DEVE continuar funcionando com a última cópia baixada e registrar a falha no log.
6. SE o servidor for iniciado pela primeira vez sem internet e sem nenhuma cópia local, ENTÃO O SISTEMA DEVE exibir uma mensagem clara no terminal e não subir com dados vazios.

### Requisito 10: Placar ao vivo

**História de usuário:** Como torcedor, quero acompanhar o placar de um jogo em andamento, para que eu não precise sair do app durante a rodada.

**Critérios de aceitação:**

1. ENQUANTO um jogo estiver em andamento, O SISTEMA DEVE exibir o placar, o quarto e o relógio atuais, com a marca "AO VIVO".
2. ENQUANTO houver jogo em andamento na semana exibida, O SISTEMA DEVE atualizar o placar ao vivo a cada 30 segundos, sem o usuário recarregar a página.
3. QUANDO um jogo terminar, O SISTEMA DEVE exibir o placar final e deixar de atualizá-lo.
4. ENQUANTO nenhum jogo da semana exibida estiver em andamento, O SISTEMA DEVE deixar de consultar o placar ao vivo.
5. SE o placar ao vivo não puder ser obtido, ENTÃO O SISTEMA DEVE exibir o último placar conhecido com a indicação "atualização ao vivo indisponível" e tentar de novo na próxima rodada de 30 segundos.
6. SE o placar ao vivo e o placar da atualização diária divergirem num jogo encerrado, ENTÃO O SISTEMA DEVE exibir o da atualização diária.

### Requisito 8: Transição das telas atuais

**História de usuário:** Como equipe, queremos que o app continue utilizável entre esta spec e a do visual novo, para que ele possa ser mostrado a qualquer momento.

**Critérios de aceitação:**

1. O SISTEMA DEVE manter funcionando as quatro telas atuais (Jogos, Treinador, Olheiro, Comentarista) com os dados novos.
2. O SISTEMA DEVE permitir escolher a temporada nas telas atuais.
3. SE uma tela atual depender de um dado que deixou de existir (como a velocidade de pico do tracking), ENTÃO O SISTEMA DEVE ocultar aquele campo, em vez de exibir um valor vazio ou zero.

### Requisito 9: Atribuição das fontes

**História de usuário:** Como equipe, queremos respeitar as licenças dos dados, para que o app possa ser publicado sem problema legal.

**Critérios de aceitação:**

1. O SISTEMA DEVE exibir, em "Sobre os dados", as fontes usadas, com o crédito exigido pela licença de cada uma.
2. O SISTEMA DEVE exibir, junto de cada matéria, o nome da fonte e o link para o original.

---

## Requisitos não funcionais

1. O SISTEMA DEVE manter as metas da spec `otimizacao-desempenho`: tela inicial em até 200 ms, abrir uma jogada em até 60 ms no servidor e p95 de até 300 ms com 10 usuários com pausa entre cliques, medidos com a semana mais recente disputada.
2. O SISTEMA DEVE subir em até 10 s quando já existir cópia local atualizada dos dados.
3. O SISTEMA DEVE fazer a primeira carga completa (6 temporadas) em até 5 minutos numa conexão doméstica, mostrando o progresso no terminal.
4. O SISTEMA DEVE ocupar no máximo 1 GB de disco com os dados locais.
5. O SISTEMA DEVE manter o uso de memória do servidor em no máximo 1 GB com as 6 temporadas carregadas.

---

## Requisitos de segurança

A feature toca **entrada externa**: os dados passam a vir de fontes de terceiros pela internet.

1. SE um texto vindo de uma fonte externa contiver marcação HTML ou script, ENTÃO O SISTEMA DEVE exibi-lo como texto literal.
2. SE um arquivo baixado não tiver o formato esperado (colunas faltando, tipos errados), ENTÃO O SISTEMA DEVE rejeitá-lo, manter a cópia anterior e registrar o erro.
3. O SISTEMA DEVE buscar dados somente nos endereços das fontes configuradas, e nunca em endereços vindos dos próprios dados.
4. SE um link externo (matéria) não for de um domínio da fonte configurada, ENTÃO O SISTEMA DEVE deixar de exibi-lo.

---

## Perguntas em aberto

- [x] **Q1. Prancheta sem movimento:** o **esquema ilustrativo** foi aceito: jogadores reais em posições-modelo da formação, com o aviso (critério 4.3). Em 2026, só a formação até a fonte publicar os jogadores por jogada (critério 4.4).
- [x] **Q2. Atualização:** **placar ao vivo** durante os jogos (virou o Requisito 10) e o restante uma vez por dia (critério 7.2).
- [x] **Q3. Jogos de 2021 com tracking real:** **confirmado**, a prancheta animada some também neles (critério 4.6).
- [x] **Q4. Playoffs:** **entram agora** (critérios 1.1 e 1.2).
- [x] **Q5. Ratings:** **por grupo de posição, com a linha ofensiva mantida**, e um aviso de que o rating dela usa menos estatísticas (critérios 5.1 e 5.7).

---

## Aprovação

- [x] Cada critério tem exatamente um DEVE
- [x] Cada critério nomeia um teste possível
- [x] Todo requisito tem pelo menos um SE...ENTÃO
- [x] Nenhuma tecnologia mencionada neste arquivo (fontes citadas por nome, porque são o contrato externo)
- [x] Seção de fora de escopo preenchida
- [x] Perguntas em aberto respondidas

**Aprovado por:** José Cota em 2026-09-25
