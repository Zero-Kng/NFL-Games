# Validação dos ratings (tarefa 4.4)

**Spec:** dados-externos · **Data:** 2026-09-25 · **Status:** ✅ validado pelo José em 2026-09-25

Os 10 melhores de cada grupo em **2025** e **2024**, com o valor bruto de cada eixo. `↓` = menor é melhor. O rating é `40 + média dos percentis × 0,59`, dentro do grupo e da temporada, só entre quem passou do volume mínimo. Na coluna **Pos**, a posição do depth chart do elenco (quando houver).

## Decisões do José (2026-09-25)

1. **Grupo Edge criado.** Edge = DE + OLB pass rusher; "Linha defensiva" fica com DT/NT; "Linebacker" com ILB/MLB. A posição vem do `depth_chart_position` do elenco (levada para o `jogador_jogo` como `posicao_elenco`, porque os brutos são descartados). "OLB" no elenco também cobre o SAM/WILL do 4-3, que joga em cobertura (Milano, Pratt, Baun, Owusu-Koramoah), então **um OLB só é Edge se teve mais pressões que alvos permitidos**. Os números separam bem os papéis (alvos por 100 snaps: mediana ~1,3 no edge × ~6 no LB de cobertura).
   - Casos de fronteira que caem em LB: híbridos que cobrem mais do que pressionam (Dennis Gardeck e Andrew Van Ginkel em 2025).
2. **QB com 6 eixos.** Os 5 de passe continuam, e entra **"Corrida" = EPA das corridas do QB por jogo**, um sinal independente que não conta o passe duas vezes. O radar do app já desenha qualquer número de eixos.
3. **Recebedor:** "Após a recepção" (YAC) virou **"Alvos por jogo"** (volume).
4. **Linha ofensiva:** confirmada como está (2 eixos do time, aviso "base reduzida").

**Efeito:** os top 10 de LB agora são LBs de fora da linha, e os pass rushers de 3-4 aparecem no Edge ao lado dos DE (Garrett, Parsons, Burns, Oweh). Allen e Hurts sobem entre os QBs. Puka Nacua, JSN e Pickens lideram os recebedores em 2025, e Ja'Marr Chase entra no top 10 de 2024.

> **Corrigido em rodadas anteriores:** (1) o eixo "Sacks" da linha defensiva saía vazio (colunas repetidas na junção); (2) o CPOE aparecia ×100 na exibição.

---

## Temporada 2025

Avaliados por grupo: Quarterback 33, Running back 52, Recebedor 108, Linha ofensiva 163, Edge 106, Linha defensiva 88, Linebacker 88, Secundária 191


### Quarterback · 2025

| # | Rating | Jogador | Pos | Time | EPA por dropback | Precisão (CPOE) | Jardas por tentativa | Cuidado com a bola ↓ | Sob pressão ↓ | Corrida |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **90** | Jordan Love | QB | GB | 0.25 | +5.4 pp | 7.64 | 1.2% | 4.3% | 0.80 |
| 2 | **82** | Brock Purdy | QB | SF | 0.16 | +5.6 pp | 7.51 | 3.8% | 3.9% | 1.54 |
| 3 | **82** | Daniel Jones | QB | IND | 0.16 | +2.3 pp | 8.08 | 2.1% | 5.4% | 1.24 |
| 4 | **81** | Drake Maye | QB | NE | 0.18 | +7.9 pp | 8.53 | 2.0% | 10.0% | 0.97 |
| 5 | **80** | Josh Allen | QB | BUF | 0.15 | +4.0 pp | 7.91 | 2.2% | 7.6% | 2.63 |
| 6 | **80** | Matthew Stafford | QB | LA | 0.23 | +0.7 pp | 7.88 | 1.3% | 3.9% | -1.59 |
| 7 | **78** | Dak Prescott | QB | DAL | 0.18 | +2.2 pp | 7.59 | 1.7% | 4.9% | -0.55 |
| 8 | **78** | Jalen Hurts | QB | PHI | 0.06 | +2.4 pp | 6.94 | 1.2% | 6.3% | 1.12 |
| 9 | **77** | Jared Goff | QB | DET | 0.17 | +1.9 pp | 7.90 | 1.4% | 6.2% | -0.85 |
| 10 | **75** | Joe Burrow | QB | CIN | 0.13 | +4.7 pp | 6.98 | 1.9% | 6.2% | 0.45 |

