---
title: "As checagens do meu agente passaram. As respostas continuavam erradas."
subtitle: "Quatro projetos de agentes, uma lição: checar que algo existe não é checar que está certo"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — substituir os [[LINK]] antes de publicar
---

# As checagens do meu agente passaram. As respostas continuavam erradas.

Em três meses construí quatro sistemas de agentes a partir do mesmo vídeo, *"5 AI Agents Projects to Build in 2026"*, todos com dados brasileiros e todos com um modelo aberto de 8B rodando no notebook:

- um **revisor de compliance** para contratos públicos ([artigo](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents));
- um **agente de risco de enchente** reproduzindo as cheias de 2024 no Rio Grande do Sul ([artigo](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent));
- **planejadores de manutenção viária** sobre a malha de Belo Horizonte ([artigo](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents));
- um **agente de manutenção de aerogeradores com memória** ([artigo](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents)).

Todos ganharam uma checagem determinística sobre a saída do modelo, porque eu não confiava no modelo. Todas essas checagens funcionaram como projetado. E todas deixaram passar respostas erradas, pelo mesmo motivo.

## O padrão: a checagem provava existência, não correção

**Compliance: citações reais, argumento errado.** O revisor precisava citar a evidência, e o código conferia que a citação estava literalmente no contrato. Um agente auditor tentava refutar cada violação apontada, e sua objeção só contava com uma contracitação literal. Em texto limpo, o auditor pegou todos os falsos alarmes. Também contestou um terço das violações *reais* (19 de 59), com citações que existem no contrato e não provam nada. Ele "refutou" uma vigência que estourava o limite de 5 anos citando a própria vigência: "72 (setenta e dois) meses". A citação era real. O argumento, não.

**Planejamento viário: números reais, significado errado.** Cada número no texto dos planejadores era procurado entre os números que as ferramentas tinham devolvido. Depois de corrigir bugs da minha própria auditoria, 98,8% foram encontrados. Ler os textos mostrou o que "encontrado" quer dizer: as 509 solicitações de uma rua descritas como "5,36% de todas as solicitações" (5,36% era a cobertura do plano inteiro; a fatia real da rua era 0,27%), um valor que "aumentou de 54,43% para 48,36%", um ganho descrito como perda. Cada número existia na saída de alguma ferramenta. Estavam presos às coisas erradas.

**Alertas de enchente: réguas reais, lugares errados.** O agente de alerta escreve o texto; o código confere que todo número, código de estação e régua silenciosa mencionados estão na entrada. Em português, os 27 textos passaram. Um deles dizia: "As estações de chuva em Encantado (86879300) e Encantado (86720000) estão desatualizadas". 86879300 é a régua de Estrela, não de Encantado, e as duas são réguas *de rio* silenciosas, não estações de chuva. Todos os códigos da frase estão na entrada.

**Memória de manutenção: campo preenchido, motivo falso.** Para o agente parar de mandar inspecionar todo alarme, exigi que ele justificasse a inspeção sempre que alarmes parecidos no passado não tivessem dado em nada, num campo obrigatório. Ele preencheu o campo. Num episódio, escreveu que o alarme era diferente por ter "uma nota do detector maior (2,9) que a dos alarmes anteriores (2,6 e 2,9)" e um resíduo de "+3,1 contra +3,3 e +3,8". As duas comparações são falsas pelos próprios números dele. O validador conferia que o campo não estava vazio.

Quatro domínios, uma falha: **cada checagem confirmava que algo existe (uma citação, um número, um código, uma justificativa) e não dizia nada sobre se foi usado corretamente.** Essas checagens continuam valendo a pena: pegam citações, números e estações inventados. Mas passar nelas é um piso, não um veredito.

## O que se sustentou: o código decide, o modelo explica

O segundo padrão é o outro lado da moeda. Nos quatro projetos, as decisões que se sustentaram foram tomadas por código comum, e o modelo foi mais útil explicando-as.

| Projeto | Decidido por código | Decidido pelo modelo |
|---|---|---|
| Compliance | Limites legais aplicados em código: falsos alarmes nessas duas regras caíram de 23 em 40 constatações para 2 | O modelo de 8B citou "12 (doze) meses" corretamente e disse que isso passa de "5 anos" |
| Risco de enchente | Fusão bayesiana: Brier 0,147; alerta sem cheia em 24 h em 1 de 45 horas | LLM com os mesmos sinais: Brier 0,195; alerta em 15–16 dessas 45 horas |
| Planejamento viário | Cronograma heurístico: concluído 9 de 9, sem interdições conflitantes | Agente de cronograma: concluído 1 de 9; nesse, o pior mês ficou 28,8% pior |
| Manutenção | — | O agente disse "inspecionar" em 230 de 231 execuções, com ou sem memória |

A linha da manutenção pede cuidado. 27 de 77 alarmes foram seguidos de uma falha real, então, com a razão de custos que assumi, "inspecionar tudo" fica perto da resposta certa. O ponto não é que o modelo errou ali; é que ele nunca *mudou de ideia*, e a memória que construí não teve sobre o que agir.

## O que eu faria diferente desde o começo

1. **Cheque significado, não só existência, onde for barato.** Junte cada número à coisa que ele descreve e cheque o par; confira se o código da estação pertence ao lugar citado ao lado; confira se a comparação de uma "justificativa" é verdadeira. No projeto de enchentes, uma checagem de pares código–lugar sinalizou 2 dos 27 textos que a checagem de existência tinha aprovado.
2. **Leia as saídas.** Cada falha acima foi encontrada lendo textos que tinham passado. Uma amostra lida por uma pessoa faz parte da avaliação, não é um luxo.
3. **Leve as decisões para o código antes de ajustar prompts.** Limites, cronogramas, probabilidades: se dá para calcular, calcule, e dê ao modelo o resultado para explicar.
4. **Trate uma checagem aprovada como "escalar menos", não como "correto".** No projeto de compliance, as checagens decidem o que vai para uma pessoa; nunca aprovam nada sozinhas.

Nada disso é motivo para não usar agentes. Cada projeto terminou com algo útil: um revisor que sabe quando passar um contrato para uma pessoa, textos de alerta que citam suas evidências, planos com os trade-offs escritos. É motivo para ser preciso sobre o que cada checagem prova.

---

*Os quatro projetos, com código, pipelines de dados e todos os números: [github.com/ricardocunha/ensaios](https://github.com/ricardocunha/ensaios). Os projetos vêm do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System".*
