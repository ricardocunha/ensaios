<!-- Post LinkedIn (PT-BR), ~1.300 caracteres. -->

Um agente de compliance que acerta 80% das vezes não serve para nada se você não sabe quais são os 80%.

Construí um para contratos públicos brasileiros (Docling + MCP + Pydantic AI, um modelo aberto de 8B rodando no notebook) e medi quando ele deveria passar o caso para uma pessoa.

O que encontrei:

→ As maiores correções foram nas ferramentas, não no prompt. Uma busca que não ligava "vincula-se" a "vinculação" gerou 10 falsos alarmes; devolver o preâmbulo do contrato na ferramenta corrigiu um erro de foro que instruções não corrigiam.

→ Modelo pequeno não deve fazer conta com limite legal. O modelo extrai os valores; o código aplica a lei. Junto com a correção da busca: falsos alarmes de 34 para 6.

→ A "confiança" do modelo dizia ~0,95 para quase tudo.

→ Nenhum sinal de escalonamento funciona em todo lugar. Em texto limpo, "3 amostras discordam" pega 75% dos erros. Em digitalização ruim o modelo erra de forma consistente (cláusula ilegível = "ausente"), as amostras concordam, e quem denuncia é a nota do OCR.

Combinados: 99,2% de acerto no que o agente decide sozinho em texto limpo, e quase tudo escalado em digitalização ruim — que é o certo.

Texto completo e código (com todos os bugs): [[LINK]]

#IA #Agentes #LLM #Compliance #LicitaçõesPúblicas #Brasil