### Running back · 2025

| # | Rating | Jogador | Pos | Time | EPA por corrida | Após o contato | Tackles quebrados | Recepção | Segurança ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **94** | De'Von Achane | RB | MIA | 0.06 | 3.02 | 10.2% | 30.50 | 0.0% |
| 2 | **87** | Jonathan Taylor | RB | IND | 0.06 | 2.35 | 9.5% | 22.24 | 0.3% |
| 3 | **86** | Jaylen Warren | RB | PIT | -0.02 | 2.34 | 12.1% | 19.82 | 0.0% |
| 4 | **83** | Chris Rodriguez Jr. | RB | WAS | 0.06 | 2.97 | 11.3% | 2.31 | 0.0% |
| 5 | **82** | Kenneth Walker III | RB | SEA | -0.04 | 1.93 | 13.2% | 19.30 | 0.0% |
| 6 | **81** | Chase Brown | RB | CIN | -0.02 | 1.97 | 7.3% | 25.71 | 0.0% |
| 7 | **81** | Kenny Gainwell | RB | PIT | -0.02 | 2.04 | 9.6% | 28.44 | 0.5% |
| 8 | **78** | Bijan Robinson | RB | ATL | -0.04 | 2.32 | 8.7% | 48.24 | 0.8% |
| 9 | **77** | Omarion Hampton | RB | LAC | -0.01 | 1.52 | 9.6% | 19.20 | 0.0% |
| 10 | **75** | J.K. Dobbins | RB | DEN | 0.03 | 2.44 | 5.5% | 3.70 | 0.0% |

### Recebedor · 2025

| # | Rating | Jogador | Pos | Time | Jardas por alvo | EPA por alvo | Aproveitamento | Alvos por jogo | Mãos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **92** | Puka Nacua | WR | LA | 9.84 | 0.62 | 73.6% | 10.95 | 2.4% |
| 2 | **90** | George Kittle | TE | SF | 8.93 | 0.65 | 81.7% | 5.92 | 1.4% |
| 3 | **90** | Jaxon Smith-Njigba | WR | SEA | 10.54 | 0.51 | 72.0% | 9.45 | 2.6% |
| 4 | **89** | George Pickens | WR | DAL | 10.43 | 0.65 | 67.9% | 8.06 | 2.2% |
| 5 | **87** | Dalton Kincaid | TE | BUF | 11.37 | 0.83 | 80.0% | 4.29 | 1.7% |
| 6 | **87** | Jalen Coker | WR | CAR | 9.60 | 0.50 | 76.4% | 4.58 | 0.0% |
| 7 | **87** | Trey McBride | TE | ARI | 7.33 | 0.43 | 74.6% | 9.94 | 1.2% |
| 8 | **86** | Stefon Diggs | WR | NE | 9.20 | 0.58 | 81.1% | 5.81 | 3.3% |
| 9 | **83** | Mack Hollins | WR | NE | 9.05 | 0.48 | 69.3% | 4.41 | 0.0% |
| 10 | **83** | Terry McLaurin | WR | WAS | 9.70 | 0.53 | 63.3% | 6.00 | 1.7% |

### Linha ofensiva · 2025

