---
title: "Um roteador de prompts por US$ 1,88: o que rótulos sintéticos compram, e o que não compram"
subtitle: "Eu precisava de um classificador de prompts em quatro Tiers para um gateway de IA, o modelo aberto que eu tinha escolhido se mostrou, pela minha leitura da licença, inutilizável num produto hospedado, e treinei o meu em CPU, em cerca de um dia, com dados sintéticos. Ele bateu a meta de 80%. Aqui está tudo o que esse número deixa de fora."
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — números finais (cada um está mapeado para o repositório do keelgw em SOURCES.md); afirmações sobre terceiros a reconferir antes de publicar
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway
---

# Um roteador de prompts por US$ 1,88: o que rótulos sintéticos compram, e o que não compram

> **Construído e verificado só localmente.** Até o último commit descrito aqui (06/10/2026), o gateway do keelgw nunca rodou numa conta AWS de verdade, nunca enviou uma requisição a um provedor de modelos de verdade e nunca atendeu um cliente. Todas as medições abaixo foram feitas num laptop. As únicas chamadas a uma API de verdade foram os lotes de rotulagem dos dados de treino.

Venho construindo o [keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway), um gateway de IA multi-tenant para pequenas empresas. Ele controla quais Models cada Member de uma Organization pode usar, por quais Clients (Claude Code, Claude Cowork, Codex) e com que Spend em dólares, sempre nas contas de provedor da própria Organization.

Uma das funções é o `model: auto`: o gateway classifica o prompt em um de quatro Tiers (simple, medium, complex, reasoning), e um Tier Map diz qual Model permitido atende cada Tier. Para isso é preciso um roteador de prompts. Eu tinha escolhido um modelo aberto de roteamento, e aí li a licença com atenção. Então treinei meu próprio classificador pequeno, em CPU, com dados sintéticos, em cerca de 26 horas entre o primeiro commit do script de geração de dados e o commit do modelo treinado.

Resumindo:

- **Os dados custaram US$ 1,88 de API.** Um modelo aberto local escreveu 4.412 prompts, o Claude Haiku 4.5 rotulou todos de novo às cegas, e o Claude Opus 5.5 arbitrou as 2.006 divergências.
- **Os dois primeiros modelos concordaram em 54,5% dos prompts** (mesmo Tier, com o rotulador confiante). A concordância caiu conforme o Tier subia: 84,2% nos prompts escritos como simple, 33,8% nos escritos como reasoning.
- **O classificador acerta 80,0% em 400 prompts sintéticos separados para avaliação**, exatamente a meta. Tomei uma decisão de treino olhando para esse conjunto, então não é um número limpo de conjunto separado.
- **Nada disso diz que funciona com tráfego real.** O gateway nunca chamou o roteador treinado, e nada mede Spend economizado nem qualidade das respostas.
- **O resto do gateway está no mesmo ponto**: construído, testado localmente, e o pior número de teste de carga que registrei (um p99 de 29,4 s) mediu o emulador de AWS, não o gateway.

