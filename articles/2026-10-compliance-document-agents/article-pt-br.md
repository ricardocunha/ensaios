---
title: "Agentes de compliance que sabem quando não têm certeza"
subtitle: "Revisando contratos públicos brasileiros com Docling, MCP e Pydantic AI, e medindo quando o agente deve passar o caso para uma pessoa"
platforms: Medium, LinkedIn Articles, TabNews, dev.to (pt)
status: RASCUNHO — substituir todos os [[RESULT: …]] antes de publicar
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents
---

# Agentes de compliance que sabem quando não têm certeza

Um agente de compliance que acerta 80% das vezes não serve para nada se você não sabe *quais* são os 80%. Alguém precisa revisar tudo de novo, e o agente não economizou nada. O agente útil é o que diz *"deste aqui eu não tenho certeza"* nos casos certos.

Este artigo constrói um e mede. Os documentos são contratos reais de compras públicas do PNCP, o Portal Nacional de Contratações Públicas. As regras vêm da Lei 14.133/2021. A arquitetura é a do vídeo *"5 AI Agents Projects to Build in 2026"* (projeto nº 4): **Docling** para ler PDFs digitalizados, um **servidor MCP** para expô-los e **Pydantic AI** para os agentes. Tudo roda em um notebook, com um modelo aberto de 8B.

Todos os números abaixo vêm do `docs/RESULTS.md` do repositório. Todos os bugs que encontrei também estão lá, porque foi deles que veio a maior parte do aprendizado.

## A montagem

```
PDF do contrato (PNCP) ─► Docling (+ OCR Apple Vision, pt-BR) ─► seções, notas por página
                                     │
                         Servidor MCP: parse_document · get_section · search_document · verify_quote
                                     │
          Revisor (Pydantic AI, uma execução por regra) ─► Finding{veredito, citação, confiança}
                                     │
          Auditor (tenta refutar violações) + checagens determinísticas ─► manter ou escalar
```

- **Oito regras** da Lei 14.133, cada uma ligada a um artigo que conferi no texto oficial: cláusula de objeto, vinculação ao edital, preço e pagamento, índice de reajuste (art. 92, § 3º), dotação orçamentária, foro (art. 92, § 1º), limite da garantia (art. 98) e limites de vigência (arts. 106 e 107).
- **Gabarito:** 60 contratos sintéticos na estrutura usual, com 0 a 2 **violações plantadas** cada. Também há **casos difíceis em conformidade**: variantes legais que parecem suspeitas, como garantia de 8% *com* a justificativa que o art. 98 exige, vigência de 60 meses ou um foro escrito como "Comarca de <sede>".
- **Modelo:** Qwen3-8B 4-bit em um servidor mlx-lm local. Custo zero por documento, o que importa quando cada experimento são centenas de execuções do agente.

## Parte 1: o OCR é bom em contratos, e o Docling sabe quando erra?

Digitalizações de verdade são mais raras no PNCP do que eu esperava. Na minha primeira amostra, 6 de 8 PDFs sem camada de texto eram **páginas em branco**, uploads quebrados. Então montei um benchmark com respostas conhecidas: peguei 20 contratos nascidos digitais, de 10 órgãos, guardei a camada de texto como gabarito e os transformei em "digitalizações" só de imagem, em quatro níveis de degradação.

| Nível | Palavras recuperadas | Números recuperados | `ocr_score` do Docling |
|---|---|---|---|
| limpo (300 dpi) | 95,1% | 91,6% | 0,994 |
| leve (200 dpi) | 96,6% | 96,6% | 0,994 |
| médio (150 dpi) | 95,5% | 91,7% | 0,993 |
| pesado (110 dpi, inclinado, desbotado) | 48,0% | 39,6% | 0,852 |

Meço os **números** separadamente porque, em um contrato, um número errado (valor, percentual, prazo) pesa mais que uma palavra errada.