| # | Rating | Jogador | Pos | Time | Volume | Disciplina ↓ | Proteção do time ↓ | Corrida do time |
|---|---|---|---|---|---|---|---|---|
| 1 | **94** | O'Cyrus Torrence | G | BUF | 1270 | 0.08 | 17.7% | 2.84 |
| 2 | **91** | David Edwards | G | BUF | 1176 | 0.17 | 18.9% | 2.87 |
| 3 | **89** | Coleman Shelton | C | LA | 1335 | 0.22 | 19.0% | 2.72 |
| 4 | **89** | Connor McGovern | C | BUF | 1166 | 0.26 | 18.8% | 2.86 |
| 5 | **86** | Alaric Jackson | T | LA | 1266 | 0.32 | 18.7% | 2.69 |
| 6 | **86** | Steve Avila | G | LA | 1051 | 0.10 | 19.1% | 2.73 |
| 7 | **85** | Joe Thuney | G | CHI | 1308 | 0.15 | 25.7% | 3.11 |
| 8 | **85** | Quinn Meinerz | G | DEN | 1238 | 0.08 | 21.1% | 2.56 |
| 9 | **85** | Terence Steele | T | DAL | 1162 | 0.26 | 20.3% | 2.68 |
| 10 | **85** | Warren McClendon Jr. | T | LA | 882 | 0.00 | 16.5% | 2.78 |

### Edge · 2025

| # | Rating | Jogador | Pos | Time | Pressão | Sacks | QB hits | Tackles para perda | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **97** | Myles Garrett | DE | CLE | 6.1% | 2.6% | 4.5% | 3.8% | 3.3% |
| 2 | **96** | Al-Quadin Muhammad | DE | DET | 5.5% | 2.4% | 4.4% | 2.0% | 0.0% |
| 3 | **94** | Josh Sweat | OLB | ARI | 5.2% | 2.2% | 3.1% | 2.4% | 0.0% |
| 4 | **94** | Odafe Oweh | OLB | LAC | 5.0% | 2.0% | 3.9% | 2.2% | 2.9% |
| 5 | **92** | Brian Burns | OLB | NYG | 4.8% | 1.9% | 3.6% | 2.6% | 5.6% |
| 6 | **91** | Jadeveon Clowney | DE | DAL | 5.4% | 2.3% | 2.7% | 3.2% | 6.5% |
| 7 | **91** | Will Anderson Jr. | DE | HOU | 5.3% | 2.0% | 3.5% | 2.8% | 7.3% |
| 8 | **90** | Micah Parsons | OLB | GB | 6.8% | 1.8% | 3.8% | 1.7% | 7.3% |
| 9 | **90** | Nik Bonitto | OLB | DEN | 5.3% | 2.0% | 3.8% | 2.0% | 7.5% |
| 10 | **89** | Tuli Tuipulotu | OLB | LAC | 4.1% | 1.8% | 3.0% | 2.7% | 5.7% |

### Linha defensiva · 2025

| # | Rating | Jogador | Pos | Time | Pressão | Sacks | QB hits | Tackles para perda | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **95** | Brandon Dorlus | DT | ATL | 3.0% | 1.8% | 2.4% | 2.4% | 5.0% |
| 2 | **95** | Chris Jones | DT | KC | 4.1% | 0.9% | 3.3% | 1.6% | 4.8% |
| 3 | **95** | DeForest Buckner | DT | IND | 4.3% | 0.9% | 2.8% | 1.9% | 5.0% |
| 4 | **93** | Jeffery Simmons | DT | TEN | 4.2% | 1.4% | 2.7% | 2.2% | 9.7% |
| 5 | **90** | Malcolm Roach | DT | DEN | 2.5% | 1.2% | 2.1% | 1.2% | 8.1% |
| 6 | **90** | Milton Williams | DT | NE | 3.1% | 1.1% | 2.1% | 2.0% | 11.1% |
| 7 | **89** | Byron Murphy II | DT | SEA | 2.7% | 1.0% | 1.7% | 1.0% | 4.5% |
| 8 | **89** | Calais Campbell | DT | ARI | 3.4% | 1.2% | 3.1% | 1.7% | 16.0% |
| 9 | **89** | Devonte Wyatt | DT | GB | 1.8% | 1.1% | 1.8% | 1.6% | 6.2% |
| 10 | **88** | Maliek Collins | DT | CLE | 3.2% | 1.4% | 2.7% | 1.5% | 13.8% |

