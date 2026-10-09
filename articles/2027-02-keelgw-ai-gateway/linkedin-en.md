<!-- LinkedIn post (EN), ~1,400 characters. -->

I trained a prompt router for $1.88. It hit its 80% target. Here is what that number leaves out.

I'm building keelgw, an AI gateway for small businesses. For `model: auto` it classifies each prompt into 4 tiers, from simple to reasoning. The open router model I had planned on turned out, as I read its licence, not to be usable in a hosted product. So I trained a small CPU classifier in about a day, from synthetic data.

What I found:

→ A local open model wrote 4,412 prompts, Claude Haiku 4.5 relabelled them blind, Claude Opus 5.5 settled the 2,006 disputes. Total API spend: $1.88.

→ The first two models agreed on 54.5% of the prompts: 84.2% on "simple", 33.8% on "reasoning". The generator couldn't write hard prompts on demand.

→ 80.0% accuracy on 400 held-out prompts. But I made one training choice while looking at that set, and the gap it decided was about 3 prompts.

→ Adding the 1,003 labels the adjudicator wasn't sure of made the classifier worse.

And the honest part: the gateway has never called this router, nothing measures money saved or answer quality, and the project has only run on a laptop. My worst load-test number, a 29.4 s p99, measured the AWS emulator.

Synthetic labels bought a pipeline and a baseline, not evidence about real traffic.

Full write-up and code: [[LINK]]

#AI #LLM #MachineLearning #Evaluation #SyntheticData #OpenSource
