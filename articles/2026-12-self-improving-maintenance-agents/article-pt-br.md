---
title: "Agentes de manutenção que aprendem com os próprios erros"
subtitle: "Um agente de LLM com memória episódica diante dos alarmes e do livro de falhas de um parque eólico real: o que a memória mudou, o que não conseguiu mudar, e por que 21 incidentes não provam nada em nenhuma direção"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — números finais (code/docs/RESULTS.md), dados do Brasil com fontes em code/docs/DATA.md
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents
---

# Agentes de manutenção que aprendem com os próprios erros

A promessa de um agente de manutenção "que se aprimora sozinho" é simples. O agente diagnostica um alarme, o livro de manutenção depois conta o que aconteceu de verdade, o agente guarda a lição e, na próxima vez, acerta mais. Ninguém retreina nada; quem aprende é a memória.

Eu queria saber se isso funciona com dados reais, e como dá para saber. Então construí um agente para um parque eólico real, reproduzi 23 meses de alarmes na ordem em que aconteceram e comparei três versões: sem memória, com memória sem filtro e com memória atrás de um filtro (o "gate"). A ideia é o projeto nº 5 do vídeo *"5 AI Agents Projects to Build in 2026"*; a arquitetura, o código e os números são meus.

Resumindo: a primeira rodada mostrou que memória não conserta um agente cuja decisão nunca muda. O agente respondeu "inspecionar" para todos os 77 alarmes, com e sem memória. Fiz então uma única rodada de mudanças, definida antes de rodar de novo, e repeti tudo. Ele continuou respondendo "inspecionar" em 230 de 231 decisões. A memória mudou uma decisão, em um episódio, e essa é a conclusão mais honesta que posso dar: neste parque, com este modelo, a memória não melhorou o agente, e 21 incidentes não provariam nada mesmo que tivesse melhorado.

Todos os números do experimento vêm do `docs/RESULTS.md` do repositório; os dados sobre o Brasil têm as fontes em `docs/DATA.md`.

## Por que isso importa para o Nordeste

Em 2024, a energia eólica gerou 107,7 TWh, 14,1% da oferta interna de energia elétrica do Brasil (EPE, *Balanço Energético Nacional 2025*). O subsistema Nordeste respondeu por 92,2% da geração eólica do país naquele ano e, em 22 de agosto de 2024, um dia de recorde, os parques da região produziram 129% do que o Nordeste consumiu (dados do ONS, compilados no boletim anual 2024 da ABEEólica). Esses parques produzem exatamente as duas coisas de que este agente precisa: SCADA de 10 minutos de cada turbina e um registro de manutenção.

O que é público fica um nível acima. O ONS publica a geração por usina, hora a hora, e, desde dezembro de 2022, a geração verificada e a velocidade do vento por parque eólico a cada meia hora. O SIGA da ANEEL é um cadastro de usinas. As taxas de indisponibilidade forçada do ONS cobrem usinas hidrelétricas, térmicas e nucleares, não eólicas. Nada disso é por turbina, e nada diz qual componente falhou. O único SCADA público por turbina que encontrei no Nordeste é um conjunto de dados de pesquisa de dois parques do litoral, Pedra do Sal e Beberibe (agosto de 2013 a julho de 2014); a descrição lista SCADA, torre anemométrica e lidar, e nenhum registro de falhas. Por isso os dados aqui são portugueses. A pergunta que o artigo responde é o que um operador no Ceará ou no Rio Grande do Norte precisaria para montar isso com os próprios dados, e o que deveria esperar do resultado.

## A montagem

```
SCADA 10 min ─► temperaturas horárias menos a ambiente ─► modelo de comportamento normal por sinal ─► resíduos
                                                                                                  │
                  Isolation Forest nos resíduos, retreinado a cada 30 dias ─► dias de alarme ─► episódios
                                                                                                  │
  episódio (só o 1º dia de alarme) ─► agente (Pydantic AI, Qwen3-8B local) ─► Diagnosis{componente, ação, …}
          ▲                                  │ ferramentas: série de resíduos · contexto · livro de manutenção (tudo cortado no momento da decisão)
          │                                  ▼
  memória: (situação, diagnóstico, desfecho) ◄── desfecho vindo do livro, visível só quando já seria conhecido
          │
     gate: desfecho conhecido · parecido · recente · mesma turbina ou mesmo grupo de componentes · no máximo 3
```

