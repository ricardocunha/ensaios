<!-- Post LinkedIn (PT-BR), ~1.300 caracteres. -->

Em maio de 2024, três das cinco réguas de rio de que eu precisava silenciaram no pico das cheias do Rio Grande do Sul.

Reproduzi o evento hora a hora com um agente de risco de desastre (fusão bayesiana de réguas e estações de chuva, um modelo aberto de 8B no notebook) para ver se ele teria avisado a tempo, e o que faz quando os sinais param de chegar.

O que encontrei:

→ As razões de verossimilhança que escolhi à mão erraram por uma ordem de grandeza e nunca puseram 4 de 5 lugares em alerta. Ajustada em 2019–2022, a fusão alertou de 7 a 26 horas antes de cada rio atingir a cota de inundação, ao custo de 3,23 falsos alarmes por lugar-ano.

→ Silêncio não é desconhecimento. Descontar a última leitura de uma régua silenciosa piorou a calibração: o rio em geral continua alto.

→ O LLM escreve, não calcula. O agente escreve o alerta em português, não tem campo para a probabilidade, e uma auditoria determinística confere cada número, código e régua silenciosa. 27 de 27 passaram. Lendo, ainda achei um código atribuído à cidade errada.

→ Fazendo a fusão sozinho, o LLM alertou antes, quase sempre em horas sem cheia nas 24 h seguintes.

É um replay, não um sistema de alerta: mostra que os sinais estavam lá, não que alguém deixou de vê-los.

Texto completo e código: [[LINK]]

#IA #Agentes #LLM #Enchentes #DefesaCivil #Brasil
