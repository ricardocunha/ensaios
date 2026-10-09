---
title: "Um agente de risco de desastre que combina sinais em que não pode confiar totalmente"
subtitle: "Reproduzindo hora a hora as cheias de 2024 no Rio Grande do Sul: fusão bayesiana calibrada de réguas de rio e estações de chuva, um LLM que escreve o alerta mas nunca faz a conta, e o que acontece quando as réguas silenciam no pico"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — substituir os [[LINK]] antes de publicar
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent
---

# Um agente de risco de desastre que combina sinais em que não pode confiar totalmente

No fim de abril e em maio de 2024, choveu durante dias sobre o Taquari e os outros rios que deságuam no Guaíba, no Rio Grande do Sul. O Vale do Taquari foi inundado e, dias depois, Porto Alegre também. A Defesa Civil do RS contabiliza 184 mortes e 25 pessoas ainda desaparecidas (última atualização, de abril de 2025); no pico, no boletim de 23 de maio de 2024, eram 581.643 pessoas desalojadas, sem contar as que estavam em abrigos públicos. Muçum, Encantado e Estrela já tinham sido inundadas em setembro e novembro de 2023.

Este artigo não trata do que deveria ter sido feito naqueles dias. Quem estava no terreno trabalhou em condições que nenhum backtest reproduz. A pergunta aqui é mais estreita, técnica, e o evento a torna concreta: **quando pluviômetros, réguas de rio, mapas de satélite e o histórico discordam, e alguns deles param de transmitir, como um agente deve combiná-los num alerta de cheia que ele consiga explicar? E ele teria avisado a tempo?**

Construí um agente assim e reproduzi o evento hora a hora, usando em cada hora só os dados que existiam naquela hora. A ideia vem do vídeo *"5 AI Agents Projects to Build in 2026"* (projeto nº 1, inteligência de desastres com múltiplos sinais). A arquitetura, os dados e a avaliação são meus. Todos os números abaixo vêm do `code/docs/RESULTS.md` do repositório.

## A montagem

![Diagrama do pipeline em quatro etapas. Fontes: a telemetria da ANA (nível do rio e chuva a cada 15 minutos), as estações do INMET (chuva horária) e os mapas de cheia do Copernicus EMS (EMSR720) alimentam um replay que, na hora t, expõe só os dados que existiam até t (store.as_of(t)). Cada estação gera um Signal por hora, com fonte, valor, RV, idade e confiabilidade. Uma fusão bayesiana em Python puro, em log-odds e calibrada em 2019-2022, produz p(cota de inundação em 24 h) e o nível de risco. O estado fundido vai para o agente de alerta (Pydantic AI, Qwen3-8B local), que escreve título e explicação em português, sem campos numéricos. Uma auditoria de citações determinística confere números, estações, lugares, réguas silenciosas e nível.](images/pipeline.pt-br.svg)

- **Escopo:** o Vale do Taquari (Muçum → Encantado → Estrela → Taquari) como caso principal, e a régua do Cais Mauá, em Porto Alegre, no Guaíba, rio abaixo (cota de inundação de 3,00 m, definida pela SEMA-RS, a secretaria estadual que opera a estação): cinco lugares com régua e cota de inundação oficial.
- **Hipótese por lugar e por hora:** *a régua do lugar atinge a cota de inundação oficial nas próximas 24 horas.* É sobre isso que a probabilidade fala, e é contra isso que ela é avaliada.
- **Modelo:** Qwen3-8B 4-bit num servidor mlx-lm local, sem modo de raciocínio. Nenhuma API paga.

## Parte 1: a auditoria dos dados decidiu o escopo

Antes de escrever qualquer agente, verifiquei o que dá para baixar de fato para abril e maio de 2024.

**O que funciona sem cadastro:** a telemetria da ANA (nível do rio e chuva a cada 15 minutos), as estações automáticas do INMET (horárias), os polígonos de inundação já processados do Copernicus Emergency Management Service para a ativação EMSR720 (todos no Vale do Taquari) e os boletins hidrológicos do SACE, do SGB, para o Taquari. Tudo isso é dado público. A ANA permite a reprodução desde que citada a fonte; o INMET diz que seus dados são públicos e de acesso gratuito; não encontrei texto de licença para os boletins do SGB. O repositório cita todas as fontes e não redistribui nenhum dos dados.

