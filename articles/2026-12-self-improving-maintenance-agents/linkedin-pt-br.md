<!-- Post LinkedIn (PT-BR), ~1.300 caracteres. -->

Agentes "que se aprimoram sozinhos" aprendem com a memória. Testei se isso é verdade num parque eólico real.

Montei um agente de manutenção (Pydantic AI, modelo aberto de 8B rodando localmente) com memória dos alarmes passados e do que o livro de falhas registrou depois, e reproduzi 23 meses de alarmes em ordem: sem memória, com memória, com memória filtrada.

O que encontrei:

→ O agente disse "inspecionar" para os 77 alarmes, com e sem memória. Memória não muda uma decisão que nunca se mexe.

→ Uma rodada de correções, decidida antes de repetir (histórico, custos, justificativa obrigatória): "inspecionar" em 230 de 231 decisões. A memória mudou exatamente uma.

→ Justificativa obrigatória é um campo, não uma checagem. Uma vez justificou a inspeção com leituras "maiores" que, pelos próprios números, não eram.

→ "Sempre inspecionar" não era bobagem: 27 de 77 alarmes vieram antes de uma falha registrada. Com custo de 1 : 10, isso é quase ótimo.

E a parte honesta: 21 incidentes não provam que a memória ajuda nem que atrapalha. É um estudo de caso do mecanismo, não uma curva de aprendizado.

A eólica é 14,1% da eletricidade do Brasil, e 92% dela vem do Nordeste, mas não achei dado público brasileiro com falhas por turbina. É isso que tornaria o teste possível.

Texto completo e código: [[LINK]]

#IA #Agentes #LLM #ManutençãoPreditiva #EnergiaEólica #Brasil