O agente responde a cada alarme com um diagnóstico tipado: qual componente do livro de manutenção está falhando (ou nenhum), e *inspecionar*, *monitorar* ou *ignorar*.

## Os dados, e duas coisas que tive de corrigir antes de confiar neles

As turbinas são do "Wind Farm 1" da EDP, em Portugal: cinco turbinas, de janeiro de 2016 a novembro de 2017, dados a cada 10 minutos. O SCADA vem do benchmark CARE to Compare (Wind Farm A, 158 MB). Os rótulos vêm dos livros de falhas da EDP de 2016 e 2017. Os dois são CC BY-SA 4.0.

O livro tem 28 linhas de falha: grupo hidráulico 8, gerador 7, rolamento do gerador 6, caixa multiplicadora 4, transformador 3. As observações misturam falhas reais ("Generator bearings replaced") com problemas de sensor ("Generator temperature sensor failure").

**Correção 1: o calendário.** O CARE desloca as datas do Farm A para esconder a origem. Achei o deslocamento casando o fim dos eventos de anomalia do CARE com as datas do livro: +2191 dias, e +2192 em dois dos arquivos. No calendário bruto do CARE, 8 pares de arquivos sobrepostos discordam (só 13-17% dos valores batem). Desfeito o deslocamento, os 38 pares sobrepostos concordam em 100% dos valores. Isso também liga os ativos anônimos do CARE às turbinas da EDP, e é essa ligação que me permite usar o livro da EDP. O CARE associa só 11 das 28 linhas do livro a um evento; nenhuma das 16 falhas de 2016 tem evento.

**Correção 2: um vazamento nos rótulos.** O Farm A tem um `status_type_id` em cada linha. Parece um sinal de estado de operação. Não é: o código 4 marca exatamente os 14 dias antes de cada registro do livro, e o código 3 os 3 dias depois. Um detector que o usasse como variável "previria" todas as falhas. Não uso em lugar nenhum.

O SCADA ainda me contou mais uma coisa: **a data do livro marca uma parada, não o início da degradação.** Em 12 das 28 datas a turbina desarma ali mesmo; outras 8 caem no fim de uma parada que já estava em curso. Por isso toda janela de detecção termina no dia anterior à data registrada.

As linhas do livro foram agrupadas em **21 incidentes** (mesmo componente em até 45 dias, ou qualquer componente em até 7 dias). Esse é todo o gabarito: 21 incidentes em 5 turbinas.

## Detecção: a maior parte do trabalho foi contra as estações do ano

Um Isolation Forest ingênuo sobre as médias brutas dos sensores, treinado nos primeiros 60 dias, aprendeu o inverno e passou a alarmar no verão: até 70-74% dos dias em julho e agosto de 2016. Os "acertos" antes das falhas (21 de 24 em 14 dias) diziam pouco quando 66% das janelas tranquilas também tinham alarme.

Duas coisas resolveram. **Retreino progressivo** a cada 30 dias, com o limiar definido nos últimos 21 dias ou mais que o modelo ainda não viu (um teste prova que a nota de um dia não muda quando algo depois dele muda). E **resíduos de comportamento normal**: um modelo de gradient boosting por temperatura prevê quanto ela sobe acima da ambiente a partir de vento, potência, rotação e carga recente, e o detector avalia o que sobra. Isso elimina principalmente os alarmes do parque inteiro, causados por clima e rede: as datas com 3 ou mais das 5 turbinas alarmando caíram de 12-13 para 3-4.

Com um orçamento equivalente de no máximo um dia de alarme saudável por turbina-mês, o Isolation Forest nos resíduos pegou **7 de 18** incidentes avaliáveis dentro de 14 dias (nas três sementes), contra uma taxa de 0,18-0,20 nas janelas tranquilas. Rolamentos do gerador foram detectados (4 de 5); incidentes hidráulicos (0-2 de 7) e da caixa multiplicadora (1 de 4), em geral, não.

O detector consegue dizer *tem algo errado*. É fraco em dizer *o quê*: o grupo de resíduo mais alto coincidiu com o componente do livro em **3 de 22** episódios pré-incidente. Essa lacuna é o motivo de existir o agente.

O detector gerou **77 episódios**: 22 começam até 30 dias antes de um incidente (cobrindo 9 incidentes), 29 começam num dia saudável (falsos alarmes) e 26 ficam perto de um incidente, na maioria depois de reparos. Essa é a carga de trabalho do agente, e é realista: a maioria dos alarmes não é seguida de falha.

## O agente, a memória e o gate

