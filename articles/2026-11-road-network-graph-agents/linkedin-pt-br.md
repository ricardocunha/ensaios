<!-- Post LinkedIn (PT-BR), ~1.500 caracteres. -->

Um agente que planeja a manutenção de vias parece ótimo até você montar ao lado dele a linha de base sem graça.

Construí um sobre a malha viária real de Belo Horizonte (OpenStreetMap) e 198.991 pedidos reais de tapa-buraco: ferramentas de grafo em NetworkX, três agentes Pydantic AI e um modelo aberto de 8B no notebook.

O que encontrei:

→ Uma mochila gulosa já fica a 1e-5 do plano ótimo. Toda mudança do agente custou valor (ele manteve de 93,8% a 100%) por no máximo +1,08 ponto de cobertura de pedidos. Isso é um peso na função objetivo, não julgamento.

→ O agente de interdições, que agenda as obras, terminou 1 de 9 execuções. 6 das 8 falhas foram um único id: escreveu "S010128" no lugar de "S10128", recebeu "id desconhecido" de volta e, em 4 dessas 6 execuções, reenviou exatamente a mesma chamada.

→ Uma heurística simples, sem LLM, agendou todas as vezes, sem nenhuma interdição em conflito. A única agenda do agente teve o pior mês 28,8% pior que o da heurística.

→ 98,8% dos números no texto dos agentes vinham de uma ferramenta (89,7% na consulta estrita). Algumas frases em volta continuavam erradas: "abriu mão de 1,08%" para um ganho.

→ Pedido de tapa-buraco mede quem reclama, não o pavimento: 21,0 locais com pedido por km em rua residencial, 0,10 no Anel Rodoviário.

Construa primeiro a linha de base determinística, e faça o agente vencê-la.

Texto completo e código (com todas as falhas): [[LINK]]

#IA #Agentes #LLM #OpenStreetMap #Urbanismo #DadosAbertos #Brasil
