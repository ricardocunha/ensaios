# Sources

Where every number and factual claim in the drafts comes from. All paths are in
[ricardocunha/sportsvision](https://github.com/ricardocunha/sportsvision) at commit `6d694fd`
(2026-10-08), read on 2026-10-09. `file:line` is a line in that commit; a bare hash is a commit
message (`git show -s <hash>`). Nothing was re-run for this article: the drafts only report what the
repository already records. The proofread of 2026-10-09 rechecked every reference against the
repository at `2abb0df` (2026-10-09); the only files changed since `6d694fd` are `docs/demo.md` and
`scripts/demo.sh`, so the line numbers below still hold.

The same numbers are used in `article-en.md`, `article-en-medium.md`, `article-pt-br.md` and the two
LinkedIn posts (PT-BR with decimal commas).

## 1. The system and the stack

| Claim in the drafts | Source |
|---|---|
| Output per pass: offside line, margin in metres, frames used, recomputable confidence | `README.md:10-12`, `README.md:77-81` |
| Three layers: Perception (Python, only layer with a neural network, per segment), State (Python, whole video), Decision (Go, deterministic); no layer answers a later layer's question | `docs/adr/0006-perception-state-decision-boundaries.md:17-23` |
| Engine tests need no network, no files and no Python | `docs/adr/0006-…:43`, `README.md:151-153` |
| Five deployables, six queues, six dead-letter queues, PostgreSQL, object store | `README.md:43-44`, `docs/adr/README.md:16` |
| kind with 1 control-plane + 2 workers ("three-node") | `docs/benchmarks.md:133`, `docs/adr/README.md:17` |
| Floci emulates S3/SQS and is provisioned by the real Terraform AWS provider | `README.md:50-52`, `docs/adr/0001-local-first-cloud-emulation.md:11` |
| KEDA scales the four queue consumers from zero on queue depth; `sv api` never below 1 | `docs/scalability.md:24-48` |
| Go and Python share JSON Schema contracts, no database | `README.md:48-50`, `docs/adr/0018-…:14` |
| Built largely by coding agents in parallel git worktrees; no real credential for them | `docs/adr/0001-local-first-cloud-emulation.md:9` |
| Nothing has run on AWS; ADR-0014 is the only record still `Proposed` | `docs/adr/README.md:22`, `docs/adr/README.md:37`, `docs/benchmarks.md:58` |
| Pitch-keypoint model untrained, about 5.4 h per epoch against a 120-epoch cap; homography from a manual calibration; only one clip has one | `docs/evaluation.md:12`, `eval/reports/README.md:122-124` |
| Models and licences: RF-DETR, SigLIP (Apache-2.0), ByteTrack via `supervision` (MIT) | `README.md:356-358`, `eval/DATA_SOURCES.md:53-57` |

## 2. Benchmark (2026-09-16, COCO 640 px model)

Disclosure block: `docs/benchmarks.md:128-148` (date, Apple M4 Pro, Docker VM 14 CPU / 7.75 GiB,
`rfdetr-nano-640.onnx`, `rules-1.0.0`, clip cut to 10 s single / 8 s burst, stride 2, median of 5
runs, cold start included).

| Number | Source |
|---|---|
| End to end, one 10 s video: 134.6 s (132.6–140.8) | `docs/benchmarks.md:175` |
| Six videos, p50 195.2 s / p95 269.5 s | `docs/benchmarks.md:176` |
| 80.2 videos/hour (78.4–82) on two vision replicas | `docs/benchmarks.md:193` |
| Detector 1.70 fps (1.67–1.71), ONNX CPU, one replica | `docs/benchmarks.md:158` |
| Stage means 3.8 / 100.2 / 29.4 / 0.023 s | `docs/benchmarks.md:182` |
| "More than 4,000 times" | `docs/benchmarks.md:276` (100.2 / 0.023 ≈ 4,357) |
| 0.023 s is the whole `rules` stage, not an engine microbenchmark | `docs/benchmarks.md:283-287` |
| Those runs produced zero events | `docs/benchmarks.md:55` |
| Not comparable to runs on the 384 px fine-tuned model | `3f05894`; `deploy/helm/sportsvision/values.yaml:47-50` |
| Burst ledger: 5 runs × 6 = 30 jobs `ANALYZED`, 0 failures, 0 dead letters, 0 restarts, 0 OOM kills | `docs/benchmarks.md:195-197`, `docs/scalability.md:222-225` |

## 3. Outcomes (ADR-0011)

| Claim | Source |
|---|---|
| Three statuses and when each is produced | `docs/adr/0011-explicit-uncertainty-outcomes.md:17-21` |
| Nine reason codes (listed) | `docs/adr/0011-…:51` |
| One event per kick frame; `PASS` when Law 11.1(a)/(b) settles it (own half, or level with or behind the ball) | `docs/adr/0011-…:50`, `README.md:172-175` |
| Review margin 0.3 m; `c_det` 0.7, `c_review` 0.4 | `internal/rules/rules.default.yaml:72`, `:84-85` |
| Thresholds are uncalibrated placeholders | `docs/adr/README.md:35` |
| Outcomes exist only for a confirmed pass; dropped kicks are a plain `continue` that emits and logs nothing | `docs/adr/0019-ball-motion-consistency-gate.md:38`; `internal/rules/engine.go:116,126,132` |

## 4. Footage

| Claim | Source |
|---|---|
| Three Wikimedia Commons clips, CC BY-SA 4.0; authors NaBUru38 (clips 21, 27) and Manchesterunited1234 (clip 157) | `eval/DATA_SOURCES.md:11-13` |
| Main clip: 39 s, 1280×720, 29.97 fps, 1,170 frames, low camera behind the goal line, pans across half the pitch | `eval/DATA_SOURCES.md:11`, `eval/reports/README.md:12-14` |
| Cluster demo uses a 20 s cut (two segments, 300 processed frames at stride 2) | `docs/benchmarks.md:215`, `docs/adr/0020-…:9` |
| The 20 s cut is 599 frames, of which the cluster processes every second one (300) | `3f05894` ("104 of 300 frames", "frames=599"); `870b2f5` |
| No labelled clips | `docs/evaluation.md:11` |
| "Four weeks": first prototype run with zero events 2026-09-10; first verdicts 2026-10-08 | `eval/reports/README.md:8,138`; `870b2f5` |

## 5. The chain

| # | Claim | Source |
|---|---|---|
| 1 | Player fine-tune: best val mAP@50-95 0.372; a detection figure on the Roboflow validation split, not an offside figure | `docs/evaluation.md:12`; `92738a3` |
| 1 | Best val mAP@50 0.742; trained on 2026-09-25. The two figures are each the run's best and come from different epochs (see section 9), so the drafts say "best figures", not one checkpoint's pair | `3f05894`; `deploy/helm/sportsvision/values.yaml:45` |
| 1 | Players and team clustering visibly improved; still zero events; ball visible in 547 of 1,170 frames; 60 kicks, no event | `92738a3`; `docs/adr/0019-…:13-19` |
| 2 | Ball dataset of 4,948 images | `eval/DATA_SOURCES.md:48`, `docs/adr/0019-…:11` |
| 2 | Ball visible 547 (47 %) → 1,086 (93 %); fragments 34 → 2; kicks 60 → 86; events 0 → 0 | `docs/adr/0019-…:13-19`; `5dceef8` |
| 2 | Speed p50 15.2 m/s, max 185 m/s = 666 km/h; 958 of 1,127 frames over the 6 m/s² threshold; threshold 6 → 60 moves kicks 86 → 64 | `docs/adr/0019-…:24-26,38` |
| 2 | About one detection in ten lands 100–200 px away and returns | `docs/adr/0019-…:48` |
| 2 | Mean confidence 0.636 vs 0.716; "confidently wrong" | `docs/adr/0019-…:52` |
| 2 | Possession defined for 49 of 1,170 frames; 79 of 86 kicks no passer, 7 no receiver; none reach evaluation | `docs/adr/0019-…:38` |
| 3 | Gate in metres, tolerance + max speed × dt, gated frame written as not visible and not interpolated | `docs/adr/0019-…:65-71`; `5dceef8` |
| 3 | Worst jump 12.14 m → 1.63 m; kicks 86 → 54; visible 93 % → 60 %; kicks reaching evaluation 0 → 1; 380 observations rejected | `docs/adr/0019-…:106-120` |
| 3 | First event: `OFFSIDE_CHECK` at frame 282, `INCONCLUSIVE(RECEIVER_MISSING)`; kick, passer, receiver, team and direction resolved; prototype, host-native, stride 1 | `docs/adr/0019-…:125`; `docs/evaluation.md:14` |
| 3 | Review bug 1: no-homography frames gated, all 36 detections of the no-keypoints fixture rejected; the measured clip has valid H in every frame | `docs/adr/0019-…:69`, `:121-124`; `5dceef8` |
| 3 | Review bug 2: radius grew with anchor age; rejected for about a second, then accepted | `docs/adr/0019-…:69`; `5dceef8` |
| 3 | Loosening possession thresholds was considered and refused | `docs/adr/0019-…:57`, `:87` |
| 4 | Fine-tuned detector never exported; chart pointed at the COCO export; "an export and an upload" | `3f05894` |
| 4 | "Almost two weeks": trained 2026-09-25, deployed 2026-10-08 (13 days) | `3f05894` (message and commit date) |
| 4 | 20 s clip with the fine-tuned detector: 152 tracks, 65/64 team split, 11 goalkeeper assignments, 16 kicks, 0 events; ball visible 104/300 = 34.7 %, 26 fragments of median length one frame | `3f05894` |
| 4 | Slicing: 34.7 % → 38.0 %, fragments 26 → 31, longest run 56 → 27, kicks 16 → 22, 85 s → 273 s (3.2×), 0 events; left off | `caa6047`; `deploy/helm/sportsvision/values-kind.yaml:174-181` |
| 4 | Dedicated ball model, unsliced: 59.0 % visible, longest run 94, kicks 28, 94 s, 0 events | `821cf32` |
| 5 | 28 kicks, players placed for 99.9 % of detections, valid homography on every frame, every kick dropped for no passer, possession in 0 of 599 frames | `870b2f5` |
| 5 | Radius 1.2 m was uncalibrated; median nearest player 2.15 m; within 1.2 m in 8.5 % of frames; raised to 2.5 m from the error budget, provisional | `870b2f5`; `internal/rules/rules.default.yaml:7-16` |
| 5 | Frames with a team player inside the radius 15 → 142, possession still 0 | `870b2f5` |
| 5 | `min_frames: 3` counted consecutive raw frames; at stride 2 every other frame is empty; no run above length 1; impossible at any stride above 1 for any radius | `870b2f5`; `internal/rules/possession.go:54` |
| 5 | Cluster stride is 2 | `deploy/helm/sportsvision/values-kind.yaml:182` |
| 5 | Diagnostic test that reports which gate dropped each kick located both causes | `870b2f5`; `docs/backlog.md:23` |
| 5 | 0/599 → 242/599 (40.4 %); kicks with a passer 0 → 16 of 28; reaching evaluation 0 → 2; events 0 → 2 | `870b2f5` |
| 5 | Frame 460 `PASS REVIEW_REQUIRED ONSIDE` conf 0.60; frame 472 `PASS DETECTED ONSIDE` conf 0.71 | `870b2f5` |
| 5 | Verified with `sv rules --local` on the artifacts of the last cluster run; no ground truth; correctness unknown | `870b2f5` |
| 5 | Regression test `TestPossessionSurvivesFrameStride` at stride 2 | `870b2f5`; `internal/rules/components_test.go:745` |
| 5 | Before the fix, no test in the rules package built a video with stride gaps | `git grep -i stride 870b2f5^ -- internal/rules` returns nothing; `870b2f5` ("the engine's own scenario tests" build a `Video` without `NewVideo`) |
| 5 | "Ten days after": ADR-0019 dated 2026-09-28, fix committed 2026-10-08 | `docs/adr/0019-…:4`; `870b2f5` |

## 6. Discarded runs and machine faults

| Claim | Source |
|---|---|
| Discarded burst run: job of about 135 s took about 13 minutes with the cluster idle | `docs/scalability.md:235-244` |
| `sv api` scaled 1→2→1 three times in thirty minutes by its request-rate trigger, driven by the benchmark's own polling (one GET every 2 s per video, about 3 requests/s for six videos) | `docs/scalability.md:53-60`, `:238-239` |
| A replica holding a `segment.perceived` delivery was killed; the message waited out its visibility timeout; no loss, no dead letter | `docs/scalability.md:239-244` |
| No alert fired because the stall was below the threshold | `docs/scalability.md:260-264` |
| Three burst runs excluded by name | `docs/benchmarks.md:199-202`, `:340-344` |
| The stall is an open design question in the backlog (not on the scalability page, which analyses it) | `docs/benchmarks.md:341-343`; `docs/backlog.md:15`, `:24` |
| 457 s against 214 s published | `docs/adr/0020-one-segment-per-vision-replica.md:9` |
| Flat 1.00 core of a 2-core limit, 0 throttle events in 3,741 cgroup periods; `docker update --cpus=1` on the vision kind node; node still advertises 14 CPUs | `docs/adr/0020-…:34-45` |
| Capped sweep favoured one thread; threads, batch and trigger changed; 637 s; that run exposed the cap | `docs/adr/0020-…:47-57`, `:125-137` |
| Uncapped: 564 ms vs 1,056 ms per frame, 1.87× | `docs/adr/0020-…:53-57` |
| "It cost a day of misdiagnosis" | `docs/adr/0020-…:106-107`; `docs/backlog.md:18` |
| `--cpus=0` does not clear the cap, `--cpu-quota=-1` does | `docs/adr/0020-…:62-63` |
| Demo failed after preflight passed: startup probe timed out 25 times over 11 minutes, 76 % of host RAM free, macOS Photos analysis at 314 % CPU | `a1bfe97` |
| Restoring the observability stack moved inference from 564 to 856 ms per frame | `docs/adr/0021-balanced-keyframe-segment-cuts.md:175-180` |

## 7. Other things that broke

| Claim | Source |
|---|---|
| KMeans(2) put 228 of 243 tracks in one team; kit purity 0.57 (k=2) vs 0.95 (k=3); default k = teams + 1 | `eval/reports/README.md:95-99` |
| ONNX Runtime CPU 26.1 fps vs torch CPU 41.1 fps (detector fps, 150-frame prototype excerpt) on macOS, default session options | `eval/reports/README.md:44-46`, `:55-57` |
| First kind run failed silently: OOM-killed vision worker, no step row, no log, no span; job stayed `SEGMENTED` with `last_error` null; messages went to the dead-letter queue | `docs/adr/0018-dead-letter-handling-and-job-failure-semantics.md:9`; `README.md:253-256` |
| Dead-letter watcher and alerts exist because of it | `docs/adr/0018-…:17-21`; `7fa46e3` |
| Missing dead-letter IAM permissions; Go roles resolve every dead-letter queue at startup; invisible because Floci enforces no IAM | `9b558cc`; `docs/reliability.md:174-186` |
| Chaos scripts delete pods and restart StatefulSets and refuse to run unless every node carries a `kind://` providerID; "during this wave the current context was in fact a production EKS cluster the whole time"; the guard fails closed | `docs/reliability.md:123-128` |
| Four of five chaos experiments pass; poison-message not completed | `docs/reliability.md:134-140`, `:165-173` |

## 8. Limits

| Claim | Source |
|---|---|
| No accuracy figure; no labelled clips; thresholds uncalibrated | `docs/evaluation.md:11,15`; `docs/adr/README.md:35` |
| Homography drifts badly while the camera pans | `eval/reports/README.md:104-112`; `docs/adr/0019-…:48` |
| Law 11.1 position only; bounding-box localisation estimated to understate a leaning attacker by 0.3–0.6 m | `README.md:202-204`; `docs/adr/0011-…:9` |

## 9. Stale or contradictory project docs, and what was chosen

| Topic | Conflict | Chosen |
|---|---|---|
| Detector in use | `README.md:26-29`, `:210-214`, `:370` and `docs/evaluation.md:12` say the deployed detector is the COCO checkpoint. `3f05894` (2026-10-08) deployed the fine-tuned one. | The commit and `values.yaml:42-51`. The drafts say COCO for the 2026-09-16 benchmark and fine-tuned from 2026-10-08. |
| Rules version | `README.md:193` says `rules-1.0.0`; `rules.default.yaml:4` says `rules-1.1.0`. | `rules-1.1.0`, with `rules-1.0.0` only for the benchmark conditions. |
| "Zero events" | `README.md:28`, `:217` and `docs/benchmarks.md:55` say every run produced zero events. ADR-0019 (one `INCONCLUSIVE`, prototype) and `870b2f5` (two verdicts, `--local`) are newer. | The newer records, each with its own conditions. |
| "Never emitted an event on real footage" (`870b2f5`) vs the frame-282 event (ADR-0019) | Both true for their path: the frame-282 event came from the host-native prototype at stride 1; the cluster path had emitted none. | Drafts call frame 282 "the project's first event … on the prototype" and frames 460/472 "the first verdicts". |
| Fragments / gaps after fix 1 | `92738a3` says 108 runs, 34 gaps over the limit, "roughly 35 pieces"; ADR-0019 table says 33 gaps and 34 fragments. | ADR-0019 table (34 → 2). Gap counts left out. |
| Training length of the player model | `docs/evaluation.md:12` says early-stopped after epoch 46; `3f05894` and `values.yaml:45` say 111 epochs. The git-ignored `data/models/rfdetr-football/metrics.csv` on the author's machine has 111 rows covering epochs 0-46, so 111 looks like a row count. In it `val/ema_mAP_50_95` peaks at 0.372 (epoch 45) and `val/ema_mAP_50` at 0.742 (epoch 43). | Epoch counts left out. The two mAP figures are given as the run's best figures, not as one checkpoint's pair. |
| Peak ball speed | 185 m/s (engine kinematics) vs 364 m/s (raw diagnostic), `docs/adr/0019-…:24-36`. The ADR says not to compare them. | Only the engine figure (185 m/s, 666 km/h), in fix 2. The gate's 363.9 → 48.8 m/s is left out. |
| Homography drift in pixels | 455 px / 164 px (`eval/reports/README.md:107-108`) vs 484 px / 144.9 px (`docs/adr/0019-…:48`), different runs. | No number; "drifts while the camera pans". |
| Player position from the box | "bottom-centre" (`docs/adr/0011-…:9`) vs "centroid rather than their feet" (`870b2f5`). | "from a bounding box", no further detail. |
| Kick counts on the first runs | 76 (prototype, stride 1, COCO) vs 65 (cluster, stride 2), `docs/evaluation.md:13`. | Not used. |
| ADR count, test counts | `README.md:230`, `:349-352` say 18 ADRs and give test counts from 2026-09-22; there are 21 ADRs now and more tests. | No counts in the drafts. "The engine has many tests" is unquantified (62 `func Test…` in `internal/rules` by `grep` at `6d694fd`, not quoted). |
| Number of fixtures | `docs/evaluation.md:20-21` says "~20 scenario directories"; `eval/fixtures/offside-v1/` holds 17. | Not used. |

## 10. Not verified, and how the drafts word around it

| Item | Status | Wording used |
|---|---|---|
| Whether `ONSIDE` is correct at frames 460 and 472 | Unknown: no labelled footage (`870b2f5`). | "Whether 'onside' is right at either frame is unknown." |
| A full cluster run with `rules-1.1.0` | Not done; the figures are from `sv rules --local` on saved cluster artifacts (`870b2f5`). | Said in the short version, in fix 5 and in the limits. |
| The 0.023 s stage "had nothing to render or store" | Inferred: the stage includes rendering and upserts (`docs/benchmarks.md:283-285`) and those runs had zero events (`:55`). | Stated as a consequence of zero events. |
| What the engine's tests covered before the fix | Checked in code, not deduced: at `870b2f5^` nothing under `internal/rules` mentions a stride, and the scenario tests build a `Video` without `NewVideo`. That the suite was "green the whole time" is not recorded anywhere. | "before the fix, no test in the rules package built a video with the gaps a stride leaves". The "green the whole time" sentence was cut. |
| The production EKS kube context | Stated in `docs/reliability.md:126-128` as "the current context", not as "my" context. The brief's lead that the scripts *ran against* the wrong context is **not** in the repo; the repo says the guard exists because of that risk and that it fails closed. | The full EN and PT-BR articles quote the doc's wording next to the guard, so it cannot be read as the scripts having run against production. Not used in the Medium version or on LinkedIn. |
| The dedicated ball model's sidecar had `label_names ['ball', 'ball']` (`3f05894`), and it was deployed the same day (`821cf32`) with no note on whether that was resolved | Unresolved in the repo. | Left out of the drafts. |
| The `model_version` collision fix has unit coverage but no cluster run behind it (`821cf32`) | Stated in the commit. | Left out for length; the limits say the verdicts have no full cluster run behind them. |
| 300 s visibility timeout vs a stall of about 780 s (`docs/scalability.md:242`, `:261`) | The doc gives both and does not explain the difference. | "until its visibility timeout expired", no number. |
| Kick breakdown "12 without a passer, 13 without a receiver, 1 dribble, 2 judged" (`docs/backlog.md:23`) | It is an example string in a backlog note, consistent with `870b2f5` (16 of 28 with a passer, 2 judged) but not presented as a measurement. | Not used. |
| The receiver at frame 282 projecting 448 px outside the frame (`3bd5c3d`) | Recorded, with the commit's own caveat that it is the weak case (position from after the pass). | Not used. |
| "A wrong tuning decision that I had to revert" (Medium) | `SV_ORT_THREADS` and `SV_BATCH_SIZE` were changed to 1 and changed back (`docs/adr/0020-…:84-85`). | As stated. |

No VERIFY or RESULT placeholders are left in the drafts.

## Proofread 2026-10-09

An independent pass over every draft against the sportsvision repository at `2abb0df`.

Facts corrected:

- Engine tests: "no GPU, no network and no Python" became "no network, no files and no Python",
  which is what ADR-0006 and the README say (EN, PT-BR).
- Player fine-tune: "reached mAP@50-95 0.372 (mAP@50 0.742)" read as one checkpoint's pair. The two
  are each the run's best figure, from different epochs, so the drafts now say "best figures" (EN,
  Medium table, PT-BR, README).