**O que está bloqueado:** o histórico de pluviômetros do CEMADEN (um CAPTCHA a cada download) e o histórico de desastres do S2iD (com licença aberta, mas o servidor recusa downloads por script). Deixei os dois de fora em vez de contornar a proteção.

Três descobertas moldaram todo o resto.

**As réguas silenciam no pico.** Numa tabela horária de 14 estações entre 20/04 e 20/05, todas as estações de chuva do INMET transmitiram durante o pico. Três das cinco réguas com cota de inundação não:

| Régua | Dias de pico, 01/05 → 06/05 (144 h): horas sem leitura de nível | Maior silêncio contínuo na janela |
|---|---|---|
| Muçum | 0 | 0 h |
| Encantado | 138 | 105 h |
| Estrela | 42 | 29 h |
| Taquari | 108 | 127 h |
| Porto Alegre, Cais Mauá | 93 | 429 h (até o fim da janela) |

A telemetria nunca registrou o pico da primeira onda em Encantado, que o SGB depois levantou em campo: 23,14 m. O Cais Mauá para às 23h15 (hora local) de 02/05, três dias antes do pico de 5,37 m do Guaíba. Já tinha acontecido antes: o recorde de 26,11 m de Muçum em setembro de 2023 também não está lá, então os máximos históricos *subestimam* as cheias. Qualquer fusão precisa tratar "sem leitura" como um estado com significado próprio, não como zero.

**O satélite chega depois do pico.** Não houve imagem do Sentinel-1 sobre Encantado, no Vale do Taquari, antes de 08/05, e o Sentinel-2 estava encoberto em 01/05. O primeiro mapa de inundação do Copernicus EMS foi entregue às 19h29 UTC de 04/05, 103,5 horas depois de o nível em Estrela chegar à faixa com razão de verossimilhança 10 ou mais. No replay, um mapa só fica visível na hora da *entrega* e serve como rótulo. O satélite pode confirmar esta cheia; não pode avisar dela.

**Existe um relógio oficial para comparar.** O arquivo do SACE lista todos os boletins do Taquari de 2024 com a hora de publicação: 43 entre abril e maio, o primeiro publicado às 7h54 de 30/04 (hora local). Os alertas da Defesa Civil são publicados numa página por aviso, sem um arquivo que eu pudesse consultar, então a outra referência é física: a primeira leitura da ANA igual ou acima da cota de inundação de cada régua. Acertar esses relógios (a ANA usa hora local; o INMET usa UTC e marca a hora pelo fim do intervalo) deu mais trabalho que qualquer modelo.

## Parte 2: sinais, idade da leitura e um replay que não enxerga o futuro

Cada fonte tem um adaptador que transforma suas leituras num `Signal` na hora *t*: o valor, uma **razão de verossimilhança** (RV: quanto mais provável é essa leitura se uma cheia está vindo do que se não está), a idade da leitura e uma **confiabilidade** entre 0 e 1.

O nível do rio cai em faixas tiradas do próprio histórico de cada estação entre 2019 e 2024 (p90, p99, cota de inundação oficial), e a RV dobra se o rio subiu 1 m em 6 horas. A chuva usa os acumulados de 24 h e 72 h. Uma régua silenciosa mantém o último valor real, com uma confiabilidade que cai pela metade a cada 6 horas, e vira um sinal explícito de "ausente" depois de 72 horas. Nada é interpolado.

O replay entrega a cada adaptador `store.as_of(t)` e mais nada. Os testes comparam cada sinal com um conjunto de dados *cortado* naquele passo e injetam um pico no futuro para verificar que nada anterior muda. Um backtest que enxerga o futuro tornaria inúteis todos os números deste texto.

## Parte 3: fusão bayesiana calibrada, e a antecedência que ela consegue

A fusão são poucas linhas de Python puro. Por lugar e por hora:

```
log_odds = logit(prior) + Σ  w_i · r_i · ln RV_i          p = sigmoid(log_odds)
```

