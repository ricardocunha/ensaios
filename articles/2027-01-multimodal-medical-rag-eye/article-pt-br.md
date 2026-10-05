---
title: "Meu RAG de exames de olho citava as fontes. Estava lendo os rótulos."
subtitle: "Um modelo de visão local com casos de retina recuperados num dataset público: o que a recuperação acrescentou, um teste com rótulos embaralhados que tirou tudo isso, e por que uma checagem de citações não percebeu a diferença"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — números finais (code/docs/RESULTS.md), dados do dataset em code/docs/DATA.md
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-multimodal-medical-rag-eye
---

# Meu RAG de exames de olho citava as fontes. Estava lendo os rótulos.

> **Demonstração de pesquisa, não um dispositivo médico.** Nada aqui diagnostica ninguém nem apoia decisão clínica. Todos os números abaixo medem concordância com os rótulos de um dataset público, não acurácia diagnóstica em pacientes.

A promessa do RAG médico multimodal é assim. Um modelo de visão e linguagem olha uma foto de retina. Ao lado dela, você coloca as fotos mais parecidas de um acervo rotulado, cada uma com seus achados. O modelo diagnostica a foto nova, cita os casos do acervo em que se apoiou, e a resposta passa a ser "fundamentada" e "explicável": um médico pode conferir os casos citados.

Eu queria saber se isso se sustenta, e como dá para saber. Então montei um sistema assim, inteiro num laptop, sobre um dataset público de 3.200 fotos de retina, e comparei com duas coisas mais simples: o mesmo modelo sem casos recuperados e uma votação simples entre vizinhos mais próximos nos embeddings das imagens. Depois rodei o teste que, na minha opinião, todo sistema com recuperação e explicações deveria rodar: manter as fotos recuperadas, trocar os rótulos delas por rótulos errados e ver o que o modelo faz. A ideia é o projeto nº 2 do vídeo *"5 AI Agents Projects to Build in 2026"*; a arquitetura, o código e os números são meus.

Em resumo:

- **A recuperação ajudou muito o modelo**: o macro-F1 nas 16 condições frequentes foi de 0,058 para 0,298.
- **Mesmo assim, não superou a votação entre vizinhos sobre a qual foi construído** (0,341), e levou 7,5 s por imagem em vez de uma consulta a um índice vetorial.
- **Com os rótulos embaralhados, todo o ganho sumiu** (0,056, indistinguível de não recuperar nada). O ganho vinha de ler os rótulos ao lado das fotos, não de comparar as fotos.
- **Um agente de explicação com checagem de citações aprovou 90% das explicações com os rótulos verdadeiros e 89% com os embaralhados.** A checagem verificou que as citações batiam com o texto mostrado ao modelo. Não tinha como saber se esse texto era verdadeiro.

Todos os números vêm do `docs/RESULTS.md` do repositório; os dados do dataset e as licenças estão em `docs/DATA.md`.

## Por que isso importa no Brasil

O Brasil tem um dataset oftalmológico bem documentado: o **BRSET**, Brazilian Multilabel Ophthalmological Dataset (Nakayama et al., *PLOS Digital Health*, 2024). São 16.266 fotos de fundo de olho de 8.524 pacientes de três centros de oftalmologia de São Paulo, de 2010 a 2020, com rótulos de várias doenças, campos de qualidade da imagem e dados demográficos. É cinco vezes o número de imagens do dataset que usei, de pacientes brasileiros, com rótulos de qualidade que permitiriam testar se a recuperação falha em fotos ruins.

Não usei. O BRSET é "aberto" no sentido do PhysioNet: acesso **credenciado**, o que significa criar conta, fazer um curso de ética em pesquisa (CITI) e assinar um termo de uso de dados. É uma proteção razoável para dados de pacientes. Também é uma barreira real para quem quer refazer um artigo numa tarde, e este projeto não cria contas em lugar nenhum. Por isso o pipeline roda num dataset público sem cadastro, e foi feito para que qualquer pessoa com acesso troque o índice pelo BRSET. O termo do BRSET pede que quem publica resultados publique também o código; este repositório já faz isso.

O recado para uma equipe brasileira é o mesmo do fim deste texto: seja qual for o dataset, a avaliação abaixo é barata de rodar, e é ela que diz se "explicável" significa alguma coisa.