**O momento da decisão é o fim do primeiro dia de alarme.** A tabela de episódios da detecção resumia episódios inteiros, de até 18 dias. Isso é informação do futuro. Então a visão do agente é reconstruída só a partir do primeiro dia, e as três ferramentas dele (série de resíduos de qualquer grupo de componentes, contexto como as notas das outras turbinas, e o livro de manutenção) devolvem apenas dados anteriores a esse momento. Vista assim, o grupo mais alto do detector acerta em **1 de 22** episódios pré-incidente, não em 3.

**Memória.** Um registro por episódio diagnosticado: o resumo e o vetor de resíduos do primeiro dia, o diagnóstico do agente e o desfecho. O desfecho vem só do livro de manutenção: a primeira linha do livro naquela turbina em até 30 dias, conhecida na data dela; senão, "nenhuma falha em 30 dias", conhecido no 31º dia. Até lá, a memória diz "desfecho ainda desconhecido". A memória nunca lê os rótulos usados na avaliação.

**A busca** usa similaridade de cosseno entre os vetores de resíduos do primeiro dia (24 sinais, sign·log1p|z|). Não há modelo de embedding: a situação *é* um vetor de resíduos.

**O gate** foi fixado antes de qualquer execução do modelo: desfecho conhecido, similaridade ≥ 0,5, no máximo 365 dias de idade, mesma turbina ou mesmo grupo de componentes no topo, no máximo 3. O braço "sem gate" pega os 3 episódios passados mais parecidos, sem filtro.

**Sem olhar o futuro, com teste.** Um teste reproduz um parque sintético três vezes: como está, com o futuro alterado e cortado numa data; todo prompt, resultado de ferramenta, decisão do gate e diagnóstico antes dessa data precisa ser idêntico.

**O que o gate faz, antes de rodar qualquer modelo.** Os prompts sem gate carregam 2,92 memórias em média; os com gate, 0,97. E este é o número que enquadrou todo o resto: em só **4** (sem gate) e **1** (com gate) dos 22 episódios pré-incidente alguma memória mostrada registra uma falha passada do componente que depois falhou. Neste parque, a memória raramente consegue entregar a resposta ao agente. Se ajuda, tem de ajudar sobretudo pelo outro lado: mostrando que alarmes parecidos não deram em nada.

## Rodada 1: o agente nunca saiu do "inspecionar"

Qwen3-8B (4 bits) num servidor mlx-lm local, sem modo de raciocínio, temperatura 0. 77 episódios × 3 braços, 0 erros.

| Braço | Componente certo (de 22 pré-incidente) | Inspecionar em pré-incidente (de 22) | Não inspecionar em falso alarme (de 29) | Adequado (de 51) | Tokens de entrada por episódio |
|---|---|---|---|---|---|
| sem memória | 1 | 22 | 0 | 22 | 6,7 mil |
| memória, sem gate | 2 | 22 | 0 | 22 | 9,3 mil |
| memória, com gate | 1 | 22 | 0 | 22 | 7,7 mil |
| só o detector (1º dia) | 1 | – | – | – | 0 |

O agente respondeu **"inspecionar" em todos os 77 episódios, nos três braços**, com confiança de 0,75 a 0,92, e indicou o grupo mais alto do detector em 77, 71 e 72 deles. Era o detector mais um "inspecionar".

A memória mudou, sim, o componente em 9 episódios, sempre na mesma direção: para `generator_bearing`. Rolamentos do gerador dominam as falhas que a memória mostra (44 das 70 memórias de falha nos prompts sem gate), e o agente copiou. Duas vezes isso atingiu um episódio avaliado:

- **Episódio 45 (T09, dez/2016), certo por um motivo fraco.** O braço sem gate trocou gerador por rolamento do gerador, o que estava certo. As três memórias dele eram episódios da T07 de abril de 2016, com 245 a 274 dias, similaridade 0,34-0,45, todos seguidos de falha de rolamento na T07. O gate teria rejeitado as três.
- **Episódio 19 (T07, jun/2016), a mesma atração, errada.** Uma memória de falha de rolamento na T09 (similaridade 0,77) levou o braço sem gate de gerador para rolamento do gerador. O incidente foi no transformador.

A lição da rodada 1 foi sobre o agente, não sobre a memória: sem custo para uma inspeção e sem nada que pese "cinco alarmes parecidos não deram em nada" contra "um deu em falha", inspecionar é sempre a resposta que parece segura. Memória não muda uma decisão que nunca se mexe.

