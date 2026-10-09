# Five correct fixes, zero offside calls

**Status:** drafts complete (EN, EN Medium, PT-BR, LinkedIn EN/PT-BR); numbers final and mapped to their sources; links pending publication · **Branch:** `article/2027-01-sportsvision-offside` · **Target date:** 2027-01-22

A field report on [SportsVision](https://github.com/ricardocunha/sportsvision), a local-first pipeline that turns football video into evidence-backed offside decisions: a Python perception and state plane (RF-DETR, ByteTrack), a deterministic Go rules engine, JSON Schema contracts, SQS queues on Floci, KEDA and kind. In the 2026-09-16 benchmark the whole rules stage took 0.023 s against 100.2 s for perception (134.6 s end to end for a 10 s video; 80.2 videos/hour for a burst of six 8 s videos on two CPU replicas), with the older 640 px COCO detector, on runs that produced zero events. On real footage four fixes upstream of the rules each worked on their own terms (detector fine-tune to a best validation mAP@50-95 of 0.372; dedicated ball model, visibility 47 % → 93 %; a ball motion gate, worst jump 12.14 m → 1.63 m and one `INCONCLUSIVE` event on the prototype; deploying the trained models to the cluster) and the cluster still emitted nothing. The last blocker was a counting bug in the rules layer: possession held in 0 of 599 frames because `min_frames: 3` counted raw frames at stride 2. After the fix (`rules-1.1.0`): 242 of 599 frames and the first two verdicts, both `ONSIDE`, verified with `sv rules --local` on cluster artifacts, not by a full cluster run, with no ground truth. No accuracy figure exists, no clip is labelled, thresholds are uncalibrated, and nothing has run on AWS. Every number is mapped to a file or commit in [SOURCES.md](SOURCES.md).

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) · Medium version: [article-en-medium.md](article-en-medium.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Project repo | https://github.com/ricardocunha/sportsvision |
| Sources | [SOURCES.md](SOURCES.md) |
| Images | [images/](images/) (two of the project's own diagrams, Apache-2.0; no footage) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]