A probabilidade a priori é a fração das horas de 2019 a 2022 em que a régua atingiu a cota de inundação nas 24 horas seguintes: de 0,01% a 1,3%. `r_i` é a confiabilidade, já com o decaimento pela idade da leitura. Os pesos foram fixados antes: 1 para a régua do próprio lugar, 0,5 por régua a montante e 1 para o grupo inteiro de chuva, dividido entre as estações, porque estações de chuva na mesma tempestade não são testemunhas independentes. Os níveis também foram fixados antes do backtest: atenção a partir de 0,10, alerta a partir de 0,50, emergência a partir de 0,90.

**As razões de verossimilhança que escolhi à mão não funcionaram.** Com probabilidades a priori tão pequenas, os números redondos que eu tinha escolhido (rio no p99 = 4, na cota de inundação = 10) nunca colocaram Muçum, Encantado, Taquari ou Porto Alegre em alerta em 2024. Estrela chegou lá 45 minutos *depois* de o rio passar da cota. Então mantive a definição de cada faixa e ajustei sua RV só com 2019–2022: a fração de horas de cheia naquela faixa dividida pela fração de horas sem cheia. Os dados discordaram da minha intuição por uma ordem de grandeza. Uma régua acima do p90 que subiu um metro em seis horas vale cerca de 32, não 3. Até "chuva, mas abaixo de todas as faixas" acabou sendo evidência *a favor* de cheia (2,5–2,8), porque cheias vêm depois de semanas úmidas.

Com a tabela calibrada, este é o primeiro alerta em cada lugar em 2024, comparado com a primeira leitura na cota de inundação:

| Lugar | Cota de inundação atingida (local) | Alerta da fusão | Antecedência | RVs escolhidas à mão |
|---|---|---|---|---|
| Muçum | 01/05 12h45 | 30/04 11h00 | **+25,75 h** | nunca em alerta |
| Encantado | 30/04 14h15 | 29/04 21h00 | **+17,25 h** | nunca |
| Estrela | 30/04 08h15 | 29/04 20h00 | **+12,25 h** | −0,75 h |
| Taquari | 01/05 04h15 | 30/04 08h00 | **+20,25 h** | nunca |
| Porto Alegre | 02/05 13h15 | 02/05 06h00 | **+7,25 h** | nunca |

Diante dos boletins oficiais, a comparação justa é com o primeiro boletim do SACE, um aviso para a bacia inteira publicado às 7h54 de 30/04. A fusão colocou Encantado e Estrela em alerta 10,9 e 11,9 horas antes dele. Muçum e Taquari ficaram a cerca de 3 horas dele: o boletim saiu 3,1 h antes do alerta de Muçum e 0,1 h antes do de Taquari. Quero ser cuidadoso aqui. O SGB emitiu um boletim de previsão para uma bacia inteira; minha fusão dá uma probabilidade para uma régua, num replay, com uma tabela ajustada em anos anteriores. Isso mostra que os sinais estavam lá, não que alguém deixou de vê-los.

**Cheias anteriores.** De 2019 a abril de 2024, a fusão calibrada alertou antes de 20 dos 22 inícios de cheia, incluindo todos os 10 nas réguas do Taquari no período fora da amostra (2023 a abril de 2024), e 1 dos 2 inícios fora da amostra no Cais Mauá (os inícios de 2019–2022 estão dentro da amostra da tabela ajustada). Em novembro de 2023, porém, o SACE foi mais rápido em Muçum (por 11 h) e em Taquari (por 18 h). A tabela escolhida à mão alertou antes de 4 dos 22.

## Parte 4: falsos alarmes, calibração e ablações

Alertas cedo têm um preço. No período fora da amostra (2023-01 → 2024-04, 6,50 lugar-anos), a fusão calibrada gerou **21 falsos alarmes, 3,23 por lugar-ano**. As regras à mão não geraram nenhum, porque quase nunca alertam. Os falsos alarmes foram quase-cheias: durante eles, o rio chegou a 0,39–0,96 da cota de inundação, com mediana de 0,77. E 2023 foi um ano excepcionalmente úmido no vale.

