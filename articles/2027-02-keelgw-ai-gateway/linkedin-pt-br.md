<!-- Post LinkedIn (PT-BR), ~1.400 caracteres. -->

Treinei um roteador de prompts com US$ 1,88 de API. Ele bateu a meta de 80%. Eis o que esse número deixa de fora.

Estou construindo o keelgw, um gateway de IA para pequenas empresas. No `model: auto` ele classifica cada prompt em 4 faixas, de simple a reasoning. O modelo aberto que eu tinha escolhido, pelas anotações do projeto sobre a licença, não servia para um produto hospedado. Treinei então um classificador pequeno em CPU, em cerca de um dia, com dados sintéticos.

O que vi:

→ Um modelo aberto local escreveu 4.412 prompts, o Claude Haiku 4.5 rotulou todos de novo às cegas, o Claude Opus 5.5 arbitrou as 2.006 divergências. Gasto: US$ 1,88.

→ Os dois primeiros concordaram com confiança em 54,5% dos prompts: 84,2% em "simple", 33,8% em "reasoning". O gerador não soube escrever prompts difíceis sob encomenda.

→ 80,0% de acurácia em 400 prompts sintéticos separados. Mas tomei uma decisão de treino olhando esse conjunto, e a diferença era de uns 3 prompts.

→ Incluir os 1.003 rótulos em que o árbitro ficou em dúvida piorou o classificador.

E a parte honesta: o gateway nunca chamou esse roteador, nada mede economia nem qualidade das respostas, e o projeto só rodou num laptop. Meu pior número de teste de carga, um p99 de 29,4 s, mediu o emulador de AWS.

Rótulos sintéticos compraram um pipeline e uma linha de base, não evidência sobre tráfego real.

Texto completo e código: [[LINK]]

#IA #LLM #MachineLearning #Avaliação #DadosSintéticos #OpenSource