## A montagem

```
foto de fundo de olho ─► embedding de imagem BiomedCLIP ─► Qdrant (local): vetores densos da imagem + texto esparso do "laudo"
                                                  │  busca híbrida, Reciprocal Rank Fusion
                                                  ▼
                          3 casos de treino mais parecidos (foto + achados registrados)
                                                  │
           foto consultada + 3 casos ─► Qwen3-VL-8B (4 bits, local, mlx-vlm) ─► Diagnosis{labels, cited_cases}
                                                  │
                     agente de explicação: por rótulo, origem = image | cases | both, casos citados
                                                  │
                     checagem de citações (código, sem modelo): os casos citados existem e têm o rótulo
```

Tudo roda localmente num M4 Pro: BiomedCLIP para os embeddings, Qdrant em modo local e o Qwen3-VL-8B-Instruct numa versão MLX de 4 bits. O modelo responde em JSON tipado (Pydantic): rótulos da lista fixa de 45 códigos de condição do RFMiD, ou "normal", e mais nada. Uma resposta inválida volta com o erro de validação, até duas novas tentativas. Nas 1.218 chamadas de diagnóstico das rodadas zero-shot e com recuperação, todas as respostas terminaram válidas (uma precisou de nova tentativa).

## Os dados, e o que precisei consertar antes de confiar neles

**RFMiD 1.0** (Pachade et al., 2021): 3.200 fotos coloridas de fundo de olho, de três câmeras, na Índia, rotuladas por dois retinólogos seniores com 45 condições mais "qualquer doença", com divisão oficial de 1.920 / 640 / 640. A licença é CC BY 4.0, e um espelho fixado no Hugging Face baixa tudo sem conta. Os rótulos são múltiplos por imagem e de cauda longa: 16 condições têm pelo menos 20 imagens de treino, e 29 das 45 têm menos. Por isso a métrica principal é o macro-F1 sobre essas 16 condições frequentes, cada uma com o mesmo peso.

**Duplicatas.** Montando as linhas de base, notei duas imagens de teste com uma foto de treino quase idêntica do mesmo olho, mas com rótulo *diferente*. Então verifiquei todos os pares das 3.200 imagens, 5,1 milhões de pares. A similaridade de embeddings não resolvia: 1.587 pares têm cosseno ≥ 0,99, e só 8 deles passam no casamento do desenho dos vasos descrito abaixo. Hash perceptual também não. O que funcionou foi casar geometricamente o desenho dos vasos da retina (pontos SIFT, pareamento um a um, uma transformação RANSAC que precisa parecer uma nova foto do mesmo olho), com limiares definidos olhando os pares lado a lado.

Apareceram 154 pares do mesmo olho entre 263 imagens, 70 deles entre divisões diferentes. **31 imagens de teste** têm o mesmo olho numa divisão anterior. Dos três braços em diante, todos os números as deixam de fora, o que deixa 609 imagens de teste; a tabela de linhas de base abaixo usa as 640.

Vieram duas surpresas. Tirar essas imagens quase não mexeu na linha de base dos vizinhos (0,339 → 0,341): o BiomedCLIP raramente recupera o mesmo olho, porque um embedding global não se guia pelo desenho dos vasos. E **os rótulos discordam de si mesmos**: 83 dos 154 pares do mesmo olho (54%) têm conjuntos de rótulos diferentes. Parte disso é legítima, já que outro enquadramento pode mostrar outro achado. Mas, entre os 8 pares de fotos quase idênticas, 7 têm rótulos diferentes. Isso limita a nota que qualquer método consegue tirar quando avaliado com esses rótulos.

## Linhas de base: uma consulta vetorial é difícil de bater

Antes de qualquer modelo de visão e linguagem, duas linhas de base sobre os mesmos embeddings:

| Método (teste, 640 imagens) | macro-F1, 16 frequentes |
|---|---|
| prever todos os rótulos (piso) | 0,108 |
| BiomedCLIP zero-shot (prompts de texto) | 0,141 |
| **votação kNN**: fração, ponderada pela similaridade, das 20 imagens de treino mais próximas com o rótulo ≥ 0,20 | **0,339** |