**A própria confiança do Docling encontra as páginas ruins?** Quando o `ocr_score` fica abaixo de 0,95, a página é mesmo ruim em 94% dos casos. Mas esse alerta pega **só 34% das páginas ruins**; o resto parece bom para o Docling. Em páginas limpas, por exemplo, o CEP no rodapé do papel timbrado saiu 46304-053 em vez de 88304-053, com `ocr_score` = 1,0. Nota baixa é um sinal útil; nota alta não garante nada.

**Quatro dos meus primeiros "erros de OCR" eram bugs da minha medição.** Cada um apareceu como um número que não fazia sentido:
1. O Docling tira a numeração dos parágrafos ("5.3") do texto e a guarda em um campo `marker`. Parecia erro de OCR, e esses números também sumiam do que o agente lia, sendo justamente o que uma constatação precisa citar.
2. Cabeçalhos e rodapés são "mobília" para o Docling e ficam fora do corpo por padrão.
3. Algumas camadas de texto quebram "14.3" em duas linhas, então a resposta certa do OCR contava como errada.
4. Os uploads em branco citados acima.

## Parte 2: o revisor, e por que as ferramentas importaram mais que o prompt

O revisor é um agente Pydantic AI com **uma execução por regra**. Isso é mais fácil para um modelo de 8B e dá a cada regra sua própria constatação, para escalar ou manter. Ele lê o contrato só pelas ferramentas MCP e precisa citar a evidência literalmente.

**Mudar a saída da ferramenta funcionou onde mudar o prompt não funcionou, duas vezes.**

- ***Foro.*** Em um contrato da Receita Federal ("É eleito o Foro de CURITIBA"), o revisor disse *violação* **3 vezes em 3, com confiança 0,95**. A unidade contratante fica em Curitiba, então a cláusula está correta. O agente nunca olhou o preâmbulo, onde as partes são qualificadas. Mandar ler o preâmbulo não mudou nada. Devolver o preâmbulo dentro da saída de `parse_document` resolveu: **3 de 3 corretos**.
- ***Vinculação.*** No primeiro baseline, essa regra gerou **10 falsos alarmes em 20 contratos**. O agente buscava "vinculação", minha ferramenta de busca exigia palavras exatas e o contrato dizia "vincula-se". A busca voltava vazia e o agente concluía que a cláusula não existia. A correção foi casar pelo radical das palavras.

**O modelo extrai, o código decide.** Nas regras de garantia e de vigência, o modelo de 8B citava "12 (doze) meses" corretamente e depois dizia que isso passava de "5 anos". Essas duas regras somaram 23 falsos alarmes em 40 constatações. Agora o modelo só **extrai** os valores (percentual, citação da justificativa, meses, se o serviço é contínuo) e dez linhas de Python aplicam a lei. É a mesma divisão do meu artigo anterior: o modelo lê, as regras decidem.

Juntas, as duas correções levaram o acerto de **74,4% para 95,0%** e os falsos alarmes **de 34 para 6**. Os 11 casos difíceis em conformidade agora estão todos certos, contra 4 antes. O recall caiu um pouco: de 22 para 21 das 23 violações encontradas.

| Revisor | Violações encontradas (recall) | Precisão | Falsos alarmes | Casos difíceis certos | Citações literais |
|---|---|---|---|---|---|
| Baseline (PDFs com texto) | 95,7% | 39,3% | 34 | 4/11 | 134/146 |
| + busca por radical, limites decididos em código | 91,3% | **77,8%** | **6** | **11/11** | 150/153 |

## Parte 3: quando o agente deve escalar?

Em texto limpo, a **confiança declarada pelo modelo** quase não carrega informação. No baseline, 88% das constatações tinham confiança ≥ 0,95, com 80,7% de acerto nelas contra 74,4% no total. Além disso, três execuções da mesma resposta errada **concordaram 3 em 3**: concordância sozinha não pega um erro que o modelo comete sempre.

Por isso o escalonamento usa sinais que o modelo não consegue contornar:

