<!-- Post LinkedIn (PT-BR), cerca de 2.100 caracteres (limite 3.000). Anexar o carrossel (mesmo roteiro do EN, traduzido). -->

A LangChain lançou há pouco o smithtune, uma CLI de fine-tuning do LangSmith. Na primeira semana, coloquei o smithtune para ler CNH. 🇧🇷🪪

O smithtune transforma os traces do seu agente no LangSmith num modelo aberto ajustado: curadoria → LoRA na Fireworks/Baseten → avaliação por replay → deploy, tudo por uma CLI.

O plano era fazer fine-tuning de um modelo de OCR com ele. Aí li o código-fonte:
→ a v0.1 filtra qualquer trace que tenha imagem
→ os modelos base vêm de uma lista fixa (Qwen, Kimi, DeepSeek, GLM)

Então dividi o problema em dois:
1️⃣ Reader: 3 modelos de OCR abertos (Chandra 2, PaddleOCR-VL, Qwen3.5-9B) comparados em zero-shot; o de 0,9B ajustado com LoRA em CNHs sintéticas, num MacBook
2️⃣ Extractor: um agente com ferramentas (dígito verificador, correção de OCR, regras de validade). Um Teacher de pesos abertos (DeepSeek-V4-Pro, MIT) cujas melhores execuções o smithtune curou, destilado num Student local de 8B

Resultados:
📉 Um modelo de OCR de 0,9B ajustado num MacBook fez 99,8% nos meus cartões sintéticos, e depois rejeitou 48 de 70 CNHs REAIS como "não é CNH". Os dados sintéticos ensinaram a ler, e também como uma CNH "se parece".
🔁 Rodada 2: as mesmas 2.293 imagens, só que mais variadas (layouts, scans, rotações) → +20 pontos em cartões reais.
✅ Rodada 3: o modelo de visão só lê, e "é CNH?" é decidido pelo texto → 81% em cartões reais, 0/70 rejeitadas por engano. O maior salto veio de mudar uma decisão de lugar, não de mais dados.
🎯 O Student local Qwen3-8B: de 46% para 81% de acertos exatos depois de uma época de LoRA num MacBook, contra 89% do Teacher via API, com custo zero por documento.

No caminho: troquei de Teacher depois de ler os termos de licença, fiquei sem crédito na Fireworks no meio da avaliação e achei três bugs silenciosos em ferramentas, cada um só visível como um número que não podia ser verdade.

Artigo completo + código (100% dados sintéticos, nenhum documento real) 👇
[[LINK]]

#IA #MachineLearning #LLM #OCR #FineTuning #LangChain #OpenSource #Brasil