O k e o limiar foram escolhidos na divisão de validação. Metade dos 10 vizinhos mais próximos compartilha um rótulo com a consulta, contra 15% ao acaso. O kNN vai bem em condições com aparência geral marcante (miopia, edema de disco óptico, opacidade de meios, oclusões venosas: F1 de 0,58 a 0,68) e mal em achados pequenos que um embedding global de 224 pixels não enxerga (drusas, cicatrizes de laser, palidez de disco: 0,00 a 0,23).

Esse 0,339 (0,341 sem as duplicatas) é o número que o sistema de RAG precisa superar.

## Busca híbrida, com um lado de texto que é só rótulo

O "R" deste RAG deveria trazer casos *com seus laudos*. O RFMiD não tem laudos, só rótulos. Então cada imagem de treino ganha um "laudo" determinístico montado a partir dos rótulos e de uma descrição fixa por condição, por exemplo "diabetic retinopathy (DR): microaneurysms, dot and blot hemorrhages and hard exudates." Ele não contém nada além dos rótulos.

O índice do Qdrant guarda as duas coisas: um vetor denso da imagem e um vetor esparso (saco de palavras) do laudo, combinados por Reciprocal Rank Fusion. O problema está no lado da consulta. Uma foto nova não tem rótulos, então o texto dela precisa vir de algo disponível na hora do teste. Testei duas fontes:

- **Os rótulos da votação kNN**: a busca híbrida passa a reordenar na direção dos casos que concordam com os vizinhos densos. Nas imagens de teste, a precisão de rótulo em 3 (média sobre as 16 condições frequentes) foi de 0,277 (só denso) para 0,329. Escolhi essa configuração para o sistema, na validação.
- **Os próprios rótulos zero-shot do modelo de visão**: pior que só denso (0,243). O modelo chamou 60% das imagens de teste de "opacidade de meios" (366 de 609, contra 103 de verdade), e o lado de texto obedientemente trouxe casos com opacidade.

A busca híbrida só é tão boa quanto o texto que você pode, honestamente, colocar na consulta.

## Três braços: a recuperação ajuda o modelo, e mesmo assim perde

O modelo vê as três fotos recuperadas, cada uma seguida dos achados registrados, e depois a foto consultada. São as mesmas 609 imagens de teste em todos os braços; os intervalos são de 95%, por bootstrap pareado sobre as imagens:

| Braço | macro-F1, 16 frequentes (IC 95%) | s / imagem |
|---|---|---|
| VLM zero-shot | 0,058 (0,042–0,077) | 5,2 |
| **VLM + 3 casos recuperados** | **0,298** (0,249–0,344) | 7,5 |
| votação kNN | 0,341 (0,304–0,380) | < 0,01 |

**Sozinho, o modelo fica abaixo do piso de "prever tudo".** Ele aponta cerca de um achado por imagem (1,13 em média), e em geral é opacidade de meios.

**Os casos recuperados acrescentam 0,24 de macro-F1**, e o intervalo pareado (+0,187 a +0,286) fica bem longe do zero. Retinopatia diabética vai de 0,18 para 0,58, miopia de 0,04 para 0,46.

**Mas o resultado não é melhor que a votação kNN sobre a qual foi construído.** A diferença pareada é −0,043 (−0,084 a −0,006). O intervalo exclui o zero por pouco, então a leitura segura é "não é melhor"; a estimativa pontual é um pouco pior. O modelo só pontua acima do kNN em algumas condições raras em que o limiar do kNN quase nunca ou nunca dispara (retinopatia serosa central, coriorretinite, cicatrizes de laser, com 10 a 12 imagens positivas cada), e por um triz na oclusão de ramo venoso (0,60 contra 0,59).

E em 74% das respostas, todos os rótulos dados pelo modelo aparecem em algum dos três casos mostrados. Isso pode ser um modelo que compara bem as fotos, ou um modelo que copia os achados escritos ao lado delas. Nesta tabela, as duas coisas parecem iguais.

## O teste: mesmas fotos, rótulos errados

Então rodei de novo o braço com recuperação, nas mesmas 609 imagens, com as mesmas três fotos recuperadas para cada uma, e uma única mudança: cada caso apareceu com os achados registrados de outro caso de treino, sorteado. Nunca é um dos conjuntos de rótulos reais dos casos daquela consulta, e o sorteio tem semente por imagem, então a rodada é reproduzível. Um modelo que compara fotos quase não deveria mudar. Um modelo que lê rótulos deveria seguir o texto novo.

