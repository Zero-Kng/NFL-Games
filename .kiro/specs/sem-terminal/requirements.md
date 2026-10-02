# Requirements Document

**Feature:** sem-terminal
**Status:** em revisão
**Data:** 2026-10-01
**Autores:** José Cota (com Claude)

---

## Introduction

Hoje o `NFL-Games.exe` abre uma janela preta de terminal ao lado do navegador. Ela mostra o progresso e os erros, e fechá-la (ou apertar Ctrl+C) é o único jeito de parar o app. Para quem só quer usar o app, a janela parece um erro, fica no caminho e é fácil de fechar sem querer. Também, entre o duplo clique e o navegador abrir, passam de 4 a 7 s sem nenhum sinal na tela, enquanto o executável se descompacta.

Esta feature faz o `.exe` do Windows abrir **sem terminal**, com a **logo na hora** do duplo clique, e dá ao app dois jeitos de terminar: **"Encerrar o app" no menu** e **encerrar sozinho** depois que a última aba dele fecha. Abrir o `.exe` de novo **reaproveita a cópia que já está rodando**, em vez de subir outra.

Restrições de contexto:

- **Só o `NFL-Games.exe` do Windows perde o terminal.** O `rodar.py` a partir do código e o executável de Linux continuam com terminal e com o comportamento de hoje: quem os usa já está num terminal.
- **O site público (spec `site-publico`) não muda.** No celular não há servidor para encerrar.
- **O visual não muda**, exceto o item novo do menu, a confirmação e a tela final de "encerrado".
- **O servidor só escuta na própria máquina por padrão**, mas qualquer página aberta no navegador consegue mandar pedidos para `127.0.0.1`. Uma rota que encerra o app não pode ficar ao alcance de sites de fora.
- **O app continua funcionando sem internet** com a cópia local, como hoje.

---

## Fora de escopo

- **Ícone na bandeja do Windows** (perto do relógio).
- **O app numa janela própria, sem navegador.** Fica para a spec do visual próprio do PC.
- **Executável de Linux sem terminal, e macOS.**
- **Assinar o executável.** É outra ideia da lista e depende de comprar um certificado.
- **Mudar o que o servidor faz durante a carga dos dados.** A tela de carregamento continua igual.

---

## Requirements

### Requisito 1: Abrir sem terminal, com a logo na hora

**História de usuário:** Como usuário do PC, quero dar dois cliques no app e ver a logo na hora, sem nenhuma janela preta, para saber que ele está abrindo e não ter nada no caminho.

**Critérios de aceitação:**

1. QUANDO o usuário abrir o `NFL-Games.exe`, O SISTEMA DEVE abrir sem nenhuma janela de terminal.
2. QUANDO o usuário abrir o `NFL-Games.exe`, O SISTEMA DEVE mostrar a logo do app antes de o executável terminar de se descompactar.
3. QUANDO o navegador abrir o app, O SISTEMA DEVE fechar a logo.
4. O SISTEMA DEVE manter o `rodar.py` (a partir do código) e o executável de Linux com terminal e com o comportamento atual.

### Requisito 2: Uma cópia só

**História de usuário:** Como usuário, quero que abrir o app de novo me leve ao app que já está aberto, para não acumular cópias escondidas.

**Critérios de aceitação:**

1. QUANDO o usuário abrir o `NFL-Games.exe` com uma cópia do app já rodando nesta máquina, O SISTEMA DEVE abrir o navegador nessa cópia e não subir outra.
2. SE a porta padrão estiver ocupada por outro programa, ENTÃO O SISTEMA DEVE subir o app na próxima porta livre, como hoje.
3. O SISTEMA DEVE identificar uma cópia do app pela resposta do próprio app, e não só pela porta ocupada.

### Requisito 3: Mensagens sem terminal

**História de usuário:** Como usuário, quero ver os erros que impedem o app de abrir, mesmo sem terminal, para saber o que fazer.

**Critérios de aceitação:**

1. ENQUANTO o `NFL-Games.exe` estiver rodando, O SISTEMA DEVE gravar num arquivo de log, ao lado dos dados, o que hoje sai no terminal.
2. QUANDO o `NFL-Games.exe` abrir, O SISTEMA DEVE recomeçar o arquivo de log, para ele não crescer sem fim.
3. SE um erro impedir o app de abrir antes de o navegador abrir, ENTÃO O SISTEMA DEVE mostrar uma janela de aviso do Windows com a mensagem e o caminho do log.
4. SE a carga dos dados falhar com o navegador já aberto, ENTÃO O SISTEMA DEVE mostrar o erro na tela de carregamento, como hoje.
5. SE o arquivo de log não puder ser gravado, ENTÃO O SISTEMA DEVE abrir o app mesmo assim.

### Requisito 4: Encerrar pelo menu