- Lesson 5 said the stall's open design question is on the scalability page. It is in the backlog;
  the scalability page analyses the stall (EN, PT-BR).
- Lesson 3 said ball visibility "went up twice". It rose three times with no event (47 → 93 %,
  34.7 → 38.0 %, 34.7 → 59.0 %); the lesson now names the two cases it draws on and gives no count
  (EN, Medium, PT-BR).
- ONNX against torch: the 26.1 and 41.1 fps are detector fps on the prototype, now said (EN, PT-BR).
- README: 80.2 videos/hour is for a burst of six 8 s videos, and the benchmark used the older 640 px
  COCO detector; both now said. The `INCONCLUSIVE` event is marked as a prototype result.
- Medium: "all measured on one clip" hid that fixes 4 and 5 ran on the cluster's 20 s cut (599
  frames, every second frame). Now said. The full EN and PT-BR say where the 599 comes from.
- The frame-282 event: "no position near the kick" became "no known position at the kick" (the
  gate is a window of frames, not a distance).

Voice and overclaiming:

- "The engine's test suite was green the whole time, so nothing in it ran possession at a stride
  above 1" was an inference. Replaced by what the code shows (see section 10).
- "On 2026-10-08 I found that…" (the commit does not say when it was found) became "Until
  2026-10-08…".
