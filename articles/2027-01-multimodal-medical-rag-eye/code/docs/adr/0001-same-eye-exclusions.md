# Same-eye images are excluded by vessel matching, not by embedding or hash similarity

RFMiD has the same eye in several images, across splits, sometimes with different labels. Test images with a same-eye image in an earlier split are left out of every "deduplicated" number (`docs/exclusions.json`: 31 test, 28 validation). The official split itself is unchanged.

Same-eye means a geometric match of the retina's vessel pattern: SIFT on the green channel, one-to-one matches, a RANSAC similarity transform that looks like a re-photograph, **≥ 8 inliers** (docs/DATA.md, "Duplicate audit").

## Considered options

- **BiomedCLIP cosine**: rejected. 1,587 pairs have cosine ≥ 0.99 and only 8 of them pass the geometric check; same-eye pairs go as low as 0.84.
- **Perceptual hash**: rejected. Near-equal hashes were mostly different eyes with the disc in the same place; same-eye pairs have a median distance of 19 of 64 bits.
- **Threshold ≥ 15 inliers** (cleaner pairs): reported, not used. Wrongly excluding a test image costs a little sample size; wrongly keeping a same-eye image leaks.

## Consequences

609 test images instead of 640. The kNN baseline barely moves (0.339 → 0.341), so duplicates were not inflating it. Recall is unknown: pairs whose vessels can't be matched (heavy haze) are missed. The audit's other finding, 54 % of same-eye pairs with different labels, is a ceiling on every score.