**Calibração:** Brier score de 0,0074 fora da amostra (skill de 0,44 sobre a climatologia) e 0,1148 em 2024 (skill de 0,66). Fora da amostra, a fusão é confiante demais entre 0,5 e 0,9 (horas com 0,60 tiveram cheia 29% das vezes; o naive Bayes ainda conta duas vezes evidências correlacionadas). Em 2024 ela foi confiante de menos abaixo de 0,9: o evento foi maior que qualquer coisa nos anos de treino.

**Ablações** (antecedência em 2024, em horas antes de a cota ser atingida, arredondada para a hora exceto no modelo completo; falsos alarmes e Brier fora da amostra):

| Configuração | Muçum | Encantado | Estrela | Taquari | Porto Alegre | Falsos alarmes (por lugar-ano) | Brier, fora da amostra | Brier, 2024 |
|---|---|---|---|---|---|---|---|---|
| completa | +25,75 | +17,25 | +12,25 | +20,25 | +7,25 | 21 (3,23) | 0,0074 | 0,1148 |
| sem nível de rio (só chuva) | perdeu | perdeu | perdeu | perdeu | perdeu | 0 | 0,0124 | 0,3104 |
| sem réguas a montante | +26 | +7 | +13 | −1 | −1 | 7 (1,08) | 0,0078 | 0,1609 |
| sem chuva do INMET | −0 | +17 | +12 | +19 | −1 | 8 (1,23) | 0,0073 | 0,1429 |
| sem decaimento por idade | +26 | +17 | +12 | +20 | +7 | 20 (3,08) | **0,0062** | **0,0927** |
| pesos iguais (naive Bayes puro) | +41 | +19 | +14 | +33 | +58 | 51 (7,84) | 0,0385 | 0,1343 |

O nível do rio sustenta o sistema: só com chuva, nada chegou a alerta. As réguas a montante compram a antecedência em Taquari e em Porto Alegre, e causam 14 dos 21 falsos alarmes. Pesos iguais alertam mais cedo, com 2,4 vezes mais falsos alarmes.

**O resultado que eu não esperava: o decaimento por idade piorou as coisas.** Tirá-lo melhorou o Brier em 2024 (0,0927 contra 0,1148) e fora da amostra (0,0062 contra 0,0074), sem mudar nenhuma antecedência. Quando uma régua silencia numa cheia, o rio em geral continua alto; às vezes ela silenciou *porque* o rio estava alto. Descontar a última leitura joga fora evidência verdadeira. Silêncio não é desconhecimento. Continuo nomeando as réguas silenciosas em todo alerta; só não acho mais que uma meia-vida fixa represente o que o silêncio significa.

## Parte 5: o LLM escreve, nunca calcula

O agente de alerta é um agente Pydantic AI com saída tipada: `headline`, `explanation`, `drivers`, `silent_gauges`. Ele recebe o estado da fusão como texto, incluindo o efeito de cada sinal em log-odds e "a probabilidade sem ele". **Ele não tem campo para a probabilidade nem para o nível**: o alerta final copia os dois da fusão, então o modelo não consegue arredondar 88,8% para 90% e transformar um alerta numa emergência.

Os alertas são escritos em português, porque quem os leria trabalha na Defesa Civil. A entrada também está em português, com vírgula decimal ("efeito +4,52; sem ele 19,1%"), para o modelo copiar cada número no formato em que vai escrevê-lo.

Depois, uma **auditoria de citações determinística** confere o texto: todo número, código de estação e lugar precisa aparecer na entrada, toda régua silenciosa precisa ser nomeada, e qualquer nível de risco declarado precisa ser o da fusão. Em português, isso significa ler "3,66 m" e "3.66 m" como o mesmo número, "1.355 cm" como um possível milhar e "risco de emergência" como um nível.

Rodei o agente em 9 horas-chave (o primeiro alerta de cada lugar e a primeira hora em atenção ou acima com a régua do próprio lugar silenciosa), em três modos, primeiro com instruções em inglês e depois em português:

| Modo | Auditoria aprovada, inglês | Auditoria aprovada, português | Chamadas ao modelo (EN / PT) |
|---|---|---|---|
| saída por ferramenta | 9 / 9 | 9 / 9 | 9 / 9 |
| saída por ferramenta + nova tentativa se a auditoria falhar | 9 / 9 | 9 / 9 | 10 / 9 |
| saída em texto (JSON na resposta) | 7 / 9 | 9 / 9 | 9 / 9 |

