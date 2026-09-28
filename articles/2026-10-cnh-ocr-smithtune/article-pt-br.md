---
title: "Testei o smithtune, o novo fine-tuning do LangSmith, para ler CNH com IA open source"
subtitle: "Fine-tuning de modelos de OCR abertos e destilação de um agente Claude em um modelo de 9B, na primeira semana do smithtune"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — substituir todos os [[RESULT: …]] antes de publicar
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-cnh-ocr-smithtune
---

# Testei o smithtune, o novo fine-tuning do LangSmith, para ler CNH com IA open source

No dia 24 de setembro de 2026, a LangChain lançou o **LangSmith Fine-Tuning** e sua CLI, o **smithtune**. A promessa: pegar os traces que o seu agente já gera no LangSmith, transformar os bons em dataset de treino, fazer fine-tuning de um modelo aberto em GPUs gerenciadas, avaliar contra o original e colocar em produção. Tudo por uma CLI, sem provisionar uma GPU sequer.

Quis testar num problema que conheço bem: **ler a CNH**. Fintechs, locadoras, apps de entrega: metade dos fluxos de onboarding no Brasil começa com "tire uma foto da sua CNH". As APIs de modelos de fronteira resolvem, mas custam caro por documento e mandam dado pessoal para fora do país, o que é uma conversa séria de LGPD.

Isto é um relato de campo, dois dias depois do lançamento, e não um tutorial. Tem bastante código (o link do repositório está no fim), e uma descoberta logo no primeiro dia mudou o projeto inteiro.

---

## O que é o smithtune, na prática

Em português claro, o smithtune é **um pipeline que vai do "histórico do meu agente" até "um modelo menor que se comporta como o meu agente"**. São quatro etapas:

1. **Curadoria.** `smithtune dataset pull` baixa *trajetórias* de um projeto de tracing do LangSmith. Uma trajetória é uma execução completa do agente: a mensagem do usuário, cada turno do modelo e cada chamada de ferramenta, até a resposta final. Você seleciona com um filtro do LangSmith, por exemplo "só execuções com feedback `correctness` = 1". Opcionalmente, `smithtune dataset triage` envia cada trajetória para um **conselho de agentes**: vários juízes LLM que dão nota com base numa rubrica que *você* escreve. Não existe rubrica padrão, e a ferramenta se recusa a adivinhar. Depois, `dataset push` guarda o conjunto curado de volta no LangSmith.
2. **Preparo e treino.** `smithtune prepare` renderiza cada trajetória no template de chat exato do modelo-alvo (revisão do tokenizer fixada, template verificado) e separa os dados em cerca de 80/10/10. `smithtune train` roda **fine-tuning supervisionado com LoRA** num provedor gerenciado: **Fireworks** ou **Baseten**.
3. **Avaliação.** Aqui está a parte esperta. `smithtune evaluate` faz uma **avaliação por replay**. Em cada passo de uma trajetória separada para teste, o modelo recebe o contexto gravado e precisa prever a próxima ação. As ferramentas *não* são executadas, então nada toca nos seus sistemas de produção. Um juiz LLM avalia se a previsão concorda com o que o modelo original fez, e o modelo base e o ajustado aparecem lado a lado como experimentos no LangSmith.
4. **Deploy.** `smithtune deploy` sobe o modelo ajustado num endpoint, e `smithtune undeploy` derruba.

Todo passo que custa dinheiro exige `--confirm`; sem ele, o smithtune só mostra uma prévia. Gostei disso mais do que esperava.

No post de lançamento, a LangChain mostra um fine-tuning do Kimi K3 chegando a 96,0 de nota numa tarefa, contra 90,0 do modelo base e 87,0 do GPT-5.6, num agente interno deles. Essa é a tese: **seus traces são um dataset pelo qual você já está pagando.**

## O porém que encontrei no primeiro dia

O plano original era simples: fazer fine-tuning de um modelo de OCR de ponta, o **Chandra**, da Datalab, com imagens de CNH, usando o smithtune.

Aí fui ler o código-fonte. Duas coisas chamam atenção na v0.1.0:

**1. Trajetórias com imagem são filtradas.** E não é por acaso. Existe uma função dedicada, `multimodal_types()`, que procura `image`, `image_url`, `input_image`, áudio, vídeo, arquivos e PDFs. A triagem descarta essas trajetórias antes do julgamento:

```python
# smithtune/triage.py (v0.1.0)
"reason": "Filtered before judging: multimodal content (" + ", ".join(media) + ")."
```

**2. Os modelos base vêm de uma lista fixa.** Na Fireworks: Qwen3.8-27B, Kimi K3, DeepSeek V4 Flash e Muse Glimmer 30B. Na Baseten: Qwen3.8-27B, Qwen3.5-9B, Kimi K3 e GLM-5.3-Flash. Cada um tem a revisão do tokenizer fixada e um "renderer" escrito à mão que reproduz exatamente o template de chat. É por isso que não dá para apontar para qualquer modelo do Hugging Face: treinar com um template diferente do usado na inferência piora o modelo sem avisar, e o smithtune escolheu correção em vez de amplitude.

Ou seja: **hoje o smithtune não faz fine-tuning de modelo de OCR.** Não é defeito. É um produto de texto e tool calls em beta público. Mas isso muda a arquitetura.

## A arquitetura que funciona: Reader + Extractor

Dividi o problema no ponto em que os pixels viram texto:

```
Foto da CNH ─► [ Reader ] ─► Transcrição ─► [ Extractor ] ─► Registro CNH (JSON validado)
               modelo de OCR (visão)           agente só-texto com ferramentas
               fine-tuning com HF / MLX         Claude Sonnet 5 → Qwen3.5-9B via smithtune
```

- O **Reader** é um modelo de visão que transforma a foto numa *Transcrição*: uma linha `RÓTULO: valor` por campo impresso, **exatamente como está impresso, com erros e tudo**. Ele nunca valida nada.
- O **Extractor** é um agente que só lê texto. Ele recebe a Transcrição e chama ferramentas determinísticas: dígitos verificadores do CPF, dígitos verificadores do número de registro da CNH, uma ferramenta que sugere correções de OCR (`O→0`, `S→5`, `B→8`), normalização de datas e checagens de coerência como "CNH emitida aos 45 anos vale 10 anos" (Lei 14.071/2020). No fim, envia um **Registro CNH** validado, ou rejeita a entrada se não for uma CNH.

O Extractor é exatamente o tipo de agente para o qual o smithtune foi feito: vários passos, muitas ferramentas, fácil de verificar. E, como nunca vê pixels, as trajetórias dele passam pelo filtro do smithtune.

## Etapa 1: três modelos de OCR abertos, um ajustado num MacBook

