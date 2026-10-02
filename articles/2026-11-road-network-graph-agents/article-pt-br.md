---
title: "Agentes de grafo que planejam a manutenção de vias"
subtitle: "A malha viária de Belo Horizonte, 198.991 pedidos de tapa-buraco, um solver de mochila e três agentes Pydantic AI: o que o LLM acrescenta quando as ferramentas fazem a conta do grafo"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — pronto para revisão (números conferidos com code/docs/RESULTS.md)
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents
---

# Agentes de grafo que planejam a manutenção de vias

Toda cidade tem mais buraco do que dinheiro. Alguém precisa decidir quais ruas serão recapeadas este ano e em que ordem, sem fechar ao mesmo tempo duas vias que, juntas, isolam um bairro do hospital mais próximo. Parece trabalho para um agente: olhar a malha, pesar os prós e contras, escrever o plano.

Montei esse sistema de agentes sobre a malha viária real de Belo Horizonte e um ano de pedidos reais de tapa-buraco, e comparei com uma linha de base de otimização simples. Ferramentas determinísticas fazem a conta do grafo. O LLM só faz o raciocínio: quais trechos incluir ou tirar, quais obras agendar juntas e como explicar o plano.

O resultado não é o que o diagrama de arquitetura promete. Neste problema o solver já faz o plano, uma heurística simples agenda melhor, e o LLM contribui com explicação e um leve deslocamento para as ruas com mais pedidos. O interessante é *como* ele falhou, e quanto do texto dele uma auditoria de números consegue de fato garantir.

Todos os números abaixo vêm do `code/docs/RESULTS.md` do repositório.

## A montagem

```
OpenStreetMap (OSMnx) ─► grafo viário ─► trechos ─► betweenness (k=2000)
Pedidos "Tapa-Buraco" da PBH ─► associados aos trechos ─► nota de condição
                                       │
                 valor = condição × criticidade × km, custo sintético
                                       │
          solver de mochila (guloso, ≤1e-5 do exato) ─► plano do solver
                                       │
   Agente de manutenção: inclui / tira trechos, cada um com motivo ─► o solver refaz o plano
                                       │
   Agente de interdições: 15 obras grandes em 3 meses, sem sobreposições que cortem acesso
                                       │
   Coordenador: plano trimestral com os prós e contras, a partir de uma ficha calculada pelas ferramentas
                                       │
   Auditoria (sem LLM): valor vs. solver, agenda recalculada, cada número do texto conferido
```

- **Ferramentas** são funções Python tipadas sobre NetworkX. Elas ranqueiam trechos, resolvem o orçamento com inclusões forçadas ou exclusões, calculam o efeito de um conjunto de interdições sobre 1.000 viagens amostradas e sobre o acesso a hospitais e escolas, e pontuam uma agenda inteira.
- **Agentes** são agentes Pydantic AI com saída tipada. A passagem de um para o outro é código comum, não um agente chamando outro: menos peças móveis para um modelo pequeno.
- **Modelo:** Qwen3-8B, 4 bits, num servidor mlx-lm local, sem modo de raciocínio. Custo zero por chamada, o que importa quando uma avaliação são dezenas de execuções de agente.

A ideia vem do projeto nº 3 do vídeo *"5 AI Agents Projects to Build in 2026"*: agentes sobre o grafo da malha viária. A arquitetura e o código são meus.

## O grafo: Belo Horizonte

Comparei Porto Alegre e Belo Horizonte e escolhi Belo Horizonte, principalmente pelos dados (próxima seção). O grafo viário dela no OSM tem **32.311 nós e 82.984 arestas**. Os tempos de viagem são as estimativas de fluxo livre do OSMnx, então todo atraso abaixo é um limite inferior do que o trânsito real faria.

**Criticidade** é a betweenness das arestas ponderada por tempo de viagem: quantos caminhos mínimos passam por uma via. A betweenness exata neste grafo levaria, pela minha estimativa, de 69 a 86 minutos no notebook (a execução exata não tinha terminado depois de cerca de uma hora), então amostro **k=2000 nós de origem** (321,1 s). Em Porto Alegre, onde a execução exata terminou, k=2000 recuperou 0,98 das 100 arestas do topo exato.

**Aresta é a unidade errada.** As arestas do topo são pedaços consecutivos da mesma via, o Anel Rodoviário. A prefeitura não recapeia uma aresta do OSM; recapeia um trecho de rua. Então junto arestas consecutivas com o mesmo nome e a mesma classe viária em **trechos**, cortando onde uma via maior cruza e a cada 1 km. Isso dá **19.842 trechos**, com mediana de 163 m.

