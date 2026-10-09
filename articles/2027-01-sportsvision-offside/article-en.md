---
title: "Five correct fixes, zero offside calls"
subtitle: "A football offside pipeline on real footage: the detector, the ball model and the motion gate each worked on their own terms, the system stayed silent, and the last blocker was a counting bug in the cheap, deterministic layer"
platforms: Medium, dev.to, Hashnode
status: DRAFT — numbers final, each mapped to its source in the sportsvision repo (SOURCES.md, repo at 6d694fd)
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside
project: https://github.com/ricardocunha/sportsvision
---

# Five correct fixes, zero offside calls

Offside is one of the few refereeing decisions that is plain geometry. At the moment the ball is played, sort the defenders along the pitch, take the second-last one, and compare a coordinate. A model has nothing to learn in that part.

So I built [SportsVision](https://github.com/ricardocunha/sportsvision). You give it a match clip, and for every pass it should return a decision with the geometry behind it: the offside line, the margin in metres, the frames it used and a confidence you can recompute. It runs as a real pipeline (queues, workers, autoscaling, traces) on a laptop.

For four weeks, on real footage, it never reached a verdict. For most of that time it returned nothing at all: no offside, no onside, not even "I can't tell".

The short version:

- **Deciding is cheap and seeing is expensive.** In the benchmark, the whole rules stage took 0.023 s and perception took 100.2 s, on the same 10-second video.
- **Four fixes upstream of the rules each worked by their own measure, and the deployed pipeline still emitted nothing.** A fine-tuned player detector. A dedicated ball model that took ball visibility from 47 % to 93 %. A motion gate that cut the worst frame-to-frame ball jump from 12.14 m to 1.63 m. And deploying the trained models, which had sat on disk while the cluster ran the old one.
- **The fifth fix was in the cheap part.** Possession was established in 0 of 599 frames, because "3 consecutive frames" counted raw frames and the cluster only looks at every second one. After the fix: 242 of 599, and the first two verdicts the engine has produced. Both say onside.
- **There is still no accuracy figure, and no offside call.** I have no labelled clips, so I can't say whether either verdict is right. And the fix was verified by re-running the rules on the artifacts of the last cluster run, not by a new full cluster run.

Every number here comes from the project's docs, decision records (ADRs) and commit messages; [SOURCES.md](SOURCES.md) maps each one to a file or a commit.

## What the system is

![Three boundaries. Perception (Python, GPU or CPU) turns video segments into detections, embeddings and pitch keypoints. State (Python, CPU) turns those into tracks, team clusters and pitch coordinates in metres. Decision (Go, deterministic) runs pass detection, the offside line and the confidence-to-outcome mapping, and writes events and evidence to PostgreSQL and S3.](images/02-perception-state-decision.svg)

The design is that split:

- **Perception** (Python) is the only layer that runs a neural network: an RF-DETR detector finds players, goalkeepers, referees and the ball, one video segment at a time.
- **State** (Python) sees the whole video: ByteTrack tracks, teams by clustering appearance embeddings, the ball trajectory, and positions in metres through a homography.
- **Decision** (Go) is deterministic. It finds possession, kicks and passes, draws the line, and maps a confidence to an outcome. Its tests need no GPU, no network and no Python.

No layer answers a question that belongs to a later one. The detector never outputs "offside"; the tracker never outputs "pass".

Around that sit five deployables (`sv api`, `sv segmenter`, `vision-worker`, `tracker`, `sv rules`), six SQS queues with their dead-letter queues, PostgreSQL and an object store, on a three-node kind cluster. S3 and SQS come from [Floci](https://github.com/floci-io/floci), an emulator that the real Terraform AWS provider can provision. KEDA scales the four queue consumers from zero on queue depth. Go and Python share no database; they share JSON Schema contracts.

The stack is local-first for a practical reason: the project was built largely with coding agents working in parallel git worktrees, and I wanted them to deploy, break and rebuild everything with no real cloud credential anywhere. Nothing has run on AWS, and the decision record about AWS compatibility is the one still marked "Proposed".

One box in the diagram is not real yet: the pitch-keypoint model is untrained (about 5.4 hours per epoch on this laptop, against a 120-epoch cap). Pitch coordinates come from a manual calibration file, and only one clip has one.

## Deciding is cheap, seeing is expensive

Benchmark of 2026-09-16, on an Apple M4 Pro with CPU-only inference in the cluster, median of 5 runs (min–max), every run a cold start from zero replicas:

| | |
|---|---|
| End to end, one 10 s video | 134.6 s (132.6–140.8) |
| Six 8 s videos at once, p50 / p95 | 195.2 s / 269.5 s |
| Throughput, six videos on two vision replicas | 80.2 videos/hour (78.4–82) |
| Detector, ONNX on CPU, one replica | 1.70 fps (1.67–1.71) |
| Stage means, one video: segment / perceive / track / rules | 3.8 s / 100.2 s / 29.4 s / **0.023 s** |

Perception costs more than 4,000 times the decision it feeds.

Three caveats. The 0.023 s is the whole `rules` stage as the worker observes it, not a microbenchmark of the engine, and it comes from runs that produced zero events, so the stage had nothing to render or store. These medians were taken with the 640 px COCO-pretrained detector; the fine-tuned model that replaced it runs at 384 px, so the table is not comparable to later runs. And "videos per hour" describes one laptop.

The part that doesn't depend on the laptop: across the five burst runs, all 30 jobs finished, with 0 failures, 0 dead letters, 0 restarts and 0 OOM kills.

## "I can't tell" is an answer, with nine reasons

![Outcomes of an offside check. Every confirmed pass becomes a PASS or an OFFSIDE_CHECK. A check is DETECTED when margin and confidence clear both thresholds, REVIEW_REQUIRED when the margin is inside the review band or the confidence sits between the two thresholds, and INCONCLUSIVE when a gate fires.](images/07-event-outcomes.svg)

Every confirmed pass produces one event with one of three statuses. `DETECTED`: a verdict the engine stands behind. `REVIEW_REQUIRED`: a verdict a person should confirm, because the margin is under 0.3 m or the confidence is in the middle band. `INCONCLUSIVE`: the engine declines, with one of nine machine-readable reasons: `NO_HOMOGRAPHY`, `BALL_NOT_VISIBLE`, `RECEIVER_MISSING`, `DIRECTION_UNKNOWN`, `DEFENDER_MISSING`, `GOALKEEPER_MISSING`, `SET_PIECE`, `TEAM_UNASSIGNED`, `LOW_CONFIDENCE`.

An `INCONCLUSIVE` event is a result, not an error. It names what perception failed to supply.

That design has a hole, and this article is about it. The three outcomes exist only for a **confirmed pass**. A kick with no passer, or with no receiver, is dropped inside the engine by a plain `continue`. It emits nothing and logs nothing. So a run can end with zero events and zero reasons.

## The footage

The project uses three Creative Commons clips from Wikimedia Commons (CC BY-SA 4.0). Everything below was measured on one: 39 seconds of an under-17 women's international, 1280×720 at 29.97 fps, 1,170 frames, from a low camera behind the goal line that pans across half the pitch. The cluster demo uses a 20-second cut of it. None of the clips has labelled passes.

## Fix 1: fine-tune the player detector

The first runs used a COCO checkpoint, which has no goalkeeper or referee class, and the engine needs the goalkeeper. On 2026-09-25 I fine-tuned RF-DETR on a public four-class football dataset. On its validation split it reached mAP@50-95 0.372 (mAP@50 0.742). That is a detection figure, not an offside figure.

Players and team clustering visibly improved. Events: 0. The ball was visible in 547 of 1,170 frames (47 %), in a trajectory broken into 34 pieces, and 60 detected kicks became no event at all.

## Fix 2: a dedicated ball model

A second RF-DETR, trained only on a 4,948-image ball dataset:

| Prototype run, 1,170 frames | Shared detector | Dedicated ball model |
|---|---|---|
| Ball visible | 547 (47 %) | 1,086 (93 %) |
| Trajectory fragments | 34 | 2 |
| Kicks detected | 60 | 86 |
| Events | 0 | 0 |

Recall doubled and the output didn't change. The reason was in the kinematics the engine computed from that trajectory: a median ball speed of 15.2 m/s, a maximum of 185 m/s (666 km/h), and 958 of 1,127 frames above the 6 m/s² kick threshold. The clip read as one continuous kick. Raising the threshold tenfold moved the kick count only from 86 to 64.

About one detection in ten landed on some other object 100 to 200 px away and came back. Acceleration is a second derivative, so each excursion made a kick. A confidence threshold couldn't separate them: mean confidence was 0.636 after a big jump against 0.716 after a calm step. The detector was confidently wrong.

With the ball jumping around, a possession holder was defined in 49 of 1,170 frames. Of the 86 kicks, 79 had no passer and 7 no receiver. None reached the offside evaluation.

## Fix 3: a motion gate, in metres

The tracker now carries the last accepted ball position forward and rejects an observation a football couldn't have reached in the elapsed time. It works in metres, not pixels, because perspective makes pixels-per-metre vary several-fold across the frame. A rejected frame is written as "ball not visible" and never interpolated, so the engine's `BALL_NOT_VISIBLE` gate can do its job.

| Same artifacts, tracker re-run | No gate | Gate on |
|---|---|---|
| Worst frame-to-frame jump | 12.14 m | 1.63 m |
| Kicks | 86 | 54 |
| Ball visible | 93 % | 60 % |
| Kicks reaching evaluation | 0 | 1 |

The visibility drop is the cost: 380 observations rejected, and more of the clip marked as unknown.

That one kick became the project's first event, at frame 282: `INCONCLUSIVE`, reason `RECEIVER_MISSING`. The engine found a kick, a passer, a receiver, their team and the attacking direction, and then declined, because the receiver had no position near the kick. It isn't a verdict. It showed the pass path could run, on the prototype, which processes every frame.

Review found two bugs in the gate. A frame with no homography was treated like a ball off the pitch, which rejected all 36 detections in an uncalibrated test fixture; the clip I measured on has a valid homography in every frame, so it could never have shown this. And the allowed radius grew with the age of the last accepted position, so a detector bouncing between two objects was rejected for about a second and then accepted: the gate switched itself off in the one case it was written for.

In the same decision record I wrote down a remedy I refused: loosening the possession thresholds until events appeared. With nothing labelled, I couldn't tell a correct event from a confident accident. Keep that in mind for fix 5.

## Fix 4: deploy what I had trained

On 2026-10-08 I found that the fine-tuned detector had never been exported. The Helm chart still pointed at the COCO model, and the trained checkpoint sat on disk while every cluster run used the old one. The missing work was an export and an upload.

With it deployed, on the 20-second clip: 152 tracks, a 65/64 team split, 11 goalkeeper assignments, 16 kicks. Events: 0. The ball was visible in 34.7 % of processed frames, in 26 fragments whose median length was one frame.

The obvious lever was ball slicing: a second ball pass over overlapping tiles. I measured it, then deployed the dedicated ball model without it:

| 20 s clip, on the cluster | Ball visible | Longest run | Kicks | Runtime | Events |
|---|---|---|---|---|---|
| Four-class detector | 34.7 % | 56 frames | 16 | 85 s | 0 |
| + slicing | 38.0 % | 27 frames | 22 | 273 s | 0 |
| Dedicated ball model, no slicing | 59.0 % | 94 frames | 28 | 94 s | 0 |

Slicing raised the visible ratio and halved the longest continuous trajectory, at 3.2 times the runtime. A pass is confirmed by following the ball from the strike to a receiver, so continuity is what counts, and slicing traded it for scattered sightings. It stays off, with the measurement written next to the flag. The dedicated model was the better trade, and still gave 0 events.

## Fix 5: the bug was in the cheap layer

At this point the cluster found 28 kicks, placed players on the pitch for 99.9 % of detections and had a valid homography in every frame. A small diagnostic test that reports which gate dropped each kick showed that every kick was dropped for the same reason: no passer. Possession was established in **0 of 599 frames**.

There were two causes.

**The radius was a guess.** A player holds the ball when within `possession.radius_m` of it, and that was 1.2 m. The number was meant to come from calibration on labelled clips, which has never run. Measured on the clip, the nearest player to the ball is 2.15 m away at the median, and within 1.2 m in only 8.5 % of frames. I raised it to 2.5 m, argued from the error budget (the calibration's own reprojection error plus locating a player from a bounding box) and not fitted. The frames with a team player inside the radius went from 15 to 142.

Possession stayed at exactly 0.

**The count was wrong.** `min_frames: 3` required three consecutive video frames. The cluster runs perception on every second frame (`SV_FRAME_STRIDE=2`), and the frames in between are filled with empty placeholders so that indexing by frame number stays cheap. Candidates therefore alternated between a track id and nothing. No run could exceed length 1. Possession was impossible at any stride above 1, for any radius.

The engine's test suite was green the whole time, so nothing in it ran possession at a stride above 1, and the prototype processes every frame. The fix counts a run in observations: frames the pipeline never looked at neither break a run nor add to it.

| On the artifacts of the last cluster run | Before | After (`rules-1.1.0`) |
|---|---|---|
| Frames with possession | 0 of 599 | 242 of 599 (40.4 %) |
| Kicks with a passer | 0 | 16 of 28 |
| Kicks reaching evaluation | 0 | 2 |
| Events | 0 | 2 |

```
frame 460  PASS  REVIEW_REQUIRED  ONSIDE  conf 0.60
frame 472  PASS  DETECTED         ONSIDE  conf 0.71
```

Those are the first verdicts the engine has produced on real footage. What they are, exactly:

- They come from `sv rules --local` on the artifacts of the last cluster run. No full cluster run has been made with the fix.
- Whether "onside" is right at either frame is unknown. There is no ground truth.
- Both are `PASS` events, the type used when Law 11.1 settles the call without a line (the receiver is in their own half, or level with or behind the ball). The system has still never called an offside.
- The 0.71 clears a detection threshold of 0.7 that has never been calibrated.
- Ten days after refusing to loosen possession thresholds, I changed one. What I can say for it: the radius alone produced nothing, and the cause that mattered was a bug. The radius is still provisional.

A regression test now covers both sides of `min_frames` at stride 2.

## What the discarded runs revealed

**A stall the benchmark caused.** One burst run was discarded because a job that normally takes about 135 s took about 13 minutes while the cluster sat idle. `sv api` scales on request rate, and the load generator polls each job every two seconds: about three requests per second for six videos, enough to scale the API up and down three times in thirty minutes. One scale-down killed a replica holding a fan-in message, which stayed invisible until its visibility timeout expired. Nothing was lost, and no alert fired, because the stall was shorter than the alert threshold. The benchmark was driving the autoscaler it was measuring. The benchmark page names the three excluded runs and why.

**A CPU cap Kubernetes couldn't see.** A demo run took 457 s against 214 s published. The vision worker held a flat 1.00 core of its 2-core limit with 0 throttle events in 3,741 cgroup periods. The cause was a `docker update --cpus=1` left on the kind node that hosts the vision pods. The node still advertised all 14 CPUs, and the pod's own counters stayed clean. A thread sweep on the capped node said one thread beat two, so I changed threads and batch size along with the scaling trigger, and the next run took 637 s. That slower run exposed the cap. Uncapped, two threads are 1.87 times one (564 against 1,056 ms per frame). It cost a day. And `docker update --cpus=0` does not clear the cap; `--cpu-quota=-1` does.

**The host.** A demo failed right after its preflight passed: the worker's startup probe timed out 25 times over 11 minutes with 76 % of host RAM free, while macOS Photos analysis used 314 % CPU. Later, restoring the observability stack moved inference from 564 to 856 ms per frame. Since then I compare per-frame rates inside one run, not wall-clock times across runs.

## Other things that broke

- **Team clustering with k=2** split "players" from "everyone else": 228 of 243 tracks in one team. Kit purity was 0.57 with k=2 and 0.95 with k=3, so the default is now teams + 1.
- **ONNX Runtime on CPU was slower than torch on CPU** on macOS with default session options: 26.1 against 41.1 fps.
- **The first run on kind failed silently.** A vision worker was OOM-killed, and a killed process records nothing: no error row, no log line, no span. The job sat in `SEGMENTED` with a null error while its messages drained into a dead-letter queue nobody read. The dead-letter watcher and the alerts come from that run.
- **Missing IAM permissions were invisible locally.** The Go services resolve every dead-letter queue at startup, and the policy only granted the source queues. On AWS none of them would have started. Floci enforces no IAM.
- **The chaos scripts check node provider IDs**, not just the context name. During that work, my current kube context was a production EKS cluster the whole time. Four of the five experiments pass; the poison-message one has not completed a full run.

## What this does not show

No accuracy. No labelled clips exist, so there is no precision, no recall and no calibrated threshold: the numbers in the rules file are placeholders. One clip, one manual calibration, and a homography that drifts while the camera pans. The engine judges offside position at the moment of the pass (Law 11.1) and nothing else, and locating a player from a bounding box is estimated to understate a leaning attacker by 0.3 to 0.6 m, at least as much as the review margin. Nothing has run on AWS. The benchmark medians predate the current model. And the two verdicts have no full cluster run behind them yet.

## What I'd tell a team building this

1. **Make "nothing happened" explain itself.** My uncertainty design covered confirmed passes and nothing before them, so a run that emits nothing looked the same as a run with nothing to emit. Counting why each kick was dropped found both causes. Had those counts been on every run's result, the first run would have shown them, before the detour through the detector, the tiling and the ball model.
2. **Test the deterministic layer at the sampling the deployed pipeline uses.** The engine has many tests, and none of them ran possession at stride 2.
3. **Measure what the next stage consumes.** Ball visibility went up twice without helping: once because the new detections were wrong, once because they were scattered. Precision and continuity were what mattered.
4. **Check what is deployed.** A trained model sat on disk for almost two weeks while the cluster ran the old one.
5. **Name the runs you exclude, and check whether your harness is steering the system.** The discarded stall is where the scalability page's open design question comes from.
6. **On kind, read the node's cgroup before believing a throughput number.** Kubernetes will not tell you a node is capped.
7. **Without labels, a verdict is a milestone, not a result.** Two events after four weeks of none is progress on the plumbing. It says nothing yet about offside.

---

*Project: [github.com/ricardocunha/sportsvision](https://github.com/ricardocunha/sportsvision) (Apache-2.0), including the [benchmarks](https://github.com/ricardocunha/sportsvision/blob/main/docs/benchmarks.md), the [evaluation page](https://github.com/ricardocunha/sportsvision/blob/main/docs/evaluation.md) and the [decision records](https://github.com/ricardocunha/sportsvision/blob/main/docs/adr/README.md). Footage: three Wikimedia Commons clips, CC BY-SA 4.0, by NaBUru38 (2018 FIFA U-17 Women's World Cup, New Zealand vs Canada, clips 21 and 27) and Manchesterunited1234 (FC Versailles 78 v. AS Nancy-Lorraine, 2024-03-08, clip 157); no frames are reproduced here. Training data: Roboflow Universe football-players-detection and football-ball-detection, CC BY 4.0. Models: RF-DETR and SigLIP (Apache-2.0), ByteTrack via supervision (MIT). Diagrams are the project's own. Not a VAR system and not compared with one. Drafts and the source of every number: [github.com/ricardocunha/ensaios › articles/2027-01-sportsvision-offside](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside).*