- "a remedy I refused" became "a remedy I deliberately did not take", ADR-0019's wording.
- "It cost a day" became "a day of misdiagnosis", the record's wording; Medium's "a wrong tuning
  decision that I had to revert" became "a tuning change that was made and then reverted".
- The production-EKS line was reworded to the reliability page's own statement, next to the guard.
- LinkedIn (both): the 0.023 s line now says the runs emitted no events, and the first event is
  marked "not a verdict".

PT-BR: the same changes; the section "As imagens" and the footer label became "Os vídeos" /
"Vídeos" (no images of the footage exist in the article); "1,87 vez uma" and "A máquina hospedeira"
were reworded.

Checked and left as they were: every other number in sections 2 to 8, the "four weeks" (2026-09-10
to 2026-10-08, 28 days), "almost two weeks" (13 days), "ten days" (2026-09-28 to 2026-10-08), "more
than 4,000 times" (100.2 / 0.023 ≈ 4,357), "halved" (56 → 27 frames), 3.2 times (273 / 85), the
footage attribution against `eval/DATA_SOURCES.md:11-13`, and the two SVGs, which are byte-identical
to the project's `docs/architecture/diagrams/svg/` files and embed no raster image.

## Author decisions, 2026-10-09

Applied to the drafts after the proofread, from the author's answers. No project code was touched.

- **Production EKS sentence:** cut (full EN and PT-BR). The chaos-scripts bullet went with the trim below.
- **Length:** "Other things that broke" reduced to two items (the silent first run on kind; the IAM permissions the emulator hid), and the host-CPU paragraph ("The host") removed from "What the discarded runs revealed" (EN, PT-BR). The chaos scripts' provider-ID guard was then restored as a third item at the author's request, without the production-context sentence (source: `docs/reliability.md`, the guard paragraph and the experiment results). Removed material, still in the project's docs: team clustering with k=2, ONNX Runtime vs torch on CPU, the macOS Photos / observability-stack contention. Their rows above no longer back any sentence in the drafts.