![Trechos viários mais críticos de Belo Horizonte](figures/bh-critical-sections.png)
*Os 100 de 19.842 trechos com maior betweenness amostrada. Dados viários © colaboradores do OpenStreetMap (ODbL), openstreetmap.org/copyright.*

O mapa mostra os corredores esperados: o Anel e as grandes avenidas radiais. Mas betweenness não é impacto de interdição. Fechar o primeiro trecho do Anel atrasa 112 de 1.000 viagens amostradas em 42,5 s, em média. Fechar um trecho da Avenida Quatro Mil Cento e Setenta e Dois, só a 8ª via da lista, atrasa 111 viagens em **388,9 s** em média, porque não existe desvio bom. Por isso o impacto de interdição tem sua própria ferramenta; não dá para lê-lo num ranking.

## Os dados de buraco, e o que eles medem de verdade

Belo Horizonte publica as solicitações de serviço dos cidadãos (BH Digital) como dados abertos, sob CC-BY, com coordenadas. O serviço de reparo de buraco se chama *Tapa-Buraco*. De agosto de 2022 a julho de 2023, o mês mais recente publicado, são **198.991 pedidos** em **88.942 locais distintos**. **95,0%** deles caem a até 30 m de uma via trafegável.

![Pedidos de tapa-buraco por km em Belo Horizonte](figures/bh-pothole-density.png)
*Pedidos de Tapa-Buraco, ago/2022 – jul/2023: locais distintos por km em cada trecho, suavizado. Mostra onde se pede reparo, não a condição medida do pavimento. Dados viários © colaboradores do OpenStreetMap (ODbL), openstreetmap.org/copyright. Pedidos: Prefeitura de Belo Horizonte, BH Digital, dados.pbh.gov.br, CC-BY.*

Dá vontade de chamar isso de "condição da via". Não é. Mede **quem reclama**:

- Ruas residenciais recebem **21,0** locais com pedido por km; o Anel recebe **0,10**. Pouca gente abre pedido de tapa-buraco a partir de uma via expressa, e neste período o Anel nem era via da prefeitura: era rodovia federal mantida pelo DNIT, até a cidade assumir 22,4 km dele em junho de 2025.
- Condição e criticidade quase não se relacionam (Spearman **−0,09**). As ruas de que as pessoas reclamam e as vias de que a malha depende são ruas diferentes.

Por isso a nota de **condição** é um percentil da densidade suavizada de pedidos, e o **valor** de consertar um trecho é condição × criticidade × km. O **custo de reparo** é sintético: área de pavimento, escalada pela condição. Não tenho os custos reais da prefeitura, então o custo está em "m² de recapeamento", não em reais. É uma premissa declarada, não um resultado.

## A linha de base: uma mochila que já é quase ótima

Dado o valor e o custo de cada trecho, escolher o que consertar dentro do orçamento é um problema da mochila 0/1 sobre **11.860 trechos candidatos**. O guloso por valor/custo fica a 1e-5 do ótimo exato (SciPy/HiGHS) e roda numa fração de segundo.

| Orçamento (fração do custo total de reparo) | Trechos | Valor capturado | Pedidos cobertos |
|---|---:|---:|---:|
| 5% | 445 | 54,43% | 5,36% |
| 10% | 952 | 70,24% | 10,89% |
| 20% | 1.997 | 83,98% | 21,65% |

O valor é concentrado: 5% do orçamento captura mais da metade dele, porque a betweenness tem cauda pesada. O solver compra vias arteriais que têm alguns pedidos (Avenida Waldir Soeiro Emrich, Amazonas, Vilarinho, Cristiano Machado, Tancredo Neves), não as ruas residenciais com mais pedidos. Essa diferença, só 5,36% dos pedidos cobertos com 5% do orçamento, é onde eu esperava que o julgamento de um agente fizesse diferença.

Há uma segunda régua determinística. Os **15 trechos mais críticos** do plano são "obras grandes", que fecham a via enquanto duram. Elas precisam caber nos 3 meses do trimestre, no máximo 5 por mês. Uma **violação** é um mês cujas obras, fechadas juntas, cortam acesso a hospital (10 min) ou escola (5 min) que nenhuma obra corta sozinha. Duas agendas determinísticas definem a régua:

- **Ingênua** (ordem de prioridade): 1 violação em todos os orçamentos, sempre do mesmo par: o trecho S00102 do Anel e o trecho S01395 da Avenida Presidente Antônio Carlos no mesmo mês (com 20%, dois trechos da Waldir Soeiro Emrich também entram em conflito nesse mês).
- **Heurística** (checagem de conflito par a par, preenchimento guloso, trocas, sem LLM): **0 violações**, e o pior mês de 17% a 27% abaixo do da ingênua.

## Os agentes

**Agente de manutenção.** Ele vê o plano do solver e pode propor inclusões e exclusões, cada uma com um motivo. Ele nunca monta o plano: o solver refaz o plano com as inclusões forçadas e as exclusões removidas, então caber no orçamento nunca é tarefa do LLM. Um validador rejeita ids desconhecidos, "inclusão" de trechos que já estão no plano e conjuntos inviáveis. Ferramentas: `rank_sections`, `get_section`, `try_plan`.

**Agente de interdições.** Ele recebe as 15 obras grandes e as distribui pelos meses. Ferramentas: `check_schedule` (pontua uma agenda inteira e nomeia os pares em conflito), `closure_impact` e `accessibility_loss`. Ele precisa copiar os números de cada mês das ferramentas e sinalizar todo mês que perde acesso.

**Coordenador.** Ele recebe uma ficha calculada pelas ferramentas (mais os motivos dos outros agentes) e escreve o plano trimestral com os prós e contras. A instrução é usar só números da ficha.

**A auditoria.** Nada nela usa LLM:
- valor, orçamento e cobertura de pedidos comparados ao solver;
- a agenda do agente pontuada de novo pela mesma ferramenta exata, contra as agendas ingênua e heurística;
- cada número que o agente de interdições declara por mês, recalculado do zero;
- cada número do texto, procurado num **livro-razão** com todos os números que as ferramentas devolveram e os prompts mostraram. O texto dos próprios agentes nunca entra no livro-razão, então uma afirmação não consegue se autojustificar.

Rodei o pipeline **3 vezes em cada um de 3 orçamentos** (5%, 10%, 20%) com as mesmas entradas: 9 pipelines, 37 minutos no total no servidor local de modelo, compartilhado com outros trabalhos.

## Resultados

### O agente de manutenção: pequenos ganhos de cobertura, pagos em valor

Ele completou 8 de 9 execuções. A única falha caiu de volta no plano do solver.

| Orçamento | Valor vs. solver (3 execuções) | Pedidos cobertos, agente | Pedidos cobertos, solver |
|---|---|---|---:|
| 5% | 95,44 / 99,74 / 93,78% | 6,11 / 5,33 / 6,40% | 5,36% |
| 10% | 97,42 / 100,00* / 99,41% | 10,99 / 10,89* / 11,97% | 10,89% |
| 20% | 99,98 / 99,99 / 99,98% | 21,62 / 21,61 / 21,62% | 21,65% |

\* o agente falhou; vale o plano do solver.

Todo desvio custa valor, como a função objetivo garante. O que o agente compra com isso é um deslocamento para as ruas de que as pessoas reclamam. As três execuções que incluíram as ruas residenciais com mais pedidos (Rua Joviano Coelho com 509 pedidos, Rua das Verbenas com 358, …) ganharam **de 0,75 a 1,08 ponto de cobertura de pedidos** por 0,6% a 6,2% do valor. Com 20% ele incluiu trechos de alto valor, e a cobertura caiu um pouco.

É uma preferência real: consertar o que o cidadão reporta. Mas daria para colocá-la na função objetivo do solver como um peso e obter a mesma resposta sempre. Não testei isso aqui.

O agente também deu respostas diferentes ao repetir. O Jaccard médio entre pares dos desvios foi **0,137** com 5%, **0,000** com 10% e **0,867** com 20%. Com 10%, as duas execuções bem-sucedidas não compartilharam um único desvio. Os planos finais continuam próximos entre si (Jaccard de 0,951 a 0,997), porque o solver preenche o orçamento em volta do que o agente força.

Ele também ignorou um limite que recebeu. A instrução diz no máximo 6 desvios. 4 das 8 propostas aceitas tinham de 10 a 12, e em 6 de 9 execuções o schema rejeitou uma proposta com 15 a 20. A única falha foram duas rejeições dessas seguidas.

### O agente de interdições: 1 de 9