| Braço (mesmas 609 imagens) | macro-F1, 16 frequentes (IC 95%) |
|---|---|
| VLM zero-shot | 0,058 (0,042–0,077) |
| VLM + casos, rótulos verdadeiros | 0,298 (0,249–0,344) |
| VLM + casos, **rótulos embaralhados** | **0,056** (0,044–0,069) |

**Embaralhar os rótulos apagou todo o ganho da recuperação.** Com as mesmas fotos e rótulos errados, o braço é indistinguível de não recuperar nada (diferença −0,002, IC −0,023 a +0,016). A distância entre rótulos verdadeiros e embaralhados (+0,243) é do mesmo tamanho que todo o ganho da recuperação (+0,240). As três fotos dos casos, sozinhas, não acrescentaram nada mensurável.

**58% das respostas mudaram** quando só os rótulos mudaram. E as respostas novas seguiram o texto: em 29% das imagens (205 rótulos no total), o modelo deu um rótulo que estava no texto embaralhado, em nenhum dos casos reais, não estava na sua própria resposta zero-shot e não era verdadeiro para a imagem. Só o texto errado explica esses rótulos.

## O agente de explicação, e uma checagem que passa de qualquer jeito

O plano sempre incluiu uma etapa de explicação, porque "cita as fontes" é a maior parte da promessa. O próprio diagnóstico já tem um campo `cited_cases`, e ele parece limpo: 65% das respostas citam algum caso, nenhuma cita um caso que não existe, e em 90% das respostas que citam, todo caso citado compartilha um rótulo com a resposta.

O agente de explicação vai além. Para cada rótulo diagnosticado, o modelo precisa dizer se ele vem da foto (`image`), dos casos (`cases`) ou de `both`, e citar os números dos casos. Depois, código, e não um modelo, verifica quatro coisas:

1. Cada rótulo diagnosticado é explicado exatamente uma vez, e nada além deles.
2. Todo caso citado existe.
3. A origem bate com as citações: "image" não cita nenhum caso, "cases" e "both" citam algum.
4. **Os achados registrados de cada caso citado contêm o rótulo para o qual ele foi citado.**

Uma checagem que falha volta para o modelo como uma lista de problemas, até duas novas tentativas. Uma resposta que continua falhando é guardada e marcada como não verificada. Rodei isso sobre os diagnósticos com rótulos verdadeiros e com rótulos embaralhados:

| | rótulos verdadeiros | rótulos embaralhados |
|---|---|---|
| aprovadas pela checagem (IC 95%) | 90,0% (87,5–92,3) | 89,3% (86,9–91,8) |
| citações de casos aprovadas que apontam um rótulo que a imagem realmente tem | **48,8%** (de 549) | **12,2%** (de 344) |
| achados aprovados que dizem "vejo na foto", sem caso | 28% | 49% |

**A checagem aprovou tanto com rótulos errados quanto com rótulos certos.** Ela fez o trabalho dela: na primeira tentativa, o problema mais comum era um caso citado para um rótulo que ele não tem (296 vezes com rótulos verdadeiros, 520 com embaralhados), e o retorno corrigiu a maior parte. Mas o trabalho dela era a consistência com o texto mostrado, e o texto estava errado.

**Uma citação aprovada não é uma citação correta.** Mesmo com os rótulos verdadeiros, menos da metade das citações aprovadas aponta um rótulo que a imagem tem. Com os rótulos embaralhados, uma em cada oito.

**E as explicações dizem que viram na foto.** Quase todo achado que cita um caso vem como "both", visto na foto *e* nos casos. Com os rótulos embaralhados, metade dos achados aprovados diz "só na foto". Pela seção anterior, sabemos que as respostas acompanharam o texto, então "consigo ver na imagem" não é evidência de que o modelo viu.

Um caso da rodada embaralhada, aprovado na primeira tentativa (imagem de teste 205). A imagem tem o rótulo de retinopatia diabética. Os três casos reais mais próximos também têm esse rótulo, e com eles o modelo respondeu retinopatia diabética. Diante das mesmas três fotos, com o caso 1 rotulado como degeneração macular relacionada à idade e os casos 2 e 3 como normais, ele respondeu degeneração macular, citou o caso 1, marcou a origem como "both" e explicou:

> "The QUERY photograph shows signs of age-related macular degeneration, consistent with the finding in reference case 1, which was also labeled ARMD."

("A foto consultada mostra sinais de degeneração macular relacionada à idade, coerente com o achado do caso de referência 1, que também tinha o rótulo ARMD.") Todas as checagens passaram.

Algumas explicações reprovadas dizem tanto quanto essas. Num caso do piloto de validação, o modelo citou três casos de miopia para tesselação, que nenhum deles tinha. Avisado disso, manteve a citação nas duas novas tentativas, explicando que a miopia deles "está associada à tesselação". Deixei o prompt como estava: ajustá-lo até a checagem passar mediria o meu prompt, não o sistema.

## O que 609 imagens dizem e o que não dizem

Os intervalos acima cobrem um tipo de incerteza: quais imagens de teste calharam de ser sorteadas. Não cobrem outro modelo, outro prompt, outro número de casos ou outro dataset. É um dataset (três câmeras, uma rede hospitalar na Índia), um modelo de 8B em 4 bits, um prompt e decodificação gulosa. Um modelo mais forte talvez compare as fotos melhor, e o teste dos rótulos embaralhados é justamente como descobrir.

A referência são os rótulos do RFMiD, que discordam de si mesmos no mesmo olho. A câmera não está nos arquivos de rótulos, então não consegui testar se o kNN, e portanto os casos que o modelo vê, em parte casa câmeras em vez de doenças. Nada disso é acurácia diagnóstica.

## O que eu diria a uma equipe construindo isso

1. **Rode um teste com rótulos embaralhados antes de chamar qualquer coisa de "fundamentada".** Mantenha as imagens recuperadas, troque os rótulos e meça de novo. Custa uma rodada a mais. Se o resultado cair ao nível do zero-shot, o modelo está lendo os rótulos e as imagens recuperadas são enfeite. Aqui o teste levou todos os pontos do ganho.
2. **Compare com a votação entre vizinhos, não só com o modelo sozinho.** "A recuperação melhora o VLM em 0,24" é verdade e engana. A votação entre os vizinhos mais próximos, base da recuperação, foi no mínimo tão boa, em milissegundos, sem modelo nenhum.
3. **Uma checagem de citações prova consistência, não correção.** Verifique citações em código, porque isso pega erros reais (aqui, centenas de casos citados para rótulos que não têm). Depois meça à parte se o que foi citado é verdade. Aqui era verdade em 49% das citações aprovadas, e em 12% com os rótulos errados, com a mesma taxa de aprovação.
4. **Não confie em "vejo na imagem".** O relato de um modelo sobre de onde veio a resposta é uma frase gerada como qualquer outra. Teste mudando o que ele poderia ter usado, e veja o que se mexe.
5. **Audite duplicatas e rótulos antes do modelo.** A auditoria pelo desenho dos vasos levou uns 11 minutos de processamento, mais o tempo de olhar pares para definir o limiar, e achou 154 pares do mesmo olho. Mais da metade deles (54%) discorda nos rótulos. Esse limite vale para qualquer método que você avaliar com esses rótulos.
6. **Para um dataset brasileiro como o BRSET, o que se reaproveita é o arcabouço de avaliação.** Troque o índice e mantenha os três braços, a rodada com rótulos embaralhados e o bootstrap. Quem tem acesso credenciado pode rodar o mesmo teste no próprio hardware e descobrir se a recuperação ajuda o modelo a olhar, ou só ajuda o modelo a ler.

---

*Ideia do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (projeto nº 2, RAG médico multimodal para doenças oculares). Dados: RFMiD 1.0, S. Pachade et al., "Retinal Fundus Multi-Disease Image Dataset (RFMiD): A Dataset for Multi-Disease Detection Research", Data 2021, 6(2), 14, doi:10.3390/data6020014, CC BY 4.0. Modelos: BiomedCLIP (Zhang et al., 2023, MIT, só para pesquisa) e Qwen3-VL-8B-Instruct (Apache-2.0), ambos rodando localmente. BRSET: Nakayama et al., PLOS Digital Health, 2024 (PhysioNet). Não é um dispositivo médico. Código, testes e todos os números: [github.com/ricardocunha/ensaios › articles/2027-01-multimodal-medical-rag-eye](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-multimodal-medical-rag-eye).*