Parti do ótimo panorama do Hugging Face sobre modelos abertos de OCR ([Supercharge your OCR pipelines with open models](https://huggingface.co/blog/ocr-open-models)) e escolhi três modelos que cobrem bem as opções:

| Modelo | Tamanho | Por quê |
|---|---|---|
| **Chandra 2** (`datalab-to/chandra-ocr-2`) | ~5B | Especialista em OCR. O model card reporta **95,2% em português** (Chandra 1: 84,3%) |
| **PaddleOCR-VL-1.6** | 0,9B | Especialista minúsculo, 109 idiomas, Apache-2.0 |
| **Qwen3.5-9B** | 9B | Generalista, e o *mesmo modelo base* do meu Student no smithtune |

Um alerta de licença, porque isso vai pegar alguém: **os pesos do Chandra 2 não são livres para uso comercial na maioria das empresas.** A licença (uma OpenRAIL-M modificada) proíbe uso comercial por organizações com mais de US$ 2 milhões de faturamento *ou* de investimento captado, e tem cláusula share-alike que alcança derivados *e as saídas do modelo*. "Pesos abertos" não é a mesma coisa que "livre para usar no trabalho". Leia a licença.

**Dados: só sintéticos.** Não treino com documento de gente real, e você também não deveria. Escrevi um gerador que:
- cria pessoas fictícias coerentes com o Faker `pt_BR`, com **dígitos verificadores de CPF e CNH válidos**, para que as ferramentas de checksum tenham algo real para verificar;
- desenha um cartão *inspirado* na CNH (mesmos rótulos, layout parecido, sem brasão, sem elementos de segurança e com uma marca d'água grande *AMOSTRA / SYNTHETIC*), além de uma variação que imita print da CNH Digital;
- degrada cada cartão para parecer "foto de celular": perspectiva, rotação, sombra, desfoque, artefatos de JPEG;
- mistura 10% de "iscas" (cartões parecidos com RG, notas fiscais) que o pipeline precisa rejeitar.

São 2.293 imagens de treino (o plano era 3.000; uma execução interrompida me fez parar por aí, e é mais que suficiente para LoRA), 300 de validação, 300 de teste e 100 "difíceis". Para checar realismo além do meu próprio gerador, também avalio no **BID Dataset** (Soares et al., SIBGRAPI 2020), citado e não redistribuído. Falo mais dele abaixo, porque ele mudou a história.

**O treino roda local.** O `mlx-vlm` suporta LoRA em Apple Silicon para o PaddleOCR-VL e para a família Qwen3.5, na qual o Chandra 2 é baseado. Ajustei só o menor modelo, o PaddleOCR-VL (0,9B). Ele treina em menos de duas horas num M4 Pro de 48 GB, o que me permitiu rodar duas rodadas completas e aprender algo com cada uma. O Chandra 2 e o Qwen3.5-9B aparecem abaixo só em zero-shot; ajustá-los com QLoRA de 4 bits é o próximo experimento óbvio:

```bash
python -m mlx_vlm.lora --model-path PaddlePaddle/PaddleOCR-VL-1.6 --dataset data/synth \
  --epochs 1 --lora-rank 32 --grad-checkpoint --train-on-completions
```

### Zero-shot: o generalista vence, e os especialistas não seguem instrução

Antes de qualquer fine-tuning, dei a mesma instrução para os três modelos: *"transcreva esta CNH com uma linha `RÓTULO: valor` por campo impresso, exatamente como aparece; se não for CNH, responda `NÃO É CNH`."* Testei em 50 imagens sintéticas separadas para teste (43 CNHs e 7 iscas), com o modo de raciocínio do Qwen desligado.

| Modelo (zero-shot) | Acurácia por rótulo | Recall de valores | CER | Iscas rejeitadas | s / imagem (M4 Pro) |
|---|---|---|---|---|---|
| **Qwen3.5-9B** (generalista) | **72,4%** | 99,8% | 0,31 | 3/7 | 21,3 |
| Chandra 2 (~5B)* | 17,3% | **100,0%** | 6,50 | 0/7 | 51,0 |
| PaddleOCR-VL-1.6 (0,9B) | 17,4% | 85,5% | 2,43 | 0/7 | 3,1 |

As métricas de acurácia são medidas só nas CNHs; as iscas são contadas à parte:
- A *acurácia por rótulo* é a fração de campos cujo valor saiu, exato, no rótulo certo. O rótulo em si é comparado com tolerância: `CAT.HAB.` conta como `CAT. HAB.`.
- O *recall de valores* ignora o formato: cada valor impresso aparece *em algum lugar* da saída?
- O *CER* é a taxa de erro por caractere contra a Transcrição de referência. Acima de 1,0 significa mais edições do que caracteres.

<sub>*O Chandra 2 recebeu um limite de 3.000 tokens de saída. Com 600, 46 de 50 saídas eram cortadas no meio do cartão. Cerca de 14% de acurácia por rótulo é o piso: campos em branco como PERMISSÃO e ACC batem mesmo quando o formato é ignorado.</sub>

Três coisas me surpreenderam:

- **Os especialistas leem perfeitamente, mas não seguem instrução.** O Chandra 2 encontrou *todos* os valores impressos (recall de 100%), e aí ignorou o prompt e escreveu o próprio formato HTML de layout, com bounding box em cada elemento:

  ```html
  <div data-bbox="335 284 556 320" data-label="Text"><p><b>ASAFE COSTA SIQUEIRA</b></p></div>
  ```

  Isso é ótimo para pipelines de documentos. Só não é o que eu pedi, e a 51 s por imagem o HTML custa mais tokens do que o texto que carrega. O PaddleOCR-VL escreve texto livre: linhas com várias colunas saem como `Nº REGISTRO VALIDADE 1º HABILITAÇÃO 34627740679 12/10/2027 02/11/2009`, e o pareamento rótulo–valor some. Ele também entra em loop e repete blocos, por isso o CER passa de 2.

- **Os erros do generalista são do tipo perigoso.** O Qwen3.5-9B segue o formato em 35 de 43 CNHs; nas outras 8, troca para "rótulo numa linha, valor na seguinte". Pior: às vezes escreve uma data *bem formatada e errada*, como `DATA NASCIMENTO: 29/05/1990` quando o cartão diz `23/07/1990`. O dígito verificador pega um CPF mal lido; nada pega uma data plausível. Esse é um bom motivo para o Extractor existir.

- **Ninguém rejeita as iscas.** Das 7 imagens que não são CNH, o Qwen disse "não é CNH" 3 vezes, e os especialistas nenhuma.

O zero-shot deixa claro o argumento para o fine-tuning: o conhecimento está lá (recall de até 100%), mas o contrato de saída não. Deveria ser a coisa mais fácil de ensinar com LoRA.

### Fine-tuning: 99,8%, nos meus próprios cartões

Comecei pelo menor modelo, o PaddleOCR-VL (0,9B): LoRA de rank 32, uma época sobre 2.293 imagens. Levou **1h51 no M4 Pro, com pico de 5,7 GB**.

Teve um desvio no caminho. A primeira execução morreu com falta de memória no Metal, e o log dizia `trainable params: 451M || all params: 905M (49.8%)`, o que não é cara de LoRA. O mlx-vlm congela encoders de visão pelo nome do atributo (`vision_model`, `vision_tower`, …), e o PaddleOCR-VL chama o dele de `visual`, então a torre de visão inteira estava sendo treinada. Congelando o `visual` na mão, caiu para 12,1M parâmetros treináveis (1,3%). Lição: **sempre leia a linha de parâmetros treináveis.**

| PaddleOCR-VL, teste sintético | Acurácia por rótulo | Recall de valores | CER | Iscas rejeitadas | s / imagem |
|---|---|---|---|---|---|
| zero-shot | 17,4% | 85,5% | 2,43 | 0/7 | 3,1 |
| **+ LoRA** | **99,8%** | **99,8%** | **0,00** | **7/7** | **2,8** |
| + LoRA, 100 imagens "difíceis" | 99,8% | 99,8% | 0,00 | 11/11 | 2,8 |

As imagens de teste não compartilham nenhum CPF, nome ou transcrição com o treino. O único erro no conjunto de teste é um acento perdido (`CÂMARA` → `CAMARA`) num print de CNH Digital. Um modelo de 0,9B num notebook supera o Qwen3.5-9B zero-shot por 27 pontos, 7× mais rápido.

Eu estava pronto para escrever "o fine-tuning resolveu". Aí testei em cartões reais.

### Aí testei em cartões reais

O **BID Dataset** me dá o que o meu gerador não consegue: **layouts reais de CNH, escaneados**, com dados pessoais sintéticos e rosto borrado, muitas vezes **de lado ou de cabeça para baixo**. Usei a amostra pública: 70 CNHs (frente e aberta) e 72 frentes de RG/CPF como iscas. As anotações são caixas de texto, não campos rotulados, então pareio cada valor com seu rótulo por formato e posição, e avalio os 7 a 9 campos que dá para parear sem ambiguidade.

| BID (layouts reais) | Acurácia por rótulo | Recall de valores | CNHs reais **rejeitadas** | RG/CPF rejeitados | s / imagem |
|---|---|---|---|---|---|
| PaddleOCR-VL zero-shot | 0,0% | 80,8% | 0/70 | 0/72 | 1,2 |
| **PaddleOCR-VL + LoRA** | 32,0% | 34,0% | **48/70** | 72/72 | 0,6 |
| Qwen3.5-9B zero-shot | **48,2%** | **85,4%** | 5/70 | 59/72 | 7,1 |

De 99,8% nos meus cartões para 32,0% nos reais. O modelo ajustado **respondeu "NÃO É CNH" para 48 de 70 carteiras de motorista legítimas.**

E aqui está a parte interessante. Nas 22 CNHs reais que ele *aceitou*, fez **92,9% de acurácia por rótulo e 96,3% de recall**. A habilidade de ler foi transferida. O que não foi transferido foi a ideia de *como uma CNH se parece*. Meu gerador tinha um único visual, então o modelo aprendeu "CNH = aquele visual" e tratou todo o resto como isca. Mais duas pistas:

- **Parar antes não ajuda.** No passo 1.000 o modelo já está com 99,9% nos sintéticos e ainda rejeita 49 de 70 CNHs reais. No passo 200 ele rejeita quase tudo, inclusive os sintéticos. O problema está nos dados, não no cronograma de treino.
- **Minhas iscas também eram irreais.** O Qwen zero-shot rejeita 59 de 72 RGs e CPFs *reais*, mas só 3 de 7 das minhas iscas sintéticas: notas fiscais, cartas e um cartão lilás de "REGISTRO GERAL" que não se parecem com nada real.

Esse é o gap sim-to-real na forma mais pura, e um conjunto de teste sintético nunca vai mostrá-lo para você. **Se você faz fine-tuning com documentos sintéticos, precisa de pelo menos um pequeno conjunto de avaliação real**, mesmo que não possa treinar com ele.

### Rodada 2: variar o que não deveria importar

A correção é *domain randomization*: variar tudo o que não deveria mudar a resposta, para o modelo não usar isso como atalho. Com o mesmo modelo, os mesmos hiperparâmetros e as mesmas 2.293 imagens, mudei só os dados:
- **Visual:** seis paletas, três famílias de fonte, layout deslocado, campos em caixas, rótulos acima ou abaixo da caixa, e variações de rótulo impressas (`CAT.HAB.`, `N° REGISTRO`, `1º HABILITAÇÃO`).
- **Captura:** 40% escaneados, e um quarto das imagens girado 90°, 180° ou 270°.
- **Iscas:** RGs e CPFs com as *mesmas* paletas e o mesmo estilo de caixas.

Para o BID continuar honesto como teste, usei só propriedades gerais que notei ao escrever o loader, e avalio nele uma vez por rodada.

| BID (70 CNHs reais, 72 RG/CPF) | Acurácia por rótulo | Recall de valores | CNHs reais rejeitadas | RG/CPF rejeitados | s / imagem |
|---|---|---|---|---|---|
| PaddleOCR-VL + LoRA, rodada 1 (um visual) | 32,0% | 34,0% | 48/70 | 72/72 | 0,6 |
| **PaddleOCR-VL + LoRA, rodada 2 (variado)** | **52,3%** | 60,6% | **30/70** | **72/72** | **0,9** |
| Qwen3.5-9B zero-shot | 48,2% | 85,4% | 5/70 | 59/72 | 7,1 |

E isso não custou nada em casa: no meu conjunto de teste sintético original, o modelo da rodada 2 continua com **99,8%** (conjunto difícil: 99,7%, contra 99,8% na rodada 1), com todas as iscas rejeitadas.

Mesmo modelo, mesmos hiperparâmetros, as mesmas 2.293 imagens; só a variedade mudou. A acurácia nos cartões reais subiu **20 pontos**, e as CNHs rejeitadas por engano caíram de 48 para 30, enquanto RGs e CPFs reais continuaram sendo rejeitados 72 de 72. O modelo de 0,9B agora passa um pouco à frente do Qwen3.5-9B zero-shot (52,3% contra 48,2%), cerca de **8× mais rápido**.

Mas não está resolvido. Ele ainda recusa **30 de 70 CNHs reais**. Nas 40 que aceita, lê 78,8% dos rótulos e 91,8% dos valores; as CNHs aceitas agora incluem cartões mais difíceis, então a média nas aceitas caiu de 92,9%. O Qwen, por outro lado, quase não rejeita CNH real (5/70). Só lê com menos precisão.

Duas lições que vou levar para o próximo projeto:

- **Variedade vale mais que volume.** Não adicionei nenhuma imagem; só deixei as mesmas 2.293 menos parecidas entre si. Só isso mexeu a acurácia no mundo real em 20 pontos.
- **O porteiro é a parte difícil, e talvez não deva ficar no modelo de visão.** Um modelo ajustado numa distribuição estreita fica muito confiante sobre o que "é" e muito rápido para rejeitar o que "não é". Neste pipeline o Extractor vê toda Transcrição de qualquer jeito, e o Qwen zero-shot rejeitou bem RGs e CPFs reais (59/72) sem treino nenhum. A rodada 3 testa exatamente isso.

### Rodada 3: tirar a decisão do modelo de visão

O Reader agora recebe uma instrução simples, "transcreva este documento", sem opção de recusar. As iscas são treinadas com o que elas de fato imprimem: um RG vira `NOME: … / FILIAÇÃO: … / NATURALIDADE: …`. A decisão "é CNH ou não" passa para o lado do texto. No pipeline completo, quem decide é o Extractor; para esta medição, uma regra simples faz o papel: a Transcrição é CNH se tiver pelo menos dois rótulos que só uma CNH imprime (CAT. HAB., Nº REGISTRO, 1ª HABILITAÇÃO, VALIDADE, PERMISSÃO, ACC). As imagens, o modelo, os hiperparâmetros e as 2.293 imagens são os mesmos da rodada 2.

| BID (70 CNHs reais, 72 RG/CPF) | Acurácia por rótulo | Recall de valores | CNHs reais rejeitadas | RG/CPF rejeitados | s / imagem |
|---|---|---|---|---|---|
| Rodada 1: um visual, o Reader decide | 32,0% | 34,0% | 48/70 | 72/72 | 0,6 |
| Rodada 2: variado, o Reader decide | 52,3% | 60,6% | 30/70 | 72/72 | 0,9 |
| **Rodada 3: variado, o texto decide** | **81,0%** | **94,4%** | **0/70** | 64/72 | 2,3 |
| Qwen3.5-9B zero-shot | 48,2% | 85,4% | 5/70 | 59/72 | 7,1 |

**Nenhuma CNH real rejeitada**, e a acurácia nos cartões reais foi de 32% para 81% ao longo das três rodadas. Nos meus conjuntos sintéticos nada piorou (100% no teste, 99,6% no conjunto difícil). Um modelo de 0,9B num notebook agora supera o Qwen3.5-9B zero-shot nos cartões reais por 33 pontos, três vezes mais rápido.

O custo também aparece: **8 de 72 RGs reais passaram pelo porteiro.** Os 8 são do mesmo modelo de RG, e neles o Reader começa a repetir rótulos de CNH com valores *vazios* (`Nº REGISTRO:`, `PERMISSÃO:`), um hábito aprendido com milhares de CNHs, enquanto a regra só confere se os rótulos existem. A correção é óbvia: contar só rótulos de CNH com um valor plausível (registro de 11 dígitos, categoria válida, uma data). Mas desenhei essa correção depois de ver as falhas no BID, então uma nova nota no BID não seria mais um teste honesto, e deixo isso como próximo passo. No pipeline completo, esses 8 ainda teriam que passar pelo Extractor, que valida os dígitos verificadores antes de enviar qualquer coisa.

O que levo da Etapa 1:

- **Nota sintética não separa o bom do ruim.** As três rodadas fazem 99–100% nos meus conjuntos sintéticos. Só o conjunto real separa: 32%, 52%, 81%.
- **Deixe o modelo de visão ler, e decida em outro lugar.** O maior salto não veio de mais dados nem de um modelo maior; veio de tirar uma decisão da parte do sistema que não conseguia generalizá-la.

## Etapa 2: destilando um agente Claude com o smithtune

### Gravando o Teacher

O Extractor é um `create_agent` do LangChain com oito ferramentas. O Teacher é o **Claude Sonnet 5**. Rodei 1.500 Transcrições: saídas reais do Reader e também Transcrições corretas com **ruído de OCR injetado** (troca letra/dígito, separador de data quebrado, `A8` no lugar de `AB`, linha faltando). Entrada limpa não ensina a recuperar erro.

O truque mais útil: **como os dados são sintéticos, toda execução tem gabarito.** Então o runner dá nota campo a campo para cada trajetória e grava de volta no LangSmith como feedback (`field_accuracy`, `exact`). Isso dá ao smithtune um sinal de qualidade *confiável* para filtrar, que é o que a própria documentação recomenda no lugar de "não deu erro" ou "o agente terminou":

```bash
smithtune dataset pull runs/smithtune/golden --project-id $PROJECT \
  --filter 'and(eq(feedback_key, "exact"), eq(feedback_score, 1))' \
  --target-count 1000 --no-triage
```

`[[RESULT: quantas das 1.500 execuções do Teacher foram exatas; custo do Teacher]]`

### O conselho de agentes concorda com o gabarito?

Como eu tinha gabarito de qualquer forma, fiz um experimento que ninguém conseguiria fazer no segundo dia: rodei a **triagem do conselho** em 200 trajetórias com a minha rubrica ("validou os checksums antes de enviar", "nunca inventou campo ausente", …) e comparei as decisões de manter ou descartar com a verdade.

`[[RESULT: % de concordância, manteve errado, descartou certo, um exemplo de erro do conselho]]`

### Treino, avaliação por replay, deploy

```bash
smithtune prepare --provider baseten --model Qwen/Qwen3.5-9B --dataset-id $GOLDEN ...
smithtune plan    --provider baseten --data-dir runs/smithtune/golden --evaluate
smithtune train   --provider baseten --data-dir runs/smithtune/golden --run-dir runs/... --evaluate --confirm
```

`[[RESULT: estimativa do plan vs tempo/custo real; o que quebrou]]`

`[[RESULT: replay eval: teacher_agreement base vs ajustado]]`

## Os números que importam

A concordância no replay diz se o Student *imita* o Teacher. A pergunta de negócio é outra: **ele extrai o CPF certo?** Então fiz o deploy do Student e rodei nas mesmas 300 Transcrições de teste que o Teacher:

`[[RESULT: tabela: Teacher (Sonnet 5) vs Qwen3.5-9B base vs Qwen3.5-9B ajustado. Acurácia por campo, registros exatos, média de tool calls, latência p50, US$/1.000 CNHs]]`

`[[RESULT: frase-manchete: "o 9B ajustado chega a X% da acurácia do Teacher custando Y%"]]`

## Veredito sobre o smithtune (v0.1.0)

**O que gostei**
- **A abstração certa.** "Traces → dataset curado → LoRA → avaliação por replay → deploy" é o ciclo que todo time acaba reconstruindo na mão.
- **A avaliação por replay** é um padrão esperto e seguro: compara modelos passo a passo sem executar ferramentas contra sistemas reais.
- **Engenharia cuidadosa:** tokenizer fixado, template de chat verificado, `--confirm` em todo passo pago e nenhuma rubrica padrão.
- **Feito para ser usado por um agente de código:** vem como skill (`npx skills add langchain-ai/smithtune`), e a documentação parece escrita como instrução para um.

**O que saber antes de começar**
- **Só texto e tool calls.** Traces de imagem, áudio e documento são filtrados.
- **Lista fixa de modelos** em dois provedores. Não dá para trazer o seu próprio modelo do Hugging Face.
- **Concordância no replay não é acurácia na tarefa.** Meça também a sua métrica de negócio.
- **O deploy custa dinheiro até você dar undeploy.** Coloque um lembrete.
- É um beta público que saiu esta semana. Espere arestas. `[[RESULT: links das issues que abri]]`

**Quem deveria usar hoje?** Times que já têm um agente funcionando com tracing no LangSmith, pagam preço de modelo de fronteira por ele e querem um modelo mais barato e mais rápido que se comporte igual. Se esse é o seu caso, o caminho de traces até modelo ajustado nunca foi tão curto.

**O que eu quero na v0.2:** trajetórias multimodais. A Fireworks já faz fine-tuning do Qwen3-VL-8B com imagens pela própria API. No dia em que o smithtune suportar isso, um Student de uma etapa só (imagem → JSON) passa a ser possível, e eu refaço este experimento.

---

**Código, dados e adapters:** [github.com/ricardocunha/ensaios › articles/2026-10-cnh-ocr-smithtune](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-cnh-ocr-smithtune) · Dataset sintético: `[[RESULT: URL do dataset no HF]]`

*Todos os documentos deste projeto são sintéticos. Nenhum dado de pessoa real foi usado no treino.*

#InteligenciaArtificial #MachineLearning #LLM #OCR #FineTuning #LangChain #OpenSource
