# Train only on Synthetic CNHs; evaluate on BID and Private Real Samples

A CNH holds personal data protected by LGPD, and the repo, dataset and adapters will all be public. We train only on Synthetic CNHs. These are generated with valid checksums and marked "AMOSTRA / SYNTHETIC", and we know their ground truth by construction. For realism, we evaluate on the BID Dataset (Soares et al., SIBGRAPI 2020). BID has no license, so we cite it and never redistribute or train on it. We also run a local, never-committed check on a few Private Real Samples.