Em inglês, as duas falhas do modo com JSON na resposta foram do mesmo tipo: uma régua silenciosa listada no campo `silent_gauges`, mas nunca mencionada no texto, justamente nas duas horas com duas ou três réguas silenciosas. Em português, as duas horas passaram. É uma execução por hora, com temperatura 0 e uma entrada com outra redação, então não leio isso como "em português é mais confiável". Mostra que o agente e a auditoria funcionam no idioma em que o alerta seria de fato lido.

Este é o alerta de Porto Alegre às 3h (hora local) de 03/05, probabilidade combinada de 95,6%, no modo com JSON na resposta, exatamente como foi gerado:

> **Porto Alegre: EMERGÊNCIA com 95,6% de probabilidade**
> A probabilidade combinada de 95,6% foi calculada com base no nível do rio em Porto Alegre (87450004) com efeito +4,52, que sem ele seria 19,1%. O nível do rio em Guaíba (87242000) contribuiu com efeito +2,12, reduzindo para 72,5% sem ele. Chuvas em Canela (A879) e Porto Alegre (A801) também elevaram a probabilidade. A régua 87450020 em Porto Alegre está silenciosa há 72 h e não contribuiu. Réguas 86950000 e 87450004 também estão desatualizadas e com menor peso.

É a frase que a versão em inglês deixou de fora nesta hora: a régua de Taquari (86950000), na foz do Taquari, que diz a Porto Alegre o que vem rio abaixo, estava silenciosa havia 18,2 horas. Aqui ela aparece.

O texto do modo por ferramenta, na mesma hora, também passou, e está errado de um jeito que a auditoria não vê. Ele diz: "As réguas silenciosas 87450020 e 86950000 não foram usadas devido à ausência de leituras recentes". Mas a 86950000 *foi* usada, com confiabilidade 0,12, e a régua da própria cidade, 87450004, só aparece como o sinal principal, nunca como silenciosa. Passa porque um código de estação em qualquer lugar do texto conta como menção.

Então, três limites. A auditoria confere *fundamentação*, não *pareamento* nem sentido. Em português, o modo por ferramenta atribuiu o código da régua de Estrela a Encantado e chamou duas réguas de rio silenciosas de "estações de chuva" (o mesmo texto nas duas execuções por ferramenta), e um texto do modo com JSON na resposta chamou dois níveis de rio a montante de "leituras de chuva". Nada disso é número, código ou lugar inventado. Uma checagem de pareamento por script pega o código atribuído ao lugar errado (2 de 27 textos em português, 0 de 27 em inglês); o resto exigiu leitura. Segundo, a auditoria precisa falar a língua do modelo: um leitor de números só em inglês leria o "1.355 cm" de um brasileiro como 1,355. Terceiro, a auditoria é tão boa quanto a entrada. Lendo os textos em inglês, descobri que, numa hora, minha lista de réguas silenciosas mostrava o acumulado de *chuva* de 24 horas de Encantado como a "última leitura", porque a ANA usa o mesmo código para chuva e nível. Nenhuma auditoria contra a mesma entrada pega isso. Está corrigido, com teste; depois da correção, aquela hora passou nos três modos, nos dois idiomas.

## Parte 6: e se o LLM fizesse a fusão?

Talvez um modelo de 8B simplesmente seja bom nisso. Então dei ao Qwen3-8B o mesmo retrato por hora que a fusão vê (valor, idade, RV calibrada e confiabilidade de cada sinal, os limiares das réguas, as réguas silenciosas, a probabilidade a priori), mas não a probabilidade combinada, e pedi uma probabilidade e um nível. Um prompt fixo para todas as horas, nada ajustado pelos resultados. As horas foram fixadas antes da primeira chamada: a cada 3 horas, de 48 h antes a 12 h depois do cruzamento da cota em 2024 em cada lugar (105), os inícios dos 21 falsos alarmes da fusão fora da amostra e 21 horas calmas sorteadas, pareadas por lugar. Três amostras de cada, com temperatura 0,7: 441 chamadas, 0 erros.

