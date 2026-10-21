# Pre-retirement replay of gpt-4-0613 under the frozen GPT-3.5/GPT-4 Void A/B protocol

- Original run: github.com/theonlypal/gpt35-gpt4-void-ab, freeze commit b468b3e29d9f4152a99fc9e2597e376f84b74ea4, run commit d77b4a64b8a3fdff06a27d80c1514531143e382b, Zenodo DOI https://doi.org/10.5281/zenodo.22912683
- Original result: gpt-4-0613 null 30/30 V0, control 0/30; gpt-3.5-turbo-1106 0/30 and 0/30.
- Context: gpt-3.5-turbo-1106 retired 2026-09-28; gpt-4-0613 scheduled for shutdown 2026-10-23 per OpenAI deprecations page.
- Protocol: unchanged. Same 120-slot schedule, same prompts, same settings, same classifier. No retries, no substitution.
- Prediction P1: all 60 gpt-3.5-turbo-1106 slots return non-2xx and classify OP.
- Prediction P2: gpt-4-0613 null 30/30 V0, control 0/30, each pair 10/10, provided returned model == gpt-4-0613.
- Prediction P3: if OpenAI reroutes the snapshot, returned model mismatch classifies OP; reported as-is.
- Execution window: before 2026-10-23 00:00 UTC. A run after shutdown is not this preregistration.

## Source and execution conditions

Official retirement dates: https://developers.openai.com/api/docs/deprecations, inspected October 20, 2026 (America/Los_Angeles). The documentation gives shutdown dates, not a precise shutdown hour. The midnight-UTC cutoff above is the study's conservative declared deadline. All 120 attempts must finish before that cutoff to qualify as an in-window replay.

No inference is authorized by publishing this repository. Execution requires a published Zenodo DOI for this preregistration, funded API access, and the author's explicit authorization. No availability probe, inference request, retry, substitution, or prompt tuning precedes that DOI. A reserved but unpublished DOI is not sufficient.

The results repository will be created by cloning this repository, retaining its complete Git history and freeze commit. The preregistration source and predictions remain unchanged. The preregistration DOI will be recorded in the results note; it will not be retroactively inserted into this frozen document. Results will be published separately at https://github.com/theonlypal/gpt4-0613-void-replay-results and deposited separately on Zenodo.

## Original implementation constraints

The ten copied files are byte-identical to the original freeze commit. README.md retains its original description; this document supplies the replay-specific predictions and execution conditions.

The runner classifies wrong returned model identities as OP. The independent verifier additionally rejects an HTTP-success response with a wrong or missing model identity, with `Successful response has wrong or missing model: <trial_id>`. Consequently P3 does not imply that the run will pass verification. Any such failure and its complete receipts must be retained and reported, without modifying the verifier. The original analyzer also requires successful verification before writing results.

Non-2xx responses remain OP, not Voids. P1 predicts operational unavailability, not the reason for an error: authentication, billing, quota, rate-limit, and retirement errors must be distinguished using the actual response bodies. A non-2xx response alone does not establish retirement. A valid returned model identifier establishes the provider-reported identity, not independent verification of underlying weights or routing.

P2's 10/10 prediction applies to each null input; each matched control predicts 0/10 V0. All scheduled slots remain in their denominators, including failures. A verified artifact is not by itself a confirmation of P1, P2, or P3. Report each prediction against observed outcomes, with operational failures separate from behavioral outcomes.

The unchanged runner does not programmatically enforce the DOI or deadline conditions. They must be checked before execution and against the saved UTC event times afterward. An incomplete or out-of-window run remains preserved and is not silently restarted.

## Original source identities

```text
protocol.json  dbbd4675bb761e545a2b49216e66ff8033bd895e4bd7a1f010ad44423d278944
run.py         a40a45c43416c459083c9ad680be355d646a05dfca96cfc78e048ca38547f860
```

FREEZE.json binds the original nine source/protocol/test files. This PREREG.md is bound by its inclusion in the same freeze Git commit and the preregistration deposit, not by the original source-hash mapping. The results history must retain that commit and this document byte-identically.