### Linebacker · 2025

| # | Rating | Jogador | Pos | Time | Tackles | Tackles para perda | Pressão | Cobertura ↓ | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **87** | Trenton Simpson | ILB | BAL | 15.7% | 1.0% | 1.2% | 82.88 | 4.8% |
| 2 | **84** | Nakobe Dean | ILB | PHI | 13.2% | 1.5% | 1.9% | 81.75 | 7.8% |
| 3 | **83** | Carson Schwesinger | MLB | CLE | 15.4% | 1.2% | 0.9% | 88.34 | 6.1% |
| 4 | **83** | Dennis Gardeck | OLB | JAX | 11.2% | 1.3% | 2.7% | 90.92 | 2.0% |
| 5 | **83** | Jack Campbell | MLB | DET | 15.9% | 0.8% | 1.1% | 91.01 | 4.0% |
| 6 | **82** | Andrew Van Ginkel | OLB | MIN | 8.8% | 1.9% | 2.7% | 74.82 | 6.9% |
| 7 | **81** | Bobby Wagner | MLB | WAS | 14.0% | 0.7% | 1.0% | 81.77 | 4.1% |
| 8 | **80** | Devin Bush | MLB | CLE | 14.1% | 0.8% | 0.7% | 73.57 | 6.7% |
| 9 | **80** | Eric Wilson | ILB | MIN | 11.5% | 1.8% | 1.9% | 75.88 | 10.9% |
| 10 | **80** | Isaiah McDuffie | MLB | GB | 17.6% | 0.5% | 0.7% | 71.41 | 6.7% |

### Secundária · 2025

| # | Rating | Jogador | Pos | Time | Rating permitido ↓ | Passes completados ↓ | Jardas por alvo ↓ | Bolas na mão | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **95** | Julian Love | SS | SEA | 56.25 | 44.0% | 5.12 | 36.0% | 6.5% |
| 2 | **93** | Quinyon Mitchell | CB | PHI | 69.03 | 45.5% | 5.90 | 25.0% | 6.1% |
| 3 | **91** | Benjamin St-Juste | CB | LAC | 75.19 | 51.1% | 5.40 | 17.8% | 0.0% |
| 4 | **91** | Jamel Dean | CB | TB | 66.43 | 48.3% | 7.09 | 20.7% | 2.1% |
| 5 | **90** | Mike Jackson | CB | CAR | 72.28 | 52.8% | 6.75 | 25.9% | 6.6% |
| 6 | **90** | Rock Ya-Sin | CB | DET | 74.04 | 51.9% | 5.57 | 16.7% | 2.3% |
| 7 | **89** | Antonio Johnson | SS | JAX | 69.90 | 61.2% | 6.84 | 28.6% | 4.8% |
| 8 | **89** | Christian Gonzalez | CB | NE | 70.00 | 49.6% | 5.65 | 15.1% | 3.3% |
| 9 | **89** | Derek Stingley Jr. | CB | HOU | 65.69 | 41.7% | 6.21 | 26.4% | 9.3% |
| 10 | **89** | Joey Porter Jr. | CB | PIT | 58.27 | 47.9% | 4.93 | 23.9% | 10.0% |

---

## Temporada 2024

Avaliados por grupo: Quarterback 35, Running back 51, Recebedor 115, Linha ofensiva 164, Edge 107, Linha defensiva 82, Linebacker 83, Secundária 205


### Quarterback · 2024