Este é o resultado principal. O agente de interdições produziu uma agenda em **1 de 9 execuções**. Não o ajustei depois da avaliação completa, porque o jeito como ele falha ensina mais do que outra revisão de prompt.

**6 das 8 falhas vêm de um único id malformado.** A Rua Juarez Teixeira Pinto, trecho **S10128**, é obra grande em todos os orçamentos. É o único id de obra que não começa com `S0`. Na primeira chamada de ferramenta de 6 execuções, o modelo escreveu **`S010128`**, como se todo id tivesse de ter a forma `S0xxxx`. A ferramenta respondeu `unknown section ids: ['S010128']`. Em 4 dessas execuções o modelo reenviou exatamente os mesmos argumentos até esgotar as 3 tentativas. Nas outras 2 ele mudou outra coisa (corrigiu um segundo id errado, ou escreveu `S0128`), mas nunca digitou `S10128`.

**As outras 2 falhas são laços.** As duas receberam `VIOLATION (pairs that conflict: S00102 + S01395)` de `check_schedule`. Uma execução manteve esse par no mês 1 nas 14 chamadas. A outra separou o par e criou um conflito novo no mês 2. As duas terminaram enviando **a mesma agenda 8 vezes** até bater o limite de 14 requisições, apesar de uma instrução para não checar de novo uma agenda já checada. Muitas dessas agendas nem eram válidas: obras repetidas, outras faltando. Minha ferramenta `check_schedule` pontuou todas mesmo assim, porque só o validador da saída final confere se a agenda está completa. Essa é uma falha de desenho de ferramenta da minha parte.

Nas 9 execuções o agente só chamou `check_schedule`. Nunca usou `closure_impact` nem `accessibility_loss`, embora as instruções peçam.

**O único sucesso** evitou a violação, e todos os números dele estavam certos (12/12 campos de mês, 6/6 alertas de acesso). Mas ele colocou o Anel, dois trechos da Antônio Carlos, a Dom Pedro I e o trecho de 388,9 segundos da Avenida Quatro Mil Cento e Setenta e Dois no mesmo mês:

| Agenda (mesmas 15 obras) | Violações | Atraso do pior mês | Nós de hospital que perdem acesso, por mês |
|---|---:|---:|---|
| Ingênua | 1 | 58.766,9 s | 20 / 9 / 14 |
| Heurística (sem LLM) | **0** | **51.731,9 s** | 16 / 13 / 13 |
| Agente | **0** | 66.627,6 s | 19 / 13 / 10 |

O pior mês dele é **28,8% pior que o da heurística**, e 13,4% pior que o da agenda ingênua com as mesmas obras. Os seis alertas de acesso dizem todos "Consider detour plans for hospital/school access".

### O coordenador, e o que uma auditoria de números consegue garantir

O coordenador completou 9 de 9 execuções, e os planos dele são bem escritos. É na auditoria que a coisa fica interessante.

A auditoria estrita achou **227 de 253** números do texto no livro-razão (89,7%). O log da avaliação não guarda o livro-razão em si, então eu o reconstruí repetindo as chamadas de ferramenta registradas. O livro-razão reconstruído bateu com o tamanho e com as contagens estritas registradas nas 9 execuções. Depois classifiquei cada um dos 26 números não encontrados e conferi cada classificação à mão:

| Classe | Quantidade | Exemplo |
|---|---:|---|
| Valor correto, notação diferente | 20 | valor por custo "3.789e-6", exatamente o valor da ferramenta. Minha auditoria lia 3 casas decimais da mantissa: um bug da auditoria |
| Correto, derivado de números das ferramentas | 3 | "Value given up: 48.96%" = 100 − 51,04 |
| Copiado do texto de um agente anterior | 0 | |
| Sem respaldo | 3 | "207 pothole requests, which is 2.1% of all snapped requests" (o certo: 0,11%) |

Se a notação científica for comparada na precisão real e números derivados simples forem aceitos (100 − x, ou a ± b de dois números respaldados no mesmo texto), a nota sobe para **250 de 253 (98,8%)**. O coordenador vai de 105/108 para **108/108**. Os três números sem respaldo são todos afirmações do agente de manutenção sobre o próprio efeito. Um dos motivos diz que os desvios "improve the overall value capture by 3.77 percentage points (from 66.01% to 69.78%)". A própria chamada `try_plan` dele tinha mostrado 66,01%, uma *perda* de 4,2 pontos frente aos 70,24% do solver, e 69,78% não aparece em lugar nenhum.