## Rodada 2: uma rodada de correções, definida antes de rodar de novo

Me permiti uma única rodada, escrita no plano antes de qualquer execução nova, sem espiar quais episódios precedem incidentes:

1. **Memória como histórico.** Antes das memórias individuais, o prompt agora diz o que aconteceu depois de alarmes parecidos, contando só desfechos já conhecidos no momento da decisão. Por exemplo: *"36 com desfecho conhecido. 17 deles foram seguidos de uma falha no livro de manutenção daquela turbina em até 30 dias (generator_bearing 8, transformer 4, generator 3, gearbox 2); 19 não foram seguidos de nada. Outros 4 ainda estão pendentes."* O braço com gate conta o próprio conjunto (o gate sem o limite de 3); o braço sem gate conta todos os alarmes passados do parque.
2. **Justificar contra o histórico.** Quando a maioria dos alarmes parecidos não deu em nada e o agente ainda assim escolhe inspecionar, um campo novo precisa dizer o que há de diferente desta vez. Uma resposta vazia volta para o modelo mais uma vez.
3. **Custos nas instruções.** Uma inspeção custa cerca de uma diária de equipe (1); uma falha que uma inspeção a tempo teria pegado custa cerca de 10; monitorar não custa nada agora, e o detector continua vigiando. A proporção é uma premissa do domínio, não ajustada a estes dados.

Também rodei o braço sem memória com o prompt novo, para separar o efeito do prompt do efeito da memória.

| Braço | Prompt | Componente certo (de 22) | Inspecionar em pré-incidente (de 22) | Não inspecionar em falso alarme (de 29) | Adequado (de 51) | Tokens de entrada por episódio |
|---|---|---|---|---|---|---|
| sem memória | v1 | 1 | 22 | 0 | 22 | 6,7 mil |
| sem memória | v2 | 1 | 22 | 0 | 22 | 8,1 mil |
| memória, sem gate | v1 | 2 | 22 | 0 | 22 | 9,3 mil |
| memória, sem gate | v2 | 2 | 22 | 0 | 22 | 10,7 mil |
| memória, com gate | v1 | 1 | 22 | 0 | 22 | 7,7 mil |
| memória, com gate | v2 | 1 | 22 | 0 | 22 | 7,8 mil |

**O prompt sozinho não mudou nada.** Com custos nas instruções e sem memória, o agente ainda inspecionou os 77 episódios e ainda indicou o grupo mais alto do detector em todos.

**A memória mudou uma decisão em 231.** As curvas mensais de aprendizado são linhas retas, uma em cima da outra: o "adequado" acumulado é igual ao número de episódios pré-incidente vistos até ali, em todos os braços e nas duas versões, porque o agente inspecionou todos eles e todos os falsos alarmes também.

O interessante é *como* o agente usou o histórico. Quatro episódios mostram isso:

- **Episódio 73, a única mudança.** T01, agosto de 2017, um alarme de transformador duas semanas depois de um registro de "transformer fan damaged" no livro. O histórico com gate dizia: 3 alarmes parecidos de transformador no passado, 0 seguidos de falha. O agente com gate escolheu *monitorar*, com urgência baixa: "similar past alarms … did not result in logbook failures" (alarmes parecidos no passado não resultaram em falhas no livro). O agente sem memória inspecionou, citando o reparo recente. Duas semanas depois de um reparo, monitorar é o que eu também faria. Foi para isso que o desenho foi feito, e aconteceu uma vez.
- **Episódio 50, uma justificativa que se contradiz.** Um falso alarme na T11. O histórico: 2 alarmes parecidos na mesma turbina, nenhum dos dois seguido de falha. O agente inspecionou mesmo assim e justificou com "a higher detector score (2.9) compared to past alarms (2.6 and 2.9), and the residual in generator_bearing is higher (+3.1 vs. +3.3 and +3.8)", ou seja, uma nota do detector "maior" (2,9 contra 2,6 e 2,9) e um resíduo "maior" (+3,1 contra +3,3 e +3,8). As duas comparações são falsas pelos próprios números dele. Meu validador conferia se o campo estava preenchido. Não tinha como conferir se era verdade.
- **Episódio 17, em que o histórico apontava para o lado errado.** T07, junho de 2016. O histórico: 2 alarmes parecidos, nenhum dos dois seguido de falha. O agente inspecionou ("more pronounced residuals", resíduos mais pronunciados), e veio um incidente no transformador. Um agente que obedecesse ao histórico teria deixado passar. Foi o único episódio pré-incidente em que o histórico com gate disse "quase sempre nada".
- **Episódio 45, ainda certo por um motivo fraco.** O agente sem gate continuou indicando o rolamento do gerador por causa de três memórias pouco parecidas de outra turbina. O gate filtra essas memórias, e o agente com gate continuou indicando o componente errado. Filtrar a memória deixou o agente mais criterioso aqui, e menos preciso.

