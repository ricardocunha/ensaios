---
title: "Five correct fixes, zero offside calls"
subtitle: "A football offside pipeline on real footage: the detector, the ball model and the motion gate each worked on their own terms, the system stayed silent, and the last blocker was a counting bug in the cheap, deterministic layer"
platforms: Medium (short version; the full version is article-en.md, for dev.to / Hashnode)
status: DRAFT — numbers final, each mapped to its source in the sportsvision repo (SOURCES.md, repo at 6d694fd)
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside
project: https://github.com/ricardocunha/sportsvision
---

# Five correct fixes, zero offside calls

Offside is one of the few refereeing decisions that is plain geometry. At the moment the ball is played, sort the defenders, take the second-last one, and compare a coordinate.

So I built [SportsVision](https://github.com/ricardocunha/sportsvision): you give it a match clip, and for every pass it should return a decision with the offside line, the margin in metres and a confidence you can recompute. It runs as a real pipeline (queues, workers, autoscaling) on a laptop.

For four weeks, on real footage, it never reached a verdict. For most of that time it returned nothing at all.

The short version: four fixes upstream of the rules each worked by their own measure, and the deployed pipeline still emitted nothing. The fifth fix was for a counting bug in the cheap, deterministic rules layer. After it, the engine produced its first two verdicts, both "onside". I have no labelled clips, so I can't say whether they are right, and there is no accuracy figure anywhere in this project.

## The system

Three layers, and no layer answers a question that belongs to a later one:

- **Perception** (Python): an RF-DETR detector finds players, goalkeepers, referees and the ball.
- **State** (Python): tracks, teams, the ball trajectory, and positions in metres on the pitch.
- **Decision** (Go): deterministic. Possession, kicks, passes, the offside line, the outcome.

Around them: five deployables, six SQS queues with dead-letter queues, PostgreSQL, a kind cluster, KEDA scale-to-zero, and Floci emulating S3 and SQS. Go and Python share JSON Schema contracts, not a database. The project was built largely with coding agents in parallel git worktrees, which is why it is local-first: no real cloud credential exists for them to misuse. Nothing has run on AWS.

## Deciding is cheap, seeing is expensive

Benchmark of 2026-09-16 (Apple M4 Pro, CPU inference in the cluster, median of 5 cold runs): one 10-second video took 134.6 s end to end. Of that, perception took 100.2 s and the rules stage **0.023 s**.

Two caveats. The 0.023 s is the whole rules stage on runs that produced zero events, not a microbenchmark of the engine. And those medians used the older 640 px COCO model, so they are not comparable to later runs.

## "I can't tell" is an answer

Every confirmed pass produces one event: `DETECTED`, `REVIEW_REQUIRED`, or `INCONCLUSIVE` with one of nine machine-readable reasons (`BALL_NOT_VISIBLE`, `RECEIVER_MISSING`, `GOALKEEPER_MISSING` and so on).

The hole: those outcomes exist only for a *confirmed* pass. A kick with no passer or no receiver was dropped inside the engine by a plain `continue`. So a run could end with zero events and zero reasons, and mine did.

## The chain

All measured on one Creative Commons clip: 39 seconds, 1,170 frames, a panning camera behind the goal line. Fixes 1 to 3 ran on the prototype, which processes every frame. Fixes 4 and 5 ran on the cluster, on a 20-second cut (599 frames) at every second frame.

| # | Fix | By its own measure | Events |
|---|---|---|---|
| 1 | Fine-tune the player detector | best val mAP@50-95 0.372, mAP@50 0.742 | 0 |
| 2 | Dedicated ball model | ball visible 47 % → 93 %, fragments 34 → 2 | 0 |
| 3 | Ball motion gate, in metres | worst jump 12.14 m → 1.63 m, kicks 86 → 54 | 1, `INCONCLUSIVE` (prototype) |
| 4 | Deploy the trained models to the cluster | ball visible 34.7 % → 59.0 %, kicks 16 → 28 | 0 |
| 5 | Count possession in observations | possession 0 → 242 of 599 frames | 2 verdicts, both onside |

**Fix 2** is the instructive one. Recall doubled and nothing changed, because the trajectory was physically impossible: a median ball speed of 15.2 m/s, a maximum of 185 m/s (666 km/h), and 958 of 1,127 frames above the kick threshold. About one detection in ten landed on another object and came back, and each excursion made a "kick". A confidence threshold couldn't separate them. The detector was confidently wrong.

**Fix 3** rejects ball positions a football couldn't have reached. It cost visibility (93 % → 60 %), with more of the clip marked as unknown, and produced the project's first event, on the prototype: `INCONCLUSIVE`, `RECEIVER_MISSING`, at frame 282. It isn't a verdict. Review also found two bugs in the gate, one of which switched it off in the exact case it was written for.

**Fix 4** was not a model problem. The fine-tuned detector had never been exported. The trained checkpoint sat on disk for almost two weeks while every cluster run used the old COCO model. I also measured ball slicing (a second pass over tiles): visibility went from 34.7 % to 38.0 %, but the longest continuous ball trajectory fell from 56 frames to 27, at 3.2 times the runtime. A pass needs continuity, so slicing stays off.

## Fix 5: the bug was in the cheap layer

By now the cluster found 28 kicks, placed players on the pitch for 99.9 % of detections, and had a valid homography in every frame. A diagnostic test showed every kick was dropped for the same reason: no passer. Possession was established in **0 of 599 frames**.

Two causes. The possession radius, 1.2 m, was a guess: on the clip, the nearest player is 2.15 m from the ball at the median. I raised it to 2.5 m, argued from the error budget, not fitted. Possession stayed at exactly 0.

The second cause was the one that mattered. `min_frames: 3` required three *consecutive video frames*. The cluster runs perception on every second frame, and the frames in between are empty placeholders. No run could ever exceed length 1. Possession was impossible at any stride above 1, for any radius. The prototype processes every frame, and before the fix no test in the rules package built a video with those gaps, so neither could show it.

After counting runs in observations instead of raw frames:

```
possession frames   0/599  ->  242/599 (40.4%)
kicks with a passer     0  ->  16 of 28
events                  0  ->  2

frame 460  PASS  REVIEW_REQUIRED  ONSIDE  conf 0.60
frame 472  PASS  DETECTED         ONSIDE  conf 0.71
```

What these are, exactly. They come from re-running the rules binary on the artifacts of the last cluster run, not from a new full cluster run. Whether "onside" is right at either frame is unknown, because there is no ground truth. Both are `PASS` events, where Law 11.1 settles the call without a line, so the system has still never called an offside. And the thresholds behind those confidences have never been calibrated.

## What the discarded and failed runs revealed

- **A stall the benchmark caused.** A job that normally takes about 135 s took about 13 minutes. The API autoscales on request rate, and the load generator's own polling was enough to scale it up and down. One scale-down killed a replica holding a message. Nothing was lost, and no alert fired. The run is excluded from the medians, by name, with the reason.
- **A CPU cap Kubernetes couldn't see.** A stray `docker update --cpus=1` on a kind node halved vision throughput. The node still advertised 14 CPUs and the pod showed 0 throttle events. It cost a day of misdiagnosis, and a tuning change that was made and then reverted.
- **The first cluster run failed silently.** An OOM-killed worker records nothing. The job sat in its stage with a null error while its messages drained into a dead-letter queue nobody read. The dead-letter watcher and the alerts exist because of that run.

## What I'd tell a team

1. **Make "nothing happened" explain itself.** A run that emits nothing looks the same as a run with nothing to emit. Counting why each kick was dropped found both causes.
2. **Test the deterministic layer at the sampling the deployed pipeline uses.**
3. **Measure what the next stage consumes.** Ball visibility rose without helping: with the first ball model the new detections were wrong, with slicing they were scattered.
4. **Check what is deployed**, not what is trained.
5. **Name the runs you exclude**, and check whether your harness is steering the system it measures.
6. **Without labels, a verdict is a milestone, not a result.** Two events after four weeks of none is progress on the plumbing. It says nothing yet about offside.

## What this does not show

No accuracy, no labelled clips, no calibrated thresholds, one clip with one manual calibration, nothing on AWS, and no full cluster run behind the two verdicts yet. It is not a VAR system and is not compared with one.

---

**Project, docs and decision records:** [github.com/ricardocunha/sportsvision](https://github.com/ricardocunha/sportsvision)

**Full write-up and the source of every number:** [github.com/ricardocunha/ensaios › articles/2027-01-sportsvision-offside](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-sportsvision-offside)

*Footage: three Wikimedia Commons clips, CC BY-SA 4.0, by NaBUru38 and Manchesterunited1234; no frames are reproduced here. Training data: Roboflow Universe football datasets, CC BY 4.0. Models: RF-DETR and SigLIP (Apache-2.0), ByteTrack via supervision (MIT).*

#ComputerVision #MLOps #Kubernetes #Golang #Python #SoftwareEngineering #Football
