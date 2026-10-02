<!-- Post LinkedIn (PT-BR), ~1.300 caracteres. -->

As checagens do meu agente passaram. As respostas continuavam erradas.

Construí quatro sistemas de agentes com dados brasileiros (contratos públicos, as cheias de 2024 no RS, as ruas de BH, aerogeradores), cada um com uma checagem determinística sobre a saída do modelo. Todas funcionaram. Todas deixaram passar respostas erradas:

→ Citações conferidas palavra por palavra, usadas para "refutar" justamente a cláusula que violava a regra.
→ 98,8% dos números encontrados nas ferramentas (depois de corrigir bugs da minha auditoria), alguns presos à coisa errada ("aumentou de 54,43% para 48,36%").
→ Todo código de estação no alerta era real; um foi atribuído à cidade errada.
→ Uma justificativa obrigatória, preenchida com comparações falsas pelos próprios números do agente.

Cada checagem provava que algo existe. Nenhuma provava que foi usado corretamente.

O que se sustentou: o código decide, o modelo explica. A fusão bayesiana venceu o LLM no risco de enchente (Brier 0,147 contra 0,195). Uma heurística concluiu 9 de 9 cronogramas; o agente, 1.

Então: cheque significado onde for barato, leia as saídas, leve as decisões para o código e trate checagem aprovada como "escalar menos", não como "correto".

[[LINK]]

#IA #Agentes #LLM #Avaliação #Brasil