Quando o histórico com gate disse "quase sempre nada" (15 de 77 prompts), o agente o contrariou 14 vezes. O histórico sem gate, do parque inteiro, disse isso em 41 prompts, e o agente o contrariou nas 41.

Há também um motivo para "inspecionar" não estar simplesmente errado neste parque. O histórico do parque inteiro dizia ao agente que 34% a 62% dos alarmes passados tinham sido seguidos de uma falha no livro em até 30 dias (a partir do momento em que pelo menos dez desfechos eram conhecidos). No total, 27 dos 77 episódios foram. Com uma inspeção custando um décimo de uma falha não detectada, inspecionar todo alarme fica perto da resposta de menor custo esperado. Os alarmes do detector são raros (no máximo cerca de um dia de alarme saudável por turbina-mês), então cada um carrega um risco real. O agente não tinha como melhorar em *se* inspecionar, porque "sempre" já era quase ótimo sob a minha própria premissa de custo. Onde poderia ter ajudado, em indicar o componente, ele copiou o detector.

## O que uns 20 incidentes podem e não podem dizer

Nenhuma das diferenças acima é um resultado estatístico. São 22 episódios pré-incidente cobrindo 9 incidentes, e 29 falsos alarmes. Uma diferença de um ou dois episódios entre braços está dentro do que outra semente, outro mês ou um prompt reescrito mudariam. O que este estudo de caso consegue fazer é mostrar o mecanismo, episódio por episódio: o que a memória pôs na frente do agente, e se a decisão mudou. É também o que você precisaria olhar no seu próprio parque antes de confiar em qualquer curva.

## O que eu diria a um time construindo isso

1. **Verifique se a decisão chega a mudar antes de pôr memória.** Minha primeira rodada parecia um experimento sobre memória. Era, na verdade, uma medição do comportamento padrão do modelo. Se o braço sem memória dá a mesma resposta para todos os casos, nenhum desenho de memória consegue mostrar uma curva de aprendizado.
2. **Conte a taxa base antes de discutir custos.** Neste parque, cerca de um terço dos alarmes do detector (27 de 77) precedeu uma falha no livro. Com uma proporção de custo de 1 : 10, isso torna "inspecionar" racional. Uma memória que ensina "a maioria dos alarmes é ruído" só ajuda onde a maioria dos alarmes *é* ruído, ou seja, com um detector mais ruidoso, ou num parque com um detector mais barato e bem calibrado.
3. **Justificativa obrigatória é um campo, não uma checagem.** O agente preencheu sempre, uma vez com números que contradiziam a afirmação. Se o motivo importa, confira em código (compare as notas, os resíduos), do mesmo jeito que você conferiria uma citação.
4. **O gate deixou a memória mais relevante e o prompt mais curto, não as respostas melhores.** Ele reduziu as memórias por prompt de 2,92 para 0,97 e eliminou os casos de baixa similaridade. Neste parque, foram justamente esses casos de baixa similaridade que produziram o único acerto de componente causado pela memória.
5. **Peça os dados que tornariam isso testável.** Para os operadores do Nordeste, as peças são SCADA a cada 10 minutos e um registro de falhas com componente, data e observação, mantido por turbina durante anos. Com algumas centenas de incidentes em vez de 21, o mesmo arcabouço, os testes contra olhar o futuro e os três braços dariam uma resposta em vez de um estudo de caso. Não encontrei nenhuma fonte brasileira, órgão público ou operador, que publique esses dados.

---

*Ideia do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (projeto nº 5, um agente de manutenção de turbinas eólicas que se aprimora sozinho). Dados: CARE to Compare Wind Farm A (Zenodo 15846963) e os livros de falhas da EDP de 2016/2017, ambos CC BY-SA 4.0. Dados do Brasil: EPE, Balanço Energético Nacional 2025; dados do ONS via ABEEólica, Boletim Anual 2024. Código, testes e todos os números: [github.com/ricardocunha/ensaios › articles/2026-12-self-improving-maintenance-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents).*