| # | Rating | Jogador | Pos | Time | EPA por dropback | Precisão (CPOE) | Jardas por tentativa | Cuidado com a bola ↓ | Sob pressão ↓ | Corrida |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **93** | Lamar Jackson | QB | BAL | 0.34 | +5.0 pp | 8.85 | 1.0% | 4.8% | 0.86 |
| 2 | **91** | Josh Allen | QB | BUF | 0.26 | +2.0 pp | 7.73 | 1.1% | 3.3% | 3.08 |
| 3 | **84** | Jalen Hurts | QB | PHI | 0.13 | +7.6 pp | 8.03 | 1.3% | 10.1% | 2.67 |
| 4 | **83** | Joe Burrow | QB | CIN | 0.16 | +6.8 pp | 7.54 | 1.4% | 6.9% | 0.94 |
| 5 | **81** | Derek Carr | QB | NO | 0.17 | +3.2 pp | 7.69 | 1.8% | 2.8% | -0.11 |
| 6 | **80** | Jared Goff | QB | DET | 0.27 | +4.8 pp | 8.54 | 2.6% | 5.4% | -0.08 |
| 7 | **80** | Jayden Daniels | QB | WAS | 0.14 | +3.3 pp | 7.39 | 1.7% | 7.9% | 3.12 |
| 8 | **80** | Tua Tagovailoa | QB | MIA | 0.20 | +3.8 pp | 7.19 | 1.8% | 5.0% | 0.04 |
| 9 | **79** | Brock Purdy | QB | SF | 0.16 | +2.1 pp | 8.49 | 2.6% | 6.4% | 1.28 |
| 10 | **77** | Baker Mayfield | QB | TB | 0.20 | +4.2 pp | 7.97 | 2.7% | 6.5% | -0.04 |

### Running back · 2024

| # | Rating | Jogador | Pos | Time | EPA por corrida | Após o contato | Tackles quebrados | Recepção | Segurança ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **87** | Bijan Robinson | RB | ATL | 0.06 | 2.39 | 7.7% | 25.35 | 0.0% |
| 2 | **87** | Jahmyr Gibbs | RB | DET | 0.15 | 2.34 | 7.8% | 32.61 | 0.3% |
| 3 | **86** | James Conner | RB | ARI | 0.01 | 2.39 | 12.7% | 25.88 | 0.4% |
| 4 | **85** | Derrick Henry | RB | BAL | 0.13 | 2.87 | 13.2% | 10.16 | 0.3% |
| 5 | **83** | Bucky Irving | RB | TB | 0.09 | 2.66 | 7.0% | 22.11 | 0.4% |
| 6 | **83** | David Montgomery | RB | DET | -0.05 | 2.31 | 13.6% | 22.73 | 0.4% |
| 7 | **83** | J.K. Dobbins | RB | LAC | 0.01 | 2.48 | 11.0% | 10.93 | 0.0% |
| 8 | **83** | Tyjae Spears | RB | TEN | -0.06 | 2.19 | 14.9% | 18.67 | 0.0% |
| 9 | **81** | Jerome Ford | RB | CLE | 0.05 | 2.12 | 8.5% | 16.07 | 0.0% |
| 10 | **80** | Antonio Gibson | RB | NE | -0.09 | 2.69 | 10.5% | 12.12 | 0.0% |

### Recebedor · 2024

| # | Rating | Jogador | Pos | Time | Jardas por alvo | EPA por alvo | Aproveitamento | Alvos por jogo | Mãos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **92** | George Kittle | TE | SF | 11.77 | 0.72 | 83.0% | 6.27 | 2.1% |
| 2 | **91** | Amon-Ra St. Brown | WR | DET | 9.27 | 0.71 | 81.5% | 8.39 | 3.3% |
| 3 | **91** | Chris Godwin Jr. | WR | TB | 9.29 | 0.57 | 80.6% | 8.86 | 3.2% |
| 4 | **91** | DeVonta Smith | WR | PHI | 9.65 | 0.68 | 79.2% | 6.24 | 1.9% |
| 5 | **89** | Nico Collins | WR | HOU | 10.51 | 0.51 | 69.6% | 8.21 | 2.6% |
| 6 | **88** | Adam Thielen | WR | CAR | 9.92 | 0.65 | 77.4% | 6.20 | 3.2% |
| 7 | **88** | Dallas Goedert | TE | PHI | 9.88 | 0.45 | 81.9% | 5.14 | 1.4% |
| 8 | **87** | A.J. Brown | WR | PHI | 10.35 | 0.62 | 65.8% | 7.06 | 1.7% |
| 9 | **87** | Khalil Shakir | WR | BUF | 8.29 | 0.44 | 78.3% | 6.67 | 0.8% |
| 10 | **85** | Ja'Marr Chase | WR | CIN | 9.76 | 0.44 | 72.6% | 10.29 | 5.1% |

