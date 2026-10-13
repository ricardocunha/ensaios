<!-- LinkedIn post (EN), ~1,300 characters. -->

My eye-scan RAG cited its sources. Then I shuffled the labels.

I built a multimodal medical RAG on a laptop: a local vision model (Qwen3-VL-8B) looks at a retinal photo next to the 3 most similar labelled cases from an archive (BiomedCLIP + Qdrant), diagnoses it, and cites the cases. 609 test images from a public dataset (RFMiD).

What I found:

→ Retrieval lifted the model's macro-F1 from 0.058 to 0.298. The plain nearest-neighbour vote over the same embeddings scored 0.341, in milliseconds.

→ Same retrieved photos, labels swapped for wrong ones: 0.056. The whole gain vanished. It came from reading the labels, not from comparing the photos.

→ An explanation agent with a citation check in code: 90% of explanations verified with true labels, 89% with shuffled ones. It checks that the citations match the text shown. It can't know the text is wrong.

→ Even with true labels, only 49% of verified citations named a label the image really had (12% with shuffled labels).

If your RAG "explains" itself, run a shuffled-labels test. It's one more run.

Brazil has a strong dataset for this, BRSET (16k photos, São Paulo), behind credentialed access. The harness is built so anyone with access can rerun it.

One dataset, one model: a research demo, not a medical device.

Full write-up and code: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-multimodal-medical-rag-eye

#AI #RAG #MedicalAI #Ophthalmology #LLM #Evaluation #Brazil
