<!-- Post LinkedIn (PT-BR), ~1.400 caracteres. -->

Meu RAG de exames de olho citava as fontes. Aí embaralhei os rótulos.

Montei um RAG médico multimodal num laptop: um modelo de visão local (Qwen3-VL-8B) olha uma foto de retina ao lado dos 3 casos rotulados mais parecidos de um acervo (BiomedCLIP + Qdrant), dá o diagnóstico e cita os casos. 609 imagens de teste de um dataset público (RFMiD).

O que encontrei:

→ A recuperação levou o macro-F1 do modelo de 0,058 para 0,298. A votação simples entre vizinhos, nos mesmos embeddings, deu 0,341, em milissegundos.

→ Mesmas fotos recuperadas, rótulos trocados por errados: 0,056. Todo o ganho sumiu. Ele vinha de ler os rótulos, não de comparar as fotos.

→ Um agente de explicação com checagem de citações em código: 90% das explicações aprovadas com rótulos verdadeiros, 89% com embaralhados. A checagem confere se a citação bate com o texto mostrado. Não tem como saber que o texto está errado.

→ Mesmo com os rótulos verdadeiros, só 49% das citações aprovadas apontavam um rótulo que a imagem tinha de fato (12% com rótulos embaralhados).

Se o seu RAG "se explica", rode um teste com rótulos embaralhados. É uma rodada a mais.

O Brasil tem um ótimo dataset para isso, o BRSET (16 mil fotos, São Paulo), com acesso credenciado. O arcabouço de avaliação foi feito para que quem tem acesso possa rodá-lo de novo.

Um dataset, um modelo: demonstração de pesquisa, não um dispositivo médico.

Texto completo e código: [[LINK]]

#IA #RAG #IAnaSaúde #Oftalmologia #LLM #Avaliação #Brasil
