<!-- Post LinkedIn (PT-BR). ~1.300 caracteres. Anexar o carrossel (mesmo roteiro do EN, traduzido). -->

A LangChain lançou o smithtune há dois dias. Coloquei ele para ler CNH. 🇧🇷🪪

O smithtune transforma os traces do seu agente no LangSmith num modelo aberto ajustado: curadoria → LoRA na Fireworks/Baseten → avaliação por replay → deploy, tudo por uma CLI.

O plano era fazer fine-tuning de um modelo de OCR com ele. Aí li o código-fonte:
→ a v0.1 filtra qualquer trace que tenha imagem
→ os modelos base vêm de uma lista fixa (Qwen, Kimi, DeepSeek, GLM)

Então dividi o problema em dois:
1️⃣ Reader: 3 modelos de OCR abertos (Chandra 2, PaddleOCR-VL, Qwen3.5-9B) comparados em zero-shot; o de 0,9B ajustado com LoRA em CNHs sintéticas, num MacBook
2️⃣ Extractor: um agente com ferramentas (dígito verificador, correção de OCR, regras de validade). Claude Sonnet 5 como Teacher, destilado com o smithtune num Qwen3.5-9B

Resultados:
📉 Um modelo de OCR de 0,9B ajustado num MacBook: 99,8% nos meus cartões sintéticos, e depois rejeitou 48 de 70 CNHs REAIS como "não é CNH". Os dados sintéticos ensinaram a ler, e também como uma CNH "se parece". 🔁 Rodada 2: as mesmas 2.293 imagens, só que mais variadas (layouts, scans, rotações) → +20 pontos em cartões reais, agora à frente do Qwen3.5-9B zero-shot, 8× mais rápido. Rodada 3: o modelo de visão só lê, e a decisão "é CNH?" vem do texto → 81% nos cartões reais, 0/70 rejeitadas por engano. O maior salto veio de mudar uma decisão de lugar, não de mais dados.
[[RESULT: 1 linha Student vs Teacher, custo]]

Bônus: medi quantas vezes o "conselho de agentes" do smithtune concorda com o gabarito → [[RESULT: %]]

Artigo completo + código (100% dados sintéticos, nenhum documento real) 👇
[[LINK]]

#IA #MachineLearning #LLM #OCR #FineTuning #LangChain #OpenSource #Brasil