**Antecedência** em relação à cota atingida (primeira hora em alerta ou acima, na grade de 3 horas, por isso a antecedência da fusão difere um pouco da Parte 3):

| Lugar | Fusão bayesiana | LLM (as 3 amostras concordam) |
|---|---|---|
| Muçum | +24,75 h | +39,75 h |
| Encantado | +15,25 h | +18,25 h |
| Estrela | +12,25 h | +12,25 h |
| Taquari | +15,25 h | +30,25 h |
| Porto Alegre | +6,25 h | +48,25 h (já em alerta na primeira hora da grade) |

Só por essa tabela, o LLM ganha. A vitória não sobrevive à próxima. A pergunta era "cota de inundação em 24 horas", e entre as 45 horas do evento em que a resposta era não, o LLM disse alerta ou emergência 15–16 vezes por amostra; a fusão, uma vez. Em Porto Alegre ele estava em alerta 48 horas antes, com a régua da própria cidade abaixo do p90. Olhando para trás, parece presciência. Diante da pergunta que foi feita, estava errado.

| | Fusão bayesiana | LLM (por amostra) |
|---|---|---|
| Horas do evento sem cheia em 24 h (45): em alerta ou acima | 1 | 16 / 16 / 15 |
| Horas de falso alarme da fusão (21): em alerta ou acima | 21 | 17 / 17 / 16 |
| Horas calmas sorteadas (21): em alerta ou acima | 0 | 0 / 0 / 0 |
| Brier score, todas as 144 horas rotuladas | **0,1469** | 0,1979 / 0,1964 / 0,1938 |

As mesmas quase-cheias enganam os dois; os dois ficam calmos nas horas de fato calmas. Mas o LLM é pior calibrado: 0,85, 0,92, 0,82 e 0,02 respondem por 299 das 441 respostas, e ele nunca passou de 0,98, nem com o rio acima da cota. Ele se comporta como um classificador com alguns rótulos de confiança.

**A consistência** foi melhor do que eu esperava: dispersão mediana de 0,03 entre as amostras, e a decisão de alertar mudou em só 2 de 147 horas. Mas o nível declarado mudou em 34 horas, a pior dispersão foi de 0,63 (0,85, 0,42 e 0,22), e em 4 respostas o nível não batia com a própria probabilidade do modelo.

Então a comparação sustenta a divisão de trabalho. O modelo lê a evidência mais ou menos na direção certa, mas não consegue sustentar um número calibrado nem um horizonte fixo. A fusão faz as duas coisas, em código que pode ser testado e submetido a ablações.

## O que eu diria a um time que vai construir isso

1. **Audite os dados antes de desenhar o agente.** O escopo, o papel do satélite e a pergunta mais difícil do projeto (o que significa uma régua silenciosa) saíram de baixar os dados e conferir seus relógios, não da arquitetura.
2. **Calibre as razões de verossimilhança no histórico.** Meus números redondos intuitivos erraram por uma ordem de grandeza e perderam quatro de cinco lugares. Ajuste em anos que você depois deixa de fora, e meça o preço em falsos alarmes.
3. **Silêncio é informação.** As réguas falharam justamente nos picos. Informe as réguas silenciosas em todo alerta e teste o que a sua fusão faz com elas. Meu decaimento por idade, o desenho óbvio, piorou a calibração.
4. **Deixe o LLM escrever, não calcular.** Mantenha a probabilidade fora do esquema de saída dele e confira, em código, o que ele escreve contra o que ele recebeu, no idioma e no formato de número em que ele escreve.
5. **Compare com o relógio oficial, com humildade.** Um replay com uma tabela ajustada não é um serviço de previsão. Ele pode mostrar que os sinais estavam lá; não pode mostrar que alguém deveria ter agido antes.

---

*Ideia do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (projeto nº 1). Código, pipeline de dados e todos os números: [github.com/ricardocunha/ensaios › articles/2026-11-disaster-risk-agent](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent). Dados da ANA, do INMET, do SGB e do Copernicus Emergency Management Service; o repositório não os redistribui. Isto é um backtest de pesquisa, não um sistema de alerta: numa emergência, siga a Defesa Civil.*
