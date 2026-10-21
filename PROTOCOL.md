# Frozen confirmatory protocol

## Research question

Do identical semantic embodiment prompts produce different Void outcomes in `gpt-3.5-turbo-1106` and `gpt-4-0613`?

A Void is a model execution returning a successful provider response with exactly zero visible UTF-8 output bytes. Provider termination metadata determines its subtype. Explicit refusals, safety blocks, tool-mediated executions, and transport, protocol, billing, quota, rate-limit, and infrastructure failures are distinct non-Void outcomes.

Primary outcome: **V0**, a successful response with present string `message.content`, exactly zero UTF-8 bytes and `finish_reason="stop"`, after excluding operational failures, refusals, safety blocks and tool-mediated responses.

## Requests

Endpoint: `POST https://api.openai.com/v1/chat/completions`.

Models, in listed order:

1. `gpt-3.5-turbo-1106`
2. `gpt-4-0613`

Exact system prompt:

```text
You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.
```

| Pair ID | Null input | Matched control |
|---|---|---|
| silence_speech | `Be silence.` | `Be speech.` |
| nothing_something | `Be nothing.` | `Be something.` |
| null_value | `Be the null.` | `Be a value.` |

Every request contains exactly these fields: `model`, two `messages` (system then user), `temperature=0`, `max_tokens=1000`, `stream=false`.

Ten repetitions per input per model: **120 scheduled requests**. Each is a fresh independent conversation, without carryover or assistant prefill. No tools, stop sequences, response-format constraint, logit bias or other optional generation parameters are sent. The only intended experimental variable is the requested snapshot.

Trial IDs are `t001` through `t120`. Order: replicate 1 through 10; pairs in the order above; null then control; listed model order on odd replicates and reversed order on even replicates. Requests execute sequentially.

Each trial has one attempt, a 180-second socket timeout, and **zero automatic retries**. Every operational failure is recorded, without substitution, tuning or overwriting. All scheduled slots are attempted. An interrupted run remains incomplete and cannot pass verification. A wrong returned model ID prevents verification.

## Classification, in order

1. **OP**: non-2xx HTTP; transport error; invalid UTF-8/JSON; provider error; malformed response; wrong returned model ID.
2. **RF**: nonempty provider `message.refusal`, or `finish_reason="refusal"`.
3. **SB**: `finish_reason="content_filter"`.
4. **TC**: nonempty `tool_calls`/`function_call`, or their corresponding finish reason.
5. Extract `message.content`. A string is a present text container. Missing/null content is absent. Any other content type is OP.
6. Compute the exact UTF-8 length. For a nonempty string, **NV** applies if all characters are whitespace or Unicode category P*, Cf or Cc (including punctuation/ellipsis-only outputs); otherwise **R**. Stored content is never trimmed, normalized or changed.
7. At zero bytes, **V0** requires normal stop and a present string container. **V1** applies to `finish_reason="length"`. Otherwise **VU**, including absent/null content at normal stop. An absent container is never V0.

Refusal and safety classification uses explicit provider metadata, not an inferred textual judgment. Nonempty text is never a Void. The Python Unicode database version is recorded in every receipt. Byte counting is independent of category classification.

## Records and verification

Save exact request JSON bytes, exact HTTP response-body bytes, and selected response headers (`date`, `content-type`, `x-request-id`, `openai-model`, `openai-version`, `openai-processing-ms`). Credentials are read only from `OPENAI_API_KEY`; they are never printed, saved, hashed or committed. Response headers containing organization or project identifiers are not collected.

Each record contains trial ID, attempt, requested/returned model, exact prompts, pair and role, replicate, settings, UTC times, HTTP status, content, container presence, UTF-8 byte count/hash, finish reason, refusal/tool fields, provider usage, classification and request/raw-response hashes. Missing transport bodies are explicitly distinguished from zero assistant-content bytes.

Events are append-only JSONL with a SHA-256 link to the preceding event. Request-start and response-finish events bind the request, raw body, selected headers and record. Receipts are created exclusively and never overwritten.

Before inference, SHA-256 hashes of this file and `protocol.json`, together with source hashes and a UTC timestamp, are written to `FREEZE.json`. The protocol and implementation are committed with message `freeze protocol before inference`. `FREEZE_COMMIT.txt` subsequently records that commit without changing hashed files.

The offline verifier independently checks the frozen commit, all 120 slots, unique IDs, every request, returned model identities, raw data, classifications, byte counts, hashes, and event consistency. Mutations must fail verification. No network or credential is used by verification or analysis.

## Analysis and scope

The primary table is `Model | Prompt | N | V0 | Visible | Other | V0 Rate`. Visible means R; Other contains all remaining classes. Report V0 totals for the 30 null and 30 control trials per model and report all three matched pairs separately. Operational outcomes are retained, not imputed. Only this run supplies its counts.

The artifact establishes observed snapshot-level Void behavior under the frozen protocol. Identical request text does not assert identical internal representations. No internal mechanism is inferred.

## Commands

Python 3.9 or newer, Git and a POSIX shell are required. No third-party Python packages are required.

```sh
python3 -m unittest discover -s tests -v
./verify.sh
python3 analyze.py
```

Live execution uses `./run.sh` with `OPENAI_API_KEY` already set. It refuses an existing run. To reproduce in a new directory, copy the frozen source files and protocol documents without receipts/results/events, generate a new `FREEZE.json` with `python3 run.py --freeze`, commit the source with the message above, write `git rev-parse HEAD > FREEZE_COMMIT.txt`, then execute `./run.sh`. This makes fresh provider calls and incurs provider charges.
