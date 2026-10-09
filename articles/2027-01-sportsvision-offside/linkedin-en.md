<!-- LinkedIn post (EN), ~1,400 characters. -->

Five correct fixes, zero offside calls.

I built a pipeline that takes football video and should return, for every pass, an offside decision with its geometry. Go for the rules, Python for the vision, queues and autoscaling on a local Kubernetes cluster. For four weeks, on real footage, it never reached a verdict.

What I found:

→ Deciding is cheap, seeing is expensive: in the benchmark, the rules stage took 0.023 s and perception 100.2 s on the same 10 s video.

→ A dedicated ball model took ball visibility from 47% to 93%. Still zero events: the trajectory hit 666 km/h. The detector was confidently wrong.

→ A motion gate cut the worst ball jump from 12.14 m to 1.63 m. First event ever: "inconclusive".

→ The fine-tuned detector had sat on disk for almost two weeks while the cluster ran the old one.

→ The last blocker was in the cheap, deterministic layer: possession needed 3 consecutive frames, and the cluster only looks at every second frame. 0 of 599 frames, for any possession radius.

After that fix: the first two verdicts, both "onside". I have no labelled clips, so I can't say if they're right, and they come from re-running the rules on saved artifacts, not a full cluster run. No accuracy figure exists.

The lesson: a run that emits nothing must say why.

Full write-up and project: [[LINK]]

#ComputerVision #MLOps #Kubernetes #Golang #Python #SoftwareEngineering