**História de usuário:** Como usuário do PC, quero encerrar o app pelo menu, para fechar de verdade sem procurar janela nenhuma.

**Critérios de aceitação:**

1. O SISTEMA DEVE oferecer "Encerrar o app" no menu lateral do app do PC.
2. O SISTEMA DEVE ocultar "Encerrar o app" no site público.
3. QUANDO o usuário escolher "Encerrar o app", O SISTEMA DEVE pedir confirmação antes de encerrar.
4. QUANDO o usuário confirmar, O SISTEMA DEVE encerrar o processo do app e mostrar na página "O NFL Games foi encerrado. Pode fechar esta aba."
5. SE o app já tiver parado quando o usuário confirmar, ENTÃO O SISTEMA DEVE mostrar a mesma tela final.
6. SE o pedido de encerrar for recusado, ENTÃO O SISTEMA DEVE avisar "Não foi possível encerrar o app" e manter a página funcionando.

### Requisito 5: Encerrar sozinho

**História de usuário:** Como usuário, quero que o app se encerre sozinho quando eu fechar as abas dele, para não deixar um processo escondido rodando.

**Critérios de aceitação:**

1. ENQUANTO uma aba do app estiver aberta, inclusive na tela de carregamento, O SISTEMA DEVE dar sinal de presença ao servidor a cada 30 s.
2. QUANDO uma aba do app for fechada, O SISTEMA DEVE avisar o servidor da saída.
3. SE o app aberto pelo `NFL-Games.exe` ficar 3 minutos sem sinal de nenhuma aba, ENTÃO O SISTEMA DEVE se encerrar.
4. SE a última aba avisar a saída e nenhuma aba der sinal em 15 s, ENTÃO O SISTEMA DEVE se encerrar.
5. ENQUANTO nenhuma aba tiver dado sinal desde a abertura, O SISTEMA DEVE continuar rodando (primeira carga, navegador que não abriu).
6. SE o relógio der um salto (o PC dormiu), ENTÃO O SISTEMA DEVE recomeçar a contagem em vez de se encerrar.
7. O SISTEMA DEVE manter o servidor rodado pelo `rodar.py` (a partir do código) sem encerrar sozinho.
8. QUANDO o app se encerrar sozinho, O SISTEMA DEVE registrar o motivo no log.

---

## Requisitos não funcionais

1. O SISTEMA DEVE mostrar a logo em até 1 s depois do duplo clique no `NFL-Games.exe`.
2. O SISTEMA DEVE terminar o processo em até 5 s depois de o usuário confirmar "Encerrar o app".
3. O SISTEMA DEVE manter o tempo até o app ficar pronto igual ao de hoje (~7 s com a cópia local), com tolerância de 1 s.
4. O SISTEMA DEVE manter o `NFL-Games.exe` sem bibliotecas novas além das que o empacotamento já usa.

---

## Requisitos de segurança

A feature cria rotas que **mudam o estado do servidor** (encerrá-lo e registrar presença) num servidor sem autenticação, que qualquer página aberta no navegador consegue chamar.

1. SE um pedido para encerrar ou para dar presença não vier da própria máquina, ENTÃO O SISTEMA DEVE recusá-lo, mesmo com o servidor aberto para a rede (`--host 0.0.0.0`).
2. SE um pedido para encerrar ou para dar presença não trouxer o cabeçalho próprio do app, ENTÃO O SISTEMA DEVE recusá-lo.
3. SE um pedido para encerrar ou para dar presença trouxer uma origem diferente do endereço do próprio app, ENTÃO O SISTEMA DEVE recusá-lo.
4. O SISTEMA DEVE deixar de autorizar chamadas de outras origens (CORS) às rotas que mudam o estado.
5. O SISTEMA DEVE gravar no log só o que hoje sai no terminal, sem dados pessoais.

---

## Perguntas em aberto

- [x] **Q1. Como o app termina sem terminal?** Resposta: **"Encerrar o app" no menu e encerrar sozinho** depois que a última aba fecha; abrir o `.exe` de novo reaproveita a cópia aberta.
- [x] **Q2. Abordagem?** Resposta: **A**: executável sem console, com a tela de abertura nativa do PyInstaller, rota protegida para encerrar e batimento da página.
- [x] **Q3. Onde vão os erros?** Resposta (suposição aceita): janela de aviso do Windows e arquivo de log ao lado dos dados.

---

## Aprovação

- [x] Cada critério tem exatamente um DEVE
- [x] Cada critério nomeia um teste possível
- [x] Todo requisito tem pelo menos um SE...ENTÃO (exceto o 1, que é só comportamento de abertura)
- [x] Seção de fora de escopo preenchida
- [x] Perguntas em aberto respondidas
- [ ] Revisado e aprovado pelo José