### Linha ofensiva · 2024

| # | Rating | Jogador | Pos | Time | Volume | Disciplina ↓ | Proteção do time ↓ | Corrida do time |
|---|---|---|---|---|---|---|---|---|
| 1 | **92** | Cody Mauch | G | TB | 1181 | 0.17 | 17.2% | 2.74 |
| 2 | **90** | Evan Brown | C | ARI | 1070 | 0.19 | 15.7% | 3.14 |
| 3 | **89** | Tyler Biadasz | C | WAS | 1172 | 0.26 | 19.1% | 2.75 |
| 4 | **87** | Connor McGovern | C | BUF | 1166 | 0.17 | 17.9% | 2.50 |
| 5 | **87** | Daniel Faalele | T | BAL | 1240 | 0.40 | 20.7% | 3.24 |
| 6 | **86** | Nick Allegretti | G | WAS | 1378 | 0.44 | 20.4% | 2.82 |
| 7 | **85** | Cam Jurgens | G | PHI | 1285 | 0.31 | 23.4% | 3.30 |
| 8 | **85** | David Edwards | G | BUF | 1182 | 0.34 | 17.8% | 2.48 |
| 9 | **84** | Tyler Linderbaum | C | BAL | 1227 | 0.57 | 20.7% | 3.25 |
| 10 | **83** | Alex Cappa | G | CIN | 1133 | 0.09 | 22.1% | 2.62 |

### Edge · 2024

| # | Rating | Jogador | Pos | Time | Pressão | Sacks | QB hits | Tackles para perda | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **95** | Myles Garrett | DE | CLE | 5.3% | 1.7% | 3.4% | 2.7% | 6.0% |
| 2 | **93** | Will Anderson Jr. | DE | HOU | 5.4% | 2.2% | 3.7% | 3.1% | 8.7% |
| 3 | **92** | Trey Hendrickson | DE | CIN | 6.5% | 2.1% | 4.4% | 2.3% | 9.5% |
| 4 | **91** | Danielle Hunter | DE | HOU | 4.5% | 1.4% | 3.0% | 2.0% | 7.0% |
| 5 | **90** | Odafe Oweh | OLB | BAL | 4.5% | 1.6% | 3.8% | 1.5% | 7.0% |
| 6 | **89** | Nik Bonitto | OLB | DEN | 4.9% | 1.8% | 3.3% | 2.1% | 10.3% |
| 7 | **88** | George Karlaftis | DE | KC | 4.6% | 1.2% | 3.6% | 1.3% | 2.0% |
| 8 | **88** | Micah Parsons | DE | DAL | 6.5% | 1.7% | 3.3% | 1.7% | 12.2% |
| 9 | **87** | Kyle Van Noy | OLB | BAL | 3.9% | 1.9% | 3.3% | 2.0% | 10.6% |
| 10 | **86** | Rashan Gary | DE | GB | 4.0% | 1.3% | 2.4% | 1.5% | 4.7% |

### Linha defensiva · 2024