Cada número está mapeado para um arquivo, linha ou commit do repositório do keelgw em [SOURCES.md](https://github.com/ricardocunha/ensaios/blob/main/articles/2027-02-keelgw-ai-gateway/SOURCES.md).

## Por que o gateway precisa de um roteador

No keelgw, um Profile lista os Models que um Member pode usar. No `auto`, o classificador devolve só um Tier, nunca o nome de um Model, e o Tier Map do Profile transforma o Tier em um dos Models permitidos. Assim, trocar o classificador nunca muda o que um Member consegue acessar.

Cada Tier é definido em uma frase, a mesma no gateway e no script de treino. *Simple* são pedidos curtos e mecânicos: renomear, formatar, consultas rápidas. *Medium* são tarefas comuns de programação: implementar uma função, corrigir um bug claro. *Complex* é trabalho grande ou de várias etapas: mudanças em vários arquivos, depuração sem causa clara. *Reasoning* são problemas difíceis: decisões de arquitetura, algoritmos, provas, análises sutis de concorrência ou de segurança.

Se o Router embutido não responde em 1.500 ms, a requisição usa o Tier de fallback do Profile. A classificação nunca recusa uma requisição.

## O plano que não passou pela leitura da licença

O projeto original apontava o Arch-Router-1.5B, um modelo generativo pequeno que compara o prompt com políticas escritas em linguagem natural, "on the belief that it was Apache-2.0" (acreditando que era Apache-2.0), como o documento de design diz hoje. Em 30/09/2026 registrei um bloqueio: pela minha leitura da licença do modelo naquele dia, ela é a licença Katanemo, que exige uma licença comercial separada da DigitalOcean para qualquer uso comercial, inclusive oferecer o modelo como serviço. Um gateway hospedado que sirva o modelo seria exatamente isso.

A alternativa prevista era o RouteLLM. O documento de design registra por que também não servia: ele roteia entre duas classes (forte e fraco), e eu precisava de quatro; os roteadores recomendados chamam a API de embeddings da OpenAI a cada prompt; e os checkpoints para hospedar por conta própria não trazem licença, embora o código seja Apache-2.0. São anotações minhas sobre projetos de outras pessoas, escritas em setembro e outubro de 2026. Confira antes de se apoiar nelas.

Em 03/10/2026 decidi treinar o meu: quatro Tiers nativos, sem GPU, nada enviado para fora do gateway, cada peça com uma licença que posso distribuir.

## O classificador: um modelo de embeddings e uma cabeça de 21 KB

```
último turno do usuário (+ turnos anteriores, no máximo 8.000 caracteres ao todo)
        │
        ▼
intfloat/multilingual-e5-small, ONNX Runtime em CPU ─► embedding de 384 dimensões
        │
        ▼
regressão logística, 4 saídas: softmax(Wx + b) ─► Tier + pontuações
```

O modelo de embeddings é o `intfloat/multilingual-e5-small` (MIT, segundo os metadados de licença do model card), fixado numa revisão do Hugging Face e conferido por sha256 na construção da imagem. Escolhi um modelo multilíngue porque os Members também vão escrever em outros idiomas. Ele roda como exportação ONNX, sem torch na imagem. A cabeça é uma regressão logística multinomial com pesos balanceados por classe, num arquivo JSON de cerca de 21 KB. A força da regularização L2 é escolhida no conjunto de validação, pelo macro-F1.

O modelo lê 512 tokens: primeiro o último turno do usuário, depois os turnos anteriores no espaço que sobrar. O serviço nunca registra o texto dos prompts. A imagem tem cerca de 0,76 GB, dos quais 487 MB são o modelo.

## Os dados: 4.412 prompts e três modelos

Eu não tinha tráfego real para rotular, então os dados são sintéticos.

```
grade: Tier × 12 stacks × 4 formatos de prompt, 16 prompts por célula
       rodada 1: 4 Tiers (192 células) · rodada 2: complex e reasoning de novo (96 células)
        │  Qwen2.5-Coder-32B no Ollama, no laptop
        ▼
4.412 prompts distintos, cada um escrito para um Tier
        │  Claude Haiku 4.5, Batches API, sem saber esse Tier
        ▼
mesmo Tier, rótulo confiante: 2.406 ──────────────────────────┐
divergentes: 2.006 ─► Claude Opus 5.5 ─┬► confiante: 1.003 ───┴► 3.409 prompts rotulados
                                       └► em dúvida: 1.003, postos de lado
        ▼
avaliação 400 (100 por Tier) · validação 303 · treino 2.706
```

**Geração.** O Qwen2.5-Coder-32B, rodando localmente no Ollama, escreveu prompts do tipo que um desenvolvedor digita num assistente de programação, para cada Tier, em 12 stacks (Python e Django, serviços em Go, SQL e PostgreSQL, Terraform e YAML de Kubernetes e assim por diante) e 4 formatos: um pedido sem nada colado, um trecho de código colado, um erro colado, um turno de continuação. Um terço das células pedia 4 dos 16 prompts em português, espanhol, alemão ou francês. Cada requisição também pedia pelo menos três prompts que enganassem um palpite baseado no tamanho: prompts longos com um pedido fácil, prompts curtos com um pedido difícil.

**Segunda rotulagem.** O Claude Haiku 4.5 rotulou todos os prompts de novo sem saber para qual Tier tinham sido escritos, 20 prompts embaralhados por requisição, e disse se estava confiante.

**Arbitragem.** Um prompt conta como concordante quando o segundo rótulo bate com o Tier para o qual ele foi escrito e o rotulador estava confiante. Os outros 2.006 foram para o Claude Opus 5.5, que viu as duas sugestões e foi avisado de que qualquer uma podia estar errada.

**Custo.** A geração foi local e gratuita. A segunda rotulagem e a arbitragem custaram, juntas, US$ 1,88. O script se recusa a iniciar uma fase paga cuja estimativa leve o total além do orçamento, de 3 dólares por padrão.

## Onde os modelos discordaram

| Escrito para | Prompts | Concordaram, rótulo confiante | Enviados à arbitragem |
|---|---|---|---|
| simple | 745 | 627 (84,2%) | 118 (15,8%) |
| medium | 742 | 534 (72,0%) | 208 (28,0%) |
| complex | 1.451 | 747 (51,5%) | 704 (48,5%) |
| reasoning | 1.474 | 498 (33,8%) | 976 (66,2%) |
| **todos** | **4.412** | **2.406 (54,5%)** | **2.006 (45,5%)** |

**O modelo local não conseguiu escrever prompts difíceis sob encomenda.** Dos 1.474 prompts que ele escreveu como reasoning, o rotulador chamou 549 de reasoning e 537 de medium. Um exemplo típico: *"Getting `OperationalError: (1215, 'Cannot add foreign key constraint')` when running a migration. Any ideas?"* (um erro de chave estrangeira ao rodar uma migração, e "alguma ideia?"). A nota do gerador diz que ele "requires reasoning about database constraints and migration logic". O Haiku e o Opus chamaram de medium.

Por isso existe uma segunda rodada: o script pediu de novo complex e reasoning, com instruções mais rígidas (a de reasoning termina com "Not a request to explain a known concept or compare popular tools", ou seja, nada de pedir para explicar um conceito conhecido ou comparar ferramentas populares). A concordância em reasoning foi de 28,9% na rodada 1 para 38,7% na rodada 2, e em complex de 44,8% para 58,3%. Melhorou, e a maioria dos prompts de reasoning continuou em disputa. O gerador escreveu 1.474 prompts como reasoning, e o conjunto rotulado terminou com 505 prompts de reasoning.

**O árbitro ficou quase sempre com o rotulador.** O Opus escolheu o Tier do rotulador em 1.516 das 2.006 divergências (75,6%) e o do gerador em 360 (17,9%). Os dois grupos têm em comum 58 prompts em que ambos tinham dado o mesmo Tier, mas o rotulador não estava confiante. Nos outros 188, o Opus escolheu um terceiro Tier.

**E ele ficou confiante em exatamente metade**: 1.003 de 2.006. Alguns dos que ficaram em dúvida são um erro colado sem pergunta nenhuma, como um stack trace puro de `java.lang.NullPointerException`. Isso é simple ou medium? As definições dos Tiers descrevem o trabalho que a resposta exige, e um stack trace sozinho não diz qual é o pedido.

## O treino, e uma decisão que desfiz no mesmo dia

Os prompts rotulados foram divididos por Tier: 100 separados para avaliação, o resto 90/10 entre treino e validação. A avaliação mistura prompts concordantes (319) com prompts arbitrados com confiança (81), então não tem só os casos fáceis.

E os 1.003 veredictos em dúvida? Às 10h42 de 06/10/2026 fiz o commit da primeira resposta: eles treinam, mas nunca medem. Três horas e meia depois fiz o commit do contrário:

| Conjunto de treino | Acurácia na validação | Acurácia na avaliação |
|---|---|---|
| rótulos confiantes + 1.003 em dúvida | 79,2% | 79,3% |
| **só rótulos confiantes (2.706)** | **82,2%** | **80,0%** |

Ou seja, 37% a mais de prompts de treino deixaram o classificador pior nos dois conjuntos, e os prompts em dúvida agora ficam de lado. A leitura plausível é que um rótulo do qual o árbitro não tem certeza é ruído. Mas eu escolhi entre as duas linhas depois de ver as duas colunas, e a segunda coluna é o conjunto de avaliação. No momento em que o usei para escolher, ele deixou de ser um conjunto separado.

## Resultados: 80,0%, e o que tem dentro

Avaliação, 400 prompts, 100 por Tier: **acurácia de 80,0%, macro-F1 de 0,8034**. A meta escrita na tarefa era de pelo menos 80%.

| Tier | Recall | Precisão | F1 |
|---|---|---|---|
| simple | 0,82 | 0,891 | 0,854 |
| medium | 0,77 | 0,647 | 0,703 |
| complex | 0,76 | 0,792 | 0,776 |
| reasoning | 0,85 | 0,914 | 0,881 |

| Real ↓ / previsto → | simple | medium | complex | reasoning |
|---|---|---|---|---|
| simple | **82** | 16 | 2 | 0 |
| medium | 7 | **77** | 10 | 6 |
| complex | 2 | 20 | **76** | 2 |
| reasoning | 1 | 6 | 8 | **85** |

**Medium é o ralo.** O classificador previu medium 119 vezes e acertou 77. As 42 previsões erradas são mais da metade dos 80 erros dele.

**Minhas anotações dizem "almost every error is a neighbouring Tier" (quase todo erro é um Tier vizinho). A matriz diz 63 de 80.** Os outros 17 (21%) estão a dois ou três Tiers de distância, incluindo 6 prompts medium mandados para reasoning, 6 prompts reasoning mandados para medium e um mandado para simple. Em 44 dos 80 erros o Tier previsto é mais baixo que o rótulo; em 36 é mais alto.

**Latência** num Apple M4 Pro, 2 threads, uma requisição por vez: p50 de 7,3 ms, p95 de 20,9 ms, em 210 requisições (200 prompts de avaliação mais 10 entradas sintéticas que enchem os 512 tokens). Isso é sobretudo a latência de prompts curtos: o prompt mediano do conjunto tem 208 caracteres. Minhas anotações da tarefa registram uma entrada cheia de 512 tokens em cerca de 70 ms nativamente e cerca de 175 ms num contêiner Linux no mesmo laptop. A meta é um p95 de no máximo 800 ms numa c7i.xlarge, e eu nunca medi lá.

## O que os 80% não dizem

1. **Ele foi selecionado no conjunto de avaliação.** Com 320 acertos em 400, o intervalo de Wilson de 95% vai de 75,8% a 83,6%. A diferença de 0,7 ponto entre as duas escolhas de treino equivale a cerca de três prompts, bem dentro desse intervalo. "Bate a meta de 80%" é verdade pela largura de um prompt.
2. **Treino e avaliação vêm do mesmo gerador e da mesma grade.** Duplicatas exatas são removidas (o ID de um prompt é um hash do texto normalizado), mas nada verifica quase duplicatas. Dois prompts da mesma célula, um no treino e outro na avaliação, podem ser a mesma ideia com outras palavras.
3. **Os rótulos são rótulos de modelos.** O pipeline escreve uma amostra de 150 linhas para eu revisar: 25 prompts confiantes por Tier e 50 em dúvida. Minhas anotações da tarefa dizem que ela "came back without corrections" (voltou sem correções). O arquivo de revisão no repositório não tem correções nem rótulos registrados: a coluna `owner_tier` está vazia nas 150 linhas. De um jeito ou de outro, os rótulos vêm da concordância entre modelos de linguagem, com no máximo uma conferência humana de 150 linhas por trás.
4. **A avaliação deixa de fora os casos difíceis por construção.** Os 1.003 prompts em que o árbitro não teve certeza são 22,7% dos dados. O tráfego real não vai deixar os prompts ambíguos de fora.
5. **A cabeça foi treinada com prompts isolados.** Quando atende uma conversa, o gateway também envia os turnos anteriores. Nenhuma linha de treino ou de avaliação tem esse contexto.
6. **A curva de validação ainda estava subindo.** O macro-F1 na validação subiu a cada passo da grade de L2, de 0,7604 a 0,8201, e o valor escolhido é o maior da grade. Não testei um maior.
7. **O gateway nunca chamou este classificador.** Localmente o serviço do roteador roda e um script de ponta a ponta o verifica, mas a configuração do gateway aponta para um mock que responde com o Tier que o teste pede.
8. **Nada mede aquilo para que o roteador serve.** A tarefa que compara o Spend por requisição de uma Organization piloto antes e depois está aberta, e nada verifica se um prompt mandado para um Model mais barato recebeu uma resposta boa o bastante. Não posso afirmar que este roteador economiza dinheiro nem que preserva a qualidade.

O que os rótulos sintéticos compraram, sim: um pipeline reproduzível, um classificador cujos erros consigo ler numa tabela, uma medida de onde as minhas próprias definições de Tier são ambíguas, e uma linha de base a superar quando existir tráfego real, com consentimento.

## O resto do gateway, em resumo

O plano de dados é um proxy reverso de streaming em Go, escrito por mim. Três decisões dão a forma dele.

**Ele nunca traduz entre protocolos.** Requisições no formato Anthropic Messages só vão para upstreams que falam a API da Anthropic, requisições OpenAI só para os compatíveis com OpenAI, e os corpos são repassados byte a byte, exceto o campo `model`. Isso mantém intacto o `cache_control`, do qual o cache de prompts depende.

**Um pipeline fixo de 13 etapas**: ID da requisição, autenticar, carregar o contexto do Member, resolver o Model (inclusive `auto`), conferir o Profile, buscar o preço, gancho de admissão, escolher o upstream, repassar e transmitir, extrair o uso, medir, gancho de liquidação, emitir o registro do Request Log. Os tokens vêm do Zitadel, que federa o login Google ou Microsoft de cada Organization, de modo que o gateway valida um único emissor.

**Dinheiro é sempre um inteiro em microdólares.** A Quota funciona em reserva e liquidação: um script Lua no Valkey confere a Quota do Member e o teto da Organization e reserva uma estimativa pelo limite superior, num único passo atômico, e um segundo script liquida o Spend real. Uma Quota esgotada devolve HTTP 403, não 429, porque, pelas minhas anotações de design, o Claude Code e o Codex repetem automaticamente as requisições que recebem 429, e uma recusa viraria uma enxurrada de tentativas. O registro de cada requisição vai por SQS para uma tabela Postgres particionada por dia; se a fila estiver inacessível, o gateway guarda 10.000 registros por pod e depois se declara indisponível em vez de descartar algum.

Tudo isso roda num laptop: kind para o Kubernetes, floci emulando as APIs da AWS, e um provedor mock que transmite respostas prontas nos formatos Anthropic e OpenAI, com injeção de falhas. Uma Organization também pode ligar um classificador hospedado (Jev, da TypeSafe AI) com a própria chave; esse caminho só foi testado contra um stub.

## Testes de carga locais: o pior número mediu o emulador

Requisições com streaming pelo k6, direto no mock e depois pelo gateway:

| Rodada | Caminho | Requisições | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 20 streams, 10 s | direto no mock | 127.806 | 1,37 ms | 3,47 ms | 4,62 ms |
| 20 streams, 10 s | pelo gateway | 11.119 | 1,97 ms | 76 ms | 259 ms |
| 500 streams, 3 s | direto no mock | 74.983 | 13,1 ms | 53 ms | 77 ms |
| 500 streams, 3 s | pelo gateway | 3.740 | 37 ms | 16,9 s | 29,4 s |

Um p99 de 29,4 s parece um gateway quebrado. É o SQS do emulador: nessas rodadas o floci aceitava um lote de 10 registros do Request Log em 1,1 s, e em cerca de 8 s na fila criptografada com KMS quando havia acúmulo, o que limita a entrega local a mais ou menos 30 registros por segundo. O buffer enche em segundos, e o gateway então faz o que foi projetado para fazer: declara-se indisponível e espera, em vez de descartar um registro. Com 20 streams, a sobrecarga mediana foi de cerca de 0,6 ms.

Mesmo assim as rodadas levaram a duas correções. Um remetente virou 16 em paralelo. E o buffer agora é esvaziado no desligamento, dentro de um prazo de 45 s; antes, um pod que estava parando podia sair com registros ainda no buffer.

As primeiras rodadas do proxy de MCP foram piores, e aí a culpa era do gateway. Com 20 chamadas de ferramenta por segundo o p95 ficou entre 2 e 10 s, e com 100 o pod foi morto por falta de memória (OOMKilled). Um perfil de goroutines mostrou quase todas as chamadas esperando um upload para o S3. Os uploads saíram do caminho da requisição e as conexões com o upstream passaram a ser reaproveitadas; com 100 chamadas por segundo, o gateway então acrescentou 0,7 ms no p95 (2,10 ms contra 1,39 ms direto).

No `auto`, com 50 requisições por segundo, o p95 foi de 3,88 ms com um Model nomeado para 9,71 ms: cerca de 6 ms pelo caminho de classificação, contra um roteador mock que responde na hora. O p99 foi de 12,0 ms para 101,6 ms. O tempo de inferência do classificador de verdade não está em nenhum dos dois números.

Nada disso diz que o gateway é rápido em produção. As metas (sobrecarga de p99 abaixo de 25 ms até o primeiro byte com 500 streams em staging, no máximo 300 ms acrescentados pelo `auto` no p95 com o Router de verdade implantado) continuam abertas, e não há nenhuma rodada em staging.

## Onde o projeto está de fato

O repositório tem 178 commits em 9 dias ativos, de 24/09/2026 a 06/10/2026. Desses, 39 são merges, e todos os outros 139 trazem a linha de coautoria de um agente de programação. Foi construído a partir das especificações, com OpenSpec: 19 mudanças, 242 tarefas marcadas e 59 abertas. A maioria das abertas espera a mesma coisa, um ambiente real onde verificar. O runbook de ambientes diz sem rodeios: "planned, not executed. The AWS account doesn't exist yet and nothing has been applied" (planejado, não executado; a conta AWS ainda não existe e nada foi aplicado).

Sessões reais do Claude Code e do Codex CLI passaram pelo gateway local, contra o provedor mock. Nenhum provedor de verdade respondeu a uma requisição pelo gateway. E o README do próprio projeto ainda diz "planning. Nothing is implemented yet" (em planejamento, nada implementado), o que está desatualizado no outro sentido.

## O que eu diria a um time construindo isso

1. **Leia a licença antes de projetar em torno de um modelo.** Descobri que o meu, pela minha leitura, não servia para um produto hospedado quando o lado do gateway já estava construído para a interface daquele modelo.
2. **Use a divergência entre rótulos como medida.** Duas famílias de modelos concordaram em 54,5% dos prompts, e a taxa por Tier (de 84,2% até 33,8%) mostrou onde as minhas definições de Tier são vagas antes de existir qualquer classificador.
3. **Não confie num gerador para acertar uma classe difícil.** Quando pedi prompts de reasoning, o modelo local escreveu prompts que outro modelo chamou de medium quase tantas vezes quanto de reasoning. Uma segunda rodada mais rígida aumentou a concordância em cerca de 10 pontos. Não resolveu.
4. **Mais rótulos podem ser rótulos piores.** Acrescentar 1.003 veredictos em dúvida custou 3 pontos na validação. Teste dos dois jeitos, e decida só pela validação.
5. **Anote o momento em que você olhou para o conjunto de avaliação.** O meu é uma reversão no mesmo dia, visível em dois commits. O número continua útil. Só não é o que "conjunto separado" promete.
6. **Calcule a afirmação a partir da matriz.** "Quase todo erro é um Tier vizinho" era anotação minha. A matriz diz 79%.
7. **Pergunte o que o seu pior número local está medindo.** O meu mediu a fila de um emulador. As mesmas rodadas levaram a duas correções reais, então rode o teste de qualquer jeito.
8. **Mantenha "construído" separado de "verificado onde vai rodar".** Uma avaliação sintética e um teste de carga local valem a pena. Não são um piloto.

---

*Projeto: [github.com/ricardocunha/keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway). O roteador está em `router/`, as métricas em `router/model/metrics.json`, os testes de carga em `gateway/loadtest/RESULTS.md`. Modelos: intfloat/multilingual-e5-small (MIT segundo o model card) para os embeddings; Qwen2.5-Coder-32B (Apache-2.0 segundo as anotações do meu projeto) no Ollama para a geração; Claude Haiku 4.5 e Claude Opus 5.5 para os rótulos. As afirmações sobre outros projetos (Arch-Router, RouteLLM, Jev, Zitadel, floci, as licenças acima e o modo como o Claude Code e o Codex repetem requisições) são anotações minhas, registradas nos documentos do projeto em setembro e outubro de 2026; confira antes de se apoiar nelas. Rascunhos e a fonte de cada número: [github.com/ricardocunha/ensaios › articles/2027-02-keelgw-ai-gateway](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway).*