Ler os textos mostrou o limite de qualquer auditoria por consulta. Todos estes números passaram, e todos estão errados no sentido:

- O coordenador escreveu que um plano "gave up 1.08% of all snapped requests compared to the unconstrained solver plan". O plano *ganhou* 1,08 ponto.
- Outro plano chamou 99,98% de "similarity to the unconstrained solver plan". É a razão de valor.
- O agente de manutenção disse que os 509 pedidos da Rua Joviano Coelho são "5.36% of all snapped requests". 5,36% é a cobertura do plano inteiro do solver; a fatia da rua é 0,27%. A consulta aceitou porque 5,36 está no livro-razão.

Então "todo número é rastreável até uma ferramenta" é alcançável com um modelo de 8B e um prompt rigoroso. "Toda frase está certa" é outra propriedade, e uma consulta não consegue checá-la. A auditoria estruturada, em que o agente preenche campos tipados e o código os recalcula, é a que eu confiaria.

### O veredito

| | Solver + heurística | Agentes LLM (Qwen3-8B) |
|---|---|---|
| Valor capturado | 54,43 / 70,24 / 83,98% | 93,8% a 100% do valor do solver |
| Pedidos cobertos | 5,36 / 10,89 / 21,65% | −0,04 a +1,08 ponto |
| Agenda concluída | 9/9 | 1/9 |
| Atraso do pior mês (o único caso comparável) | 51.731,9 s | 66.627,6 s |
| Mesma resposta ao repetir | sim | sobreposição dos desvios de 0,0 a 0,87 |
| Números rastreáveis às ferramentas | n/a | 89,7% estrito, 98,8% com notação/derivados |

Neste problema o LLM acrescenta **explicação e pequenos deslocamentos na cobertura de pedidos, não planos melhores**. A mochila já otimiza o objetivo declarado, então o agente só pode trocar valor por algum outro objetivo, e faz isso de forma inconsistente. Agendar fica melhor com a heurística: ela terminou todas as vezes, nunca teve uma violação, e o pior mês dela foi menor.

Isso não torna a camada de agentes inútil. Um plano com os prós e contras escritos em linguagem simples é algo que um engenheiro da prefeitura consegue ler e contestar, e os números do coordenador eram rastreáveis. Mas a decisão em si é do solver.

## O que eu diria a um time que vai construir isso

1. **Construa primeiro a linha de base determinística, e faça o agente vencê-la.** Aqui uma mochila gulosa e uma pequena heurística de agendamento puseram uma régua que o LLM não alcançou. Sem elas, os planos do agente pareceriam bons.
2. **Se o "julgamento" do agente é uma preferência, coloque-a na função objetivo.** A única coisa que o agente de manutenção queria sempre, mais cobertura das ruas reclamadas, é um peso no solver: reprodutível, explicável e de graça.
3. **Não faça o modelo digitar ids.** Seis das oito falhas de agendamento foram um id com um zero a mais. Dê ao modelo índices ou nomes de uma lista fechada, resolva-os no código e faça o erro dizer qual id ele provavelmente quis dizer.
4. **Faça as ferramentas rejeitarem entradas impossíveis, e barre chamadas repetidas no código.** Minha ferramenta de agenda pontuou alegremente agendas com obras faltando, e o agente mandou a mesma chamada 8 vezes. Uma instrução para não se repetir não impediu nenhuma das duas coisas.
5. **Uma auditoria de números mostra de onde o número veio, não se a frase que o usa está certa.** Guarde a nota estrita e a tolerante, leia os textos mesmo assim, e leve toda afirmação que importa para campos tipados que o código consiga recalcular.
6. **Pedido de tapa-buraco mede quem reclama, não o pavimento.** Diga isso no plano, e não deixe um modelo tratar "mais reclamações" como "pior via".

---

*Ideia do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (projeto nº 3, agentes sobre o grafo da malha viária). Código, pipeline de dados e todos os números: [github.com/ricardocunha/ensaios › articles/2026-11-road-network-graph-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents). Dados viários © colaboradores do OpenStreetMap (ODbL). Pedidos de tapa-buraco: Prefeitura de Belo Horizonte, BH Digital, CC-BY; as figuras mostram só agregados por trecho, nunca pedidos individuais. Os custos de reparo são sintéticos e os tempos de viagem são de fluxo livre.*
