<!-- LinkedIn post (EN). -->

My eye-scan RAG showed its sources. Then I changed the labels.

I made a medical RAG on my laptop. It uses a vision model (Qwen3-VL-8B) to look at a retinal photo and the three closest labeled cases from an archive (BiomedCLIP + Qdrant). It gives a diagnosis and shows the cases it used. I tested it with 609 images from the RFMiD dataset.

What I found:

Retrieval improved the model's macro-F1 from 0.058 to 0.298. Just using nearest-neighbour voting on the same data got 0.341 and was much faster.

When I used the same photos but gave them the wrong labels, the score dropped to 0.056. The improvement was from reading the labels, not from looking at the photos.

I made an explanation agent that checks citations in code. It verified 90% of explanations with true labels and 89% with shuffled labels. It only checks if the citations match the text. It does not know if the text is wrong.

Even with true labels, only 49% of the verified citations gave a label the image really had. With shuffled labels, it was 12%.

If your RAG explains itself, try a shuffled-labels test. Just run it one more time.

Brazil has a good dataset for this called BRSET (16,000 photos from São Paulo). You need credentials to get it. The test setup lets anyone with access run it again.

This is just one dataset and one model. It is a research demo, not a medical device.

Full write-up and code:
Article: https://github.com/ricardocunha/ensaios/blob/main/articles/2027-01-multimodal-medical-rag-eye/article-en.md
README: https://github.com/ricardocunha/ensaios/blob/main/articles/2027-01-multimodal-medical-rag-eye/README.md

#AI #RAG #MedicalAI #Ophthalmology #LLM #Evaluation