- **discordância** entre 3 amostras;
- uma **citação que não está no documento** (checada em código);
- **nota de OCR baixa** nas páginas de onde vem a evidência;
- um **auditor** que tenta refutar cada violação com a própria busca, e cuja objeção só conta se vier com uma contracitação literal.

Rodei cada contrato e regra 3 vezes e fiquei com a maioria, nos PDFs com texto e nos mesmos contratos como digitalização pesada:

| Escalar quando… | Texto: escalado | Texto: acerto no que fica | Texto: erros pegos | Pesado: escalado | Pesado: acerto no que fica | Pesado: erros pegos |
|---|---|---|---|---|---|---|
| nunca | 0% | 97,5% | — | 0% | **47,5%** | — |
| amostras discordam | 11% | **99,3%** | **75%** | 33% | 44,9% | 30% |
| nota de OCR < 0,9 | 0% | 97,5% | 0% | 77% | 59,5% | **82%** |
| confiança declarada < 0,9 | 7% | 97,3% | 0% | 77% | 73,0% | 88% |
| auditor contesta | 13% | 99,3% | 75% | 51% | 66,7% | 69% |
| qualquer um dos acima | 18% | 99,2% | 75% | 93% | **100%** | **100%** |

**Em texto limpo, o sinal é a discordância.** Ela escala 11% das decisões, pega três quartos dos erros e deixa 99,3% de acerto no restante.

**Em digitalização pesada o revisor desaba, e a discordância não percebe.** O acerto cai para 47,5%. Das 137 checagens em conformidade, ele apontou 80 violações: não encontra a cláusula no texto embaralhado e diz que ela não existe, *sempre*, então as amostras concordam. Os sinais que funcionam aqui são a **nota de OCR** e, curiosamente, a própria confiança do modelo, que percebe o texto embaralhado. Combinada, a política manda 93% das decisões sobre digitalizações pesadas para uma pessoa e acerta os 7% restantes. Para um documento tão ruim, é o comportamento correto.

**O auditor pega falsos alarmes, e discute demais.** Em texto, contestou todos os 13 falsos alarmes, e também 19 das 59 violações reais, com citações que existem no documento mas não sustentam a objeção (ele "refutou" uma violação de vigência de 72 meses citando "72 (setenta e dois) meses"). A checagem literal prova que a citação é real, não que é pertinente. Como uma contestação só escala e nunca reverte, o custo é tempo de revisão, não decisão errada.

**Nenhum sinal de escalonamento funciona em todo lugar.** A discordância pega erros em texto limpo e falha em digitalização ruim; a nota de OCR faz o contrário. Use os dois.

## Parte 4: contratos reais

[[RESULT: 20 contratos reais do PNCP, rotulados à mão: concordância com o revisor, o que ele erra em texto real]]

## O que eu diria a um time que vai construir isso

1. **Meça o OCR nos seus documentos, com gabarito.** Ele foi bem até a degradação média e desabou na pesada. A confiança do Docling é um alerta confiável quando está baixa, e diz pouco quando está alta.
2. **Conserte as ferramentas antes do prompt.** Os dois erros sistemáticos do revisor eram problemas de informação: um preâmbulo que faltava e uma busca que não reconhecia uma forma verbal. Mais instruções não resolveram nenhum dos dois.
3. **Não deixe um modelo de 8B fazer conta com limite legal.** Ele extrai os valores; o código decide.
4. **Não dependa de um único sinal de escalonamento.** A discordância pega erros em texto limpo e falha em digitalização ruim; a nota de OCR faz o contrário. Combine checagens que o modelo não consegue contornar: discordância, citação literal, qualidade do OCR e um segundo agente adversário.

---

*Ideia do vídeo "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (projeto nº 4). Código, pipeline de dados e todos os números: [github.com/ricardocunha/ensaios › articles/2026-10-compliance-document-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents). Os contratos são públicos; o repositório não os redistribui, e as citações aqui têm nomes omitidos. É uma bancada de testes, não aconselhamento jurídico.*