| # | Rating | Jogador | Pos | Time | Pressão | Sacks | QB hits | Tackles para perda | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **95** | Leonard Williams | DT | SEA | 3.7% | 1.5% | 3.7% | 2.1% | 7.4% |
| 2 | **94** | Dexter Lawrence | NT | NYG | 3.3% | 1.6% | 2.9% | 1.4% | 5.0% |
| 3 | **91** | Cameron Heyward | DT | PIT | 2.9% | 1.0% | 2.4% | 1.7% | 6.6% |
| 4 | **90** | Chris Jones | DT | KC | 4.7% | 0.6% | 2.7% | 1.1% | 4.5% |
| 5 | **90** | Kobie Turner | NT | LA | 2.6% | 1.2% | 1.7% | 1.5% | 4.6% |
| 6 | **90** | Nnamdi Madubuike | DT | BAL | 2.7% | 1.0% | 2.1% | 1.3% | 2.2% |
| 7 | **88** | DeForest Buckner | DT | IND | 3.3% | 1.1% | 2.4% | 1.4% | 12.5% |
| 8 | **87** | Vita Vea | NT | TB | 2.5% | 0.9% | 1.9% | 1.3% | 5.1% |
| 9 | **86** | Braden Fiske | DT | LA | 3.1% | 1.4% | 1.7% | 1.6% | 13.5% |
| 10 | **86** | Devonte Wyatt | DT | GB | 3.3% | 1.4% | 2.5% | 2.5% | 22.7% |

### Linebacker · 2024

| # | Rating | Jogador | Pos | Time | Tackles | Tackles para perda | Pressão | Cobertura ↓ | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **89** | Devin Bush | ILB | CLE | 12.1% | 1.6% | 1.2% | 79.64 | 3.9% |
| 2 | **87** | Edgerrin Cooper | ILB | GB | 15.8% | 2.4% | 1.6% | 78.84 | 11.1% |
| 3 | **83** | Nakobe Dean | ILB | PHI | 14.3% | 1.2% | 0.7% | 81.25 | 8.2% |
| 4 | **83** | Zack Baun | OLB | PHI | 14.4% | 1.1% | 0.7% | 77.32 | 7.5% |
| 5 | **82** | Ivan Pace Jr. | ILB | MIN | 17.1% | 2.0% | 2.6% | 97.17 | 10.0% |
| 6 | **82** | Jordan Hicks | ILB | CLE | 11.4% | 0.7% | 1.5% | 79.34 | 2.5% |
| 7 | **82** | Kyzir White | ILB | ARI | 12.4% | 0.9% | 1.0% | 84.89 | 5.2% |
| 8 | **82** | Leo Chenal | OLB | KC | 12.6% | 1.0% | 1.0% | 89.56 | 4.7% |
| 9 | **81** | Kaden Elliss | ILB | ATL | 12.7% | 0.7% | 2.0% | 89.76 | 4.5% |
| 10 | **81** | Tyrice Knight | MLB | SEA | 14.7% | 0.5% | 0.7% | 81.70 | 4.7% |

### Secundária · 2024

| # | Rating | Jogador | Pos | Time | Rating permitido ↓ | Passes completados ↓ | Jardas por alvo ↓ | Bolas na mão | Tackles perdidos ↓ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **92** | Jaden Hicks | SS | KC | 66.75 | 57.1% | 6.95 | 38.1% | 0.0% |
| 2 | **91** | Malik Mustapha | FS | SF | 60.30 | 35.0% | 4.15 | 30.0% | 10.1% |
| 3 | **89** | Kerby Joseph | FS | DET | 53.80 | 45.7% | 8.13 | 45.7% | 6.5% |
| 4 | **89** | Marcus Maye | FS | MIA | 72.39 | 55.0% | 4.25 | 20.0% | 8.6% |
| 5 | **89** | Pat Surtain II | CB | DEN | 76.83 | 61.5% | 6.23 | 23.1% | 0.0% |
| 6 | **89** | Storm Duck | CB | MIA | 69.51 | 53.3% | 5.50 | 13.3% | 3.4% |
| 7 | **88** | Amani Hooker | FS | TEN | 74.16 | 52.5% | 6.92 | 35.0% | 8.1% |
| 8 | **88** | Cobie Durant | CB | LA | 70.32 | 52.8% | 5.98 | 22.6% | 9.3% |
| 9 | **88** | Isaiah Rodgers | CB | PHI | 78.63 | 47.5% | 5.88 | 17.5% | 6.5% |
| 10 | **88** | Quinyon Mitchell | CB | PHI | 74.78 | 53.7% | 5.54 | 18.9% | 7.7% |

