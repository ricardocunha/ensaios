---
title: "Cinco correções certas, nenhum impedimento marcado"
subtitle: "Um pipeline de impedimento no futebol diante de vídeo real: o detector, o modelo de bola e o filtro de movimento funcionaram, cada um na sua métrica, o sistema continuou mudo, e o último bloqueio era um erro de contagem na camada barata e determinística"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — números finais, cada um ligado à sua fonte no repositório sportsvision (SOURCES.md, repositório em 6d694fd)
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside
project: https://github.com/ricardocunha/sportsvision
---

# Cinco correções certas, nenhum impedimento marcado

O impedimento é uma das poucas decisões de arbitragem que são pura geometria. No momento em que a bola é jogada, ordene os defensores ao longo do campo, pegue o penúltimo e compare uma coordenada. Nessa parte não há nada para um modelo aprender.

Então construí o [SportsVision](https://github.com/ricardocunha/sportsvision). Você entrega um trecho de jogo e, para cada passe, ele deveria devolver uma decisão com a geometria que a sustenta: a linha de impedimento, a margem em metros, os quadros usados e uma confiança que dá para recalcular. Ele roda como um pipeline de verdade (filas, workers, autoscaling, traces) num laptop.

Durante quatro semanas, com vídeo real, ele não chegou a nenhum veredito. Na maior parte desse tempo não devolveu nada: nem impedimento, nem posição legal, nem um "não sei dizer".

Resumindo:

- **Decidir é barato e enxergar é caro.** No benchmark, a etapa de regras inteira levou 0,023 s e a percepção levou 100,2 s, no mesmo vídeo de 10 segundos.
- **Quatro correções antes das regras funcionaram, cada uma na sua métrica, e o pipeline implantado continuou sem emitir nada.** Um detector de jogadores com ajuste fino. Um modelo dedicado de bola, que levou a visibilidade da bola de 47% para 93%. Um filtro de movimento, que reduziu o pior salto da bola entre quadros de 12,14 m para 1,63 m. E a implantação dos modelos treinados, que tinham ficado no disco enquanto o cluster rodava o antigo.
- **A quinta correção foi na parte barata.** A posse de bola era estabelecida em 0 de 599 quadros, porque "3 quadros consecutivos" contava quadros brutos e o cluster só olha um quadro a cada dois. Depois da correção: 242 de 599, e os dois primeiros vereditos que o motor produziu. Os dois dizem posição legal.
- **Ainda não há número de acurácia, nem impedimento marcado.** Não tenho trechos rotulados, então não sei dizer se algum dos dois vereditos está certo. E a correção foi verificada rodando as regras de novo sobre os artefatos da última execução no cluster, não com uma nova execução completa no cluster.

Todos os números vêm da documentação, dos registros de decisão (ADRs) e das mensagens de commit do projeto; o [SOURCES.md](SOURCES.md) liga cada um a um arquivo ou a um commit.

## O que é o sistema

![Três fronteiras. A Percepção (Python, GPU ou CPU) transforma segmentos de vídeo em detecções, embeddings e pontos-chave do campo. O Estado (Python, CPU) transforma isso em tracks, times e coordenadas do campo em metros. A Decisão (Go, determinística) faz a detecção de passes, a linha de impedimento e o mapeamento de confiança para resultado, e grava eventos e evidências no PostgreSQL e no S3.](images/02-perception-state-decision.svg)

O projeto é essa divisão:

- A **Percepção** (Python) é a única camada que roda uma rede neural: um detector RF-DETR encontra jogadores, goleiros, árbitros e a bola, um segmento de vídeo por vez.
- O **Estado** (Python) vê o vídeo inteiro: tracks do ByteTrack, times por agrupamento de embeddings de aparência, a trajetória da bola e as posições em metros por meio de uma homografia.
- A **Decisão** (Go) é determinística. Ela encontra posse, chutes e passes, traça a linha e transforma uma confiança num resultado. Os testes dela não precisam de rede, de arquivos nem de Python.

Nenhuma camada responde a uma pergunta que pertence à seguinte. O detector nunca diz "impedimento"; o tracker nunca diz "passe".

Em volta disso há cinco serviços implantáveis (`sv api`, `sv segmenter`, `vision-worker`, `tracker`, `sv rules`), seis filas SQS com suas filas de mensagens mortas (dead-letter), PostgreSQL e um armazenamento de objetos, num cluster kind de três nós. O S3 e o SQS vêm do [Floci](https://github.com/floci-io/floci), um emulador que o provider AWS de verdade do Terraform consegue provisionar. O KEDA escala os quatro consumidores de fila a partir de zero, pela profundidade da fila. Go e Python não compartilham banco de dados; compartilham contratos em JSON Schema.

A pilha é local por um motivo prático: o projeto foi construído em grande parte por agentes de código trabalhando em worktrees git paralelas, e eu queria que eles pudessem implantar, quebrar e reconstruir tudo sem que existisse nenhuma credencial de nuvem real. Nada rodou na AWS, e o registro de decisão sobre compatibilidade com a AWS é o único ainda marcado como "Proposed".

Uma caixa do diagrama ainda não é real: o modelo de pontos-chave do campo não foi treinado (cerca de 5,4 horas por época neste laptop, contra um teto de 120 épocas). As coordenadas do campo vêm de um arquivo de calibração manual, e só um trecho tem esse arquivo.

## Decidir é barato, enxergar é caro

Benchmark de 16 de setembro de 2026, num Apple M4 Pro com inferência só em CPU no cluster, mediana de 5 execuções (mín–máx), todas com partida a frio a partir de zero réplicas:

| | |
|---|---|
| Ponta a ponta, um vídeo de 10 s | 134,6 s (132,6–140,8) |
| Seis vídeos de 8 s de uma vez, p50 / p95 | 195,2 s / 269,5 s |
| Vazão, seis vídeos em duas réplicas de visão | 80,2 vídeos/hora (78,4–82) |
| Detector, ONNX em CPU, uma réplica | 1,70 fps (1,67–1,71) |
| Médias por etapa, um vídeo: segmentar / perceber / rastrear / regras | 3,8 s / 100,2 s / 29,4 s / **0,023 s** |

A percepção custa mais de 4.000 vezes a decisão que ela alimenta.

Três ressalvas. Os 0,023 s são a etapa `rules` inteira, como o worker a observa, não um microbenchmark do motor, e vêm de execuções que produziram zero eventos, ou seja, a etapa não tinha evidência para renderizar nem evento para gravar. Essas medianas foram tiradas com o detector pré-treinado no COCO, de 640 px; o modelo com ajuste fino que o substituiu roda a 384 px, então a tabela não é comparável com as execuções posteriores. E "vídeos por hora" descreve um laptop.

A parte que não depende do laptop: nas cinco execuções em rajada, os 30 jobs terminaram, com 0 falhas, 0 mensagens mortas, 0 reinícios e 0 processos mortos por falta de memória.

## "Não sei dizer" é uma resposta, com nove motivos

![Resultados de uma checagem de impedimento. Todo passe confirmado vira um PASS ou um OFFSIDE_CHECK. A checagem é DETECTED quando margem e confiança passam dos dois limiares, REVIEW_REQUIRED quando a margem está dentro da faixa de revisão ou a confiança fica entre os dois limiares, e INCONCLUSIVE quando um dos gates dispara.](images/07-event-outcomes.svg)

Todo passe confirmado produz um evento com um de três status. `DETECTED`: um veredito que o motor sustenta. `REVIEW_REQUIRED`: um veredito que uma pessoa deveria confirmar, porque a margem é menor que 0,3 m ou a confiança está na faixa intermediária. `INCONCLUSIVE`: o motor se recusa a julgar, com um de nove motivos legíveis por máquina: `NO_HOMOGRAPHY`, `BALL_NOT_VISIBLE`, `RECEIVER_MISSING`, `DIRECTION_UNKNOWN`, `DEFENDER_MISSING`, `GOALKEEPER_MISSING`, `SET_PIECE`, `TEAM_UNASSIGNED`, `LOW_CONFIDENCE`.

Um evento `INCONCLUSIVE` é um resultado, não um erro. Ele diz o que a percepção deixou de entregar.

Esse desenho tem um buraco, e este artigo é sobre ele. Os três resultados só existem para um **passe confirmado**. Um chute sem passador, ou sem recebedor, é descartado dentro do motor por um simples `continue`. Não emite nada e não registra nada. Assim, uma execução pode terminar com zero eventos e zero motivos.

## Os vídeos

O projeto usa três trechos em Creative Commons do Wikimedia Commons (CC BY-SA 4.0). Tudo o que vem abaixo foi medido em um deles: 39 segundos de um jogo internacional feminino sub-17, 1280×720 a 29,97 fps, 1.170 quadros, de uma câmera baixa atrás da linha de fundo que varre metade do campo. O protótipo processa todos os quadros dele. A demonstração no cluster usa um corte de 20 segundos (599 quadros) e processa um quadro a cada dois. Nenhum dos trechos tem passes rotulados.

## Correção 1: ajuste fino do detector de jogadores

As primeiras execuções usavam um checkpoint do COCO, que não tem classe de goleiro nem de árbitro, e o motor precisa do goleiro. Em 25 de setembro de 2026 fiz o ajuste fino do RF-DETR num dataset público de futebol com quatro classes. Na divisão de validação do dataset, os melhores números dele foram mAP@50-95 de 0,372 e mAP@50 de 0,742. São números de detecção, não de impedimento.

Os jogadores e a separação dos times melhoraram visivelmente. Eventos: 0. A bola estava visível em 547 de 1.170 quadros (47%), numa trajetória quebrada em 34 pedaços, e 60 chutes detectados não viraram nenhum evento.

## Correção 2: um modelo dedicado de bola

Um segundo RF-DETR, treinado só num dataset de bola com 4.948 imagens:

| Execução do protótipo, 1.170 quadros | Detector compartilhado | Modelo dedicado de bola |
|---|---|---|
| Bola visível | 547 (47%) | 1.086 (93%) |
| Fragmentos da trajetória | 34 | 2 |
| Chutes detectados | 60 | 86 |
| Eventos | 0 | 0 |

O recall dobrou e a saída não mudou. O motivo estava na cinemática que o motor calculou a partir dessa trajetória: velocidade mediana da bola de 15,2 m/s, máxima de 185 m/s (666 km/h), e 958 de 1.127 quadros acima do limiar de chute de 6 m/s². O trecho inteiro parecia um chute contínuo. Multiplicar o limiar por dez só levou a contagem de chutes de 86 para 64.

Cerca de uma detecção em cada dez caía em algum outro objeto, a 100 ou 200 px de distância, e voltava. Aceleração é uma segunda derivada, então cada escapada fabricava um chute. Um limiar de confiança não separava os casos: a confiança média era 0,636 depois de um salto grande, contra 0,716 depois de um passo calmo. O detector errava com confiança.

Com a bola pulando de um lado para o outro, havia um dono da posse definido em 49 de 1.170 quadros. Dos 86 chutes, 79 não tinham passador e 7 não tinham recebedor. Nenhum chegou à avaliação de impedimento.

## Correção 3: um filtro de movimento, em metros

O tracker agora leva adiante a última posição aceita da bola e rejeita uma observação que uma bola de futebol não teria como alcançar no tempo decorrido. Ele trabalha em metros, não em pixels, porque a perspectiva faz a relação entre pixels e metros variar várias vezes ao longo do quadro. Um quadro rejeitado é gravado como "bola não visível" e nunca é interpolado, para que o gate `BALL_NOT_VISIBLE` do motor faça o trabalho dele.

| Mesmos artefatos, tracker rodado de novo | Sem filtro | Com filtro |
|---|---|---|
| Pior salto entre quadros | 12,14 m | 1,63 m |
| Chutes | 86 | 54 |
| Bola visível | 93% | 60% |
| Chutes que chegam à avaliação | 0 | 1 |

A queda de visibilidade é o custo: 380 observações rejeitadas, e uma parte maior do trecho marcada como desconhecida.

Esse único chute virou o primeiro evento do projeto, no quadro 282: `INCONCLUSIVE`, motivo `RECEIVER_MISSING`. O motor achou um chute, um passador, um recebedor, o time deles e a direção de ataque, e então se recusou a julgar, porque o recebedor não tinha posição conhecida no momento do chute. Não é um veredito. Mostrou que o caminho do passe conseguia rodar, no protótipo, que processa todos os quadros.

A revisão achou dois bugs no filtro. Um quadro sem homografia era tratado como bola fora do campo, o que rejeitou as 36 detecções de um fixture de teste sem calibração; o trecho em que eu media tem homografia válida em todos os quadros, então nunca teria mostrado isso. E o raio permitido crescia com a idade da última posição aceita, de modo que um detector que ficasse pulando entre dois objetos era rejeitado por cerca de um segundo e depois aceito: o filtro se desligava justamente no caso para o qual foi escrito.

O mesmo registro de decisão cita um remédio que deixei de lado de propósito: afrouxar os limiares de posse até aparecerem eventos. Sem nada rotulado, nada permitiria distinguir um evento correto de um acaso com confiança alta. Guarde isso para a correção 5.

## Correção 4: implantar o que eu tinha treinado

Até 8 de outubro de 2026, o detector com ajuste fino nunca tinha sido exportado. O chart do Helm ainda apontava para o modelo do COCO, e o checkpoint treinado em 25 de setembro ficou no disco enquanto todas as execuções no cluster usavam o antigo. O trabalho que faltava era uma exportação e um upload.

Com ele implantado, no trecho de 20 segundos: 152 tracks, uma divisão de times de 65/64, 11 atribuições de goleiro, 16 chutes. Eventos: 0. A bola estava visível em 34,7% dos quadros processados, em 26 fragmentos cujo comprimento mediano era de um quadro.

A alavanca óbvia era o fatiamento da bola (slicing): uma segunda passada de detecção sobre recortes sobrepostos da imagem. Medi, e depois implantei o modelo dedicado de bola sem ele:

| Trecho de 20 s, no cluster | Bola visível | Maior sequência | Chutes | Tempo | Eventos |
|---|---|---|---|---|---|
| Detector de quatro classes | 34,7% | 56 quadros | 16 | 85 s | 0 |
| + fatiamento | 38,0% | 27 quadros | 22 | 273 s | 0 |
| Modelo dedicado de bola, sem fatiamento | 59,0% | 94 quadros | 28 | 94 s | 0 |

O fatiamento aumentou a proporção de quadros com bola e cortou pela metade a maior trajetória contínua, com 3,2 vezes o tempo de execução. Um passe é confirmado seguindo a bola do chute até um recebedor, então o que conta é a continuidade, e o fatiamento a trocava por avistamentos espalhados. Ficou desligado, com a medição escrita ao lado da flag. O modelo dedicado foi a melhor troca, e mesmo assim deu 0 eventos.

## Correção 5: o bug estava na camada barata

A essa altura o cluster achava 28 chutes, posicionava os jogadores no campo em 99,9% das detecções e tinha homografia válida em todos os quadros. Um pequeno teste de diagnóstico, que informa qual gate descartou cada chute, mostrou que todos caíam pelo mesmo motivo: sem passador. A posse era estabelecida em **0 de 599 quadros**.

Havia duas causas.

**O raio era um palpite.** Um jogador tem a posse quando está a menos de `possession.radius_m` da bola, e esse valor era 1,2 m. O número deveria sair da calibração com trechos rotulados, que nunca rodou. Medido no trecho, o jogador mais próximo da bola está a 2,15 m na mediana, e a menos de 1,2 m em só 8,5% dos quadros. Subi para 2,5 m, com um argumento baseado no orçamento de erro (o erro de reprojeção da própria calibração mais o fato de localizar o jogador por uma caixa delimitadora), sem ajuste aos dados. Os quadros com um jogador do time dentro do raio foram de 15 para 142.

A posse continuou em exatamente 0.

**A contagem estava errada.** `min_frames: 3` exigia três quadros consecutivos do vídeo. O cluster roda a percepção em um quadro a cada dois (`SV_FRAME_STRIDE=2`), e os quadros intermediários são preenchidos com marcadores vazios para que a indexação por número de quadro continue barata. Os candidatos, portanto, alternavam entre um id de track e nada. Nenhuma sequência passava de comprimento 1. A posse era impossível com qualquer passo acima de 1, com qualquer raio.

Nem os testes nem o protótipo tinham como mostrar isso: antes da correção, nenhum teste do pacote de regras montava um vídeo com as lacunas que o passo deixa, e o protótipo processa todos os quadros. A correção conta a sequência em observações: quadros que o pipeline nunca olhou não quebram a sequência nem somam a ela.

| Sobre os artefatos da última execução no cluster | Antes | Depois (`rules-1.1.0`) |
|---|---|---|
| Quadros com posse | 0 de 599 | 242 de 599 (40,4%) |
| Chutes com passador | 0 | 16 de 28 |
| Chutes que chegam à avaliação | 0 | 2 |
| Eventos | 0 | 2 |

```
frame 460  PASS  REVIEW_REQUIRED  ONSIDE  conf 0.60
frame 472  PASS  DETECTED         ONSIDE  conf 0.71
```

Esses são os primeiros vereditos que o motor produziu com vídeo real. O que eles são, exatamente:

- Vêm de `sv rules --local` sobre os artefatos da última execução no cluster. Nenhuma execução completa no cluster foi feita com a correção.
- Não se sabe se "posição legal" está certo em algum dos dois quadros. Não há gabarito.
- Os dois são eventos `PASS`, o tipo usado quando a Regra 11.1 resolve o lance sem precisar de linha (o recebedor está no próprio campo, ou na mesma linha da bola ou atrás dela). O sistema ainda não marcou nenhum impedimento.
- A confiança de 0,71 passa de um limiar de detecção de 0,7 que nunca foi calibrado.
- Dez dias depois de registrar que não afrouxaria os limiares de posse, mudei um deles. O que posso dizer a favor: o novo raio foi defendido pelo orçamento de erro, sozinho não produziu nada, e a causa que importava era um bug. O raio continua provisório.

Um teste de regressão agora cobre os dois lados de `min_frames` com passo 2.

## O que as execuções descartadas revelaram

**Uma travada causada pelo próprio benchmark.** Uma execução em rajada foi descartada porque um job que normalmente leva cerca de 135 s levou cerca de 13 minutos, com o cluster ocioso. O `sv api` escala pela taxa de requisições, e o gerador de carga consulta cada job a cada dois segundos: cerca de três requisições por segundo para seis vídeos, o bastante para escalar a API para cima e para baixo três vezes em trinta minutos. Uma dessas reduções matou uma réplica que segurava uma mensagem do fan-in, que ficou invisível até o tempo de visibilidade expirar. Nada se perdeu, e nenhum alerta disparou, porque a travada foi mais curta que o limiar do alerta. O benchmark estava comandando o autoscaler que ele media. A página de benchmarks cita as três execuções excluídas e o motivo de cada uma.

**Um limite de CPU que o Kubernetes não enxergava.** Uma execução de demonstração levou 457 s, contra 214 s publicados. O worker de visão ficou cravado em 1,00 núcleo do seu limite de 2, com 0 eventos de throttling em 3.741 períodos de cgroup. A causa era um `docker update --cpus=1` esquecido no nó do kind que hospeda os pods de visão. O nó continuava anunciando as 14 CPUs, e os contadores do próprio pod continuavam limpos. Uma varredura de threads no nó limitado dizia que uma thread era melhor que duas, então mudei threads e tamanho de lote junto com o gatilho de escala, e a execução seguinte levou 637 s. Foi essa execução mais lenta que denunciou o limite. Sem o limite, duas threads são 1,87 vez mais rápidas que uma (564 contra 1.056 ms por quadro). Custou um dia de diagnóstico errado. E `docker update --cpus=0` não remove o limite; `--cpu-quota=-1` remove.

## Outras coisas que quebraram

- **A primeira execução no kind falhou em silêncio.** Um worker de visão foi morto por falta de memória, e um processo morto não registra nada: nem linha de erro, nem log, nem span. O job ficou em `SEGMENTED` com erro nulo enquanto as mensagens dele escoavam para uma fila de mensagens mortas que ninguém lia. O observador dessas filas e os alertas vêm dessa execução.
- **Permissões de IAM faltando eram invisíveis localmente.** Os serviços em Go resolvem todas as filas de mensagens mortas na inicialização, e a política só liberava as filas de origem. Na AWS nenhum deles teria subido. O Floci não aplica IAM.

## O que isto não mostra

Nenhuma acurácia. Não existem trechos rotulados, então não há precisão, nem recall, nem limiar calibrado: os números do arquivo de regras são provisórios. Um trecho, uma calibração manual, e uma homografia que deriva enquanto a câmera se move. O motor julga a posição de impedimento no momento do passe (Regra 11.1) e mais nada, e localizar um jogador por uma caixa delimitadora subestima um atacante inclinado em 0,3 a 0,6 m, segundo a estimativa do projeto, o que é no mínimo o tamanho da margem de revisão. Nada rodou na AWS. As medianas do benchmark são anteriores ao modelo atual. E os dois vereditos ainda não têm uma execução completa no cluster por trás.

## O que eu diria a um time construindo isso

1. **Faça o "não aconteceu nada" se explicar.** Meu desenho de incerteza cobria passes confirmados e nada antes deles, então uma execução que não emite nada ficava igual a uma execução que não tinha nada para emitir. Contar por que cada chute foi descartado achou as duas causas. Se essas contagens estivessem no resultado de toda execução, a primeira já as teria mostrado, antes do desvio pelo detector, pelo fatiamento e pelo modelo de bola.
2. **Teste a camada determinística com a amostragem que o pipeline implantado usa.** O motor tem muitos testes, e antes da correção nenhum deles montava um vídeo com as lacunas que o passo 2 deixa.
3. **Meça o que a etapa seguinte consome.** A visibilidade da bola subiu sem ajudar: com o primeiro modelo de bola porque as detecções novas estavam erradas, com o fatiamento porque estavam espalhadas. O que importava era precisão e continuidade.
4. **Confira o que está implantado.** Um modelo treinado ficou no disco por quase duas semanas enquanto o cluster rodava o antigo.
5. **Dê nome às execuções que você exclui, e verifique se o seu instrumento de medição está conduzindo o sistema.** A travada descartada agora é uma questão de projeto em aberto no backlog do projeto.
6. **No kind, leia o cgroup do nó antes de acreditar num número de vazão.** O Kubernetes não avisa que um nó está limitado.
7. **Sem rótulos, um veredito é um marco, não um resultado.** Dois eventos depois de quatro semanas sem nenhum é um avanço no encanamento. Ainda não diz nada sobre impedimento.

---

*Projeto: [github.com/ricardocunha/sportsvision](https://github.com/ricardocunha/sportsvision) (Apache-2.0), incluindo os [benchmarks](https://github.com/ricardocunha/sportsvision/blob/main/docs/benchmarks.md), a [página de avaliação](https://github.com/ricardocunha/sportsvision/blob/main/docs/evaluation.md) e os [registros de decisão](https://github.com/ricardocunha/sportsvision/blob/main/docs/adr/README.md). Vídeos: três trechos do Wikimedia Commons, CC BY-SA 4.0, de NaBUru38 (Copa do Mundo Feminina Sub-17 da FIFA de 2018, Nova Zelândia x Canadá, trechos 21 e 27) e Manchesterunited1234 (FC Versailles 78 x AS Nancy-Lorraine, 08/03/2024, trecho 157); nenhum quadro é reproduzido aqui. Dados de treino: football-players-detection e football-ball-detection do Roboflow Universe, CC BY 4.0. Modelos: RF-DETR e SigLIP (Apache-2.0), ByteTrack via supervision (MIT). Os diagramas são do próprio projeto. Não é um sistema de VAR nem é comparado com um. Rascunhos e a fonte de cada número: [github.com/ricardocunha/ensaios › articles/2027-01-sportsvision-offside](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside).*
