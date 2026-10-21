#!/usr/bin/env python3
"""Generate descriptive results exclusively from independently verified receipts."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import verify


def counts(records):
    """Count observed classifications without inserting any expected result."""
    observed = Counter(record["classification"] for record in records)
    n = len(records)
    v0 = observed.get("V0", 0)
    visible = observed.get("R", 0)
    return {
        "N": n,
        "V0": v0,
        "Visible": visible,
        "Other": n - v0 - visible,
        "V0 Rate": v0 / n if n else None,
        "classifications": dict(sorted(observed.items())),
    }


def percent(value):
    return "N/A" if value is None else "{:.1%}".format(value)


def analyze(root):
    root = Path(root).resolve()
    # Verification precedes every aggregation and every write. In particular,
    # neither a receipt's classification nor a previously saved result is trusted.
    records = verify.verify(root, require_manifest=False)
    protocol = verify.verify_freeze(root)
    primary = []
    role_totals = []
    pair_totals = []
    for model in protocol["models"]:
        model_records = [r for r in records if r["requested_model"] == model]
        for pair in protocol["pairs"]:
            for role in ("null", "control"):
                subset = [r for r in model_records
                          if r["pair_id"] == pair["pair_id"] and r["role"] == role]
                primary.append({"Model": model, "Prompt": pair[role], **counts(subset)})
            nulls = [r for r in model_records
                     if r["pair_id"] == pair["pair_id"] and r["role"] == "null"]
            controls = [r for r in model_records
                        if r["pair_id"] == pair["pair_id"] and r["role"] == "control"]
            pair_totals.append({
                "model": model, "pair_id": pair["pair_id"],
                "null_prompt": pair["null"], "control_prompt": pair["control"],
                "null": counts(nulls), "control": counts(controls),
            })
        for role in ("null", "control"):
            subset = [r for r in model_records if r["role"] == role]
            role_totals.append({"model": model, "role": role, **counts(subset)})

    http_success = sum(isinstance(r.get("http_status"), int)
                       and 200 <= r["http_status"] < 300 for r in records)
    returned_present = sum(isinstance(r.get("returned_model"), str)
                           and bool(r["returned_model"]) for r in records)
    returned_matches = sum(r.get("returned_model") == r["requested_model"] for r in records)
    finish_reasons = Counter(
        str(r["finish_reason"]) if r.get("finish_reason") is not None else "<absent>"
        for r in records
    )
    metrics = {
        "recorded_attempts": len(records),
        "http_successes": http_success,
        "all_http_successful": http_success == len(records),
        "recorded_retries": sum(max(0, r["attempt_number"] - 1) for r in records),
        "returned_model_ids_present": returned_present,
        "returned_model_matches": returned_matches,
        "transport_errors": sum(bool(r.get("transport_error")) for r in records),
        "finish_reasons": dict(sorted(finish_reasons.items())),
        "classifications": counts(records)["classifications"],
    }
    summary = {
        "schema_version": 1,
        "source": "Only independently verified records from this artifact.",
        "scope": protocol["scope"],
        "endpoint": protocol["endpoint"],
        "models": protocol["models"],
        "system_prompt": protocol["system_prompt"],
        "settings": protocol["settings"],
        "omitted_parameters": protocol["omitted_parameters"],
        "context": protocol["context"],
        "primary_table": primary,
        "null_control_totals": role_totals,
        "matched_pairs": pair_totals,
        "execution_metrics": metrics,
    }

    lines = [
        "# Observed Void A/B results", "",
        "These counts use only the complete run's independently verified receipts. "
        "V0 denotes successful, present-string, zero-byte content with normal stop, "
        "after operational failures, refusals, safety blocks and tool responses are excluded. "
        "Visible means R; Other includes every remaining classification.", "",
        "| Model | Prompt | N | V0 | Visible | Other | V0 Rate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in primary:
        lines.append("| {Model} | {Prompt} | {N} | {V0} | {Visible} | {Other} | {rate} |".format(
            **row, rate=percent(row["V0 Rate"])))
    lines.extend(["", "## Null and control totals", ""])
    for row in role_totals:
        lines.extend(["{model} {role_upper} V0: {V0}/{N}".format(
            **row, role_upper=row["role"].upper()), ""])
    lines.extend(["", "## Each matched pair", "",
                  "| Model | Null prompt | Null V0 / N | Control prompt | Control V0 / N |",
                  "|---|---|---:|---|---:|"])
    for pair in pair_totals:
        lines.append("| {model} | {null_prompt} | {nv0} / {nn} | {control_prompt} | {cv0} / {cn} |".format(
            **pair, nv0=pair["null"]["V0"], nn=pair["null"]["N"],
            cv0=pair["control"]["V0"], cn=pair["control"]["N"]))
    lines.extend([
        "", "## Execution evidence", "",
        "Recorded attempts: {recorded_attempts}; HTTP successes: {http_successes}/{recorded_attempts}; "
        "recorded retries: {recorded_retries}; transport errors: {transport_errors}.".format(**metrics),
        "",
        "Returned model IDs exactly matched the requested snapshot in {returned_model_matches}/"
        "{recorded_attempts} records; {returned_model_ids_present}/{recorded_attempts} records "
        "contained a returned model ID.".format(**metrics), "",
        "Finish reasons: " + json.dumps(metrics["finish_reasons"], sort_keys=True) + ".", "",
        "Classifications: " + json.dumps(metrics["classifications"], sort_keys=True) + ".", "",
        "## Exact scope", "",
        "Models: " + ", ".join("`" + m + "`" for m in protocol["models"]) + ".", "",
        "Endpoint: `" + protocol["endpoint"] + "`.", "",
        "Settings: `" + json.dumps(protocol["settings"], sort_keys=True) + "`.", "",
        "System prompt:", "", "```text", protocol["system_prompt"], "```", "",
        protocol["context"], "",
        "Omitted parameters: " + ", ".join("`" + p + "`" for p in protocol["omitted_parameters"]) + ".", "",
        "All scheduled operational outcomes remain in their denominators; there is no imputation.", "",
        protocol["scope"], "",
    ])

    results = root / "results"
    results.mkdir(exist_ok=True)
    columns = [
        "trial_id", "attempt_number", "requested_model", "returned_model", "pair_id", "role",
        "replicate", "user_prompt", "http_status", "classification", "finish_reason",
        "message_content", "text_container_present", "visible_utf8_bytes", "visible_sha256",
        "raw_response_received", "response_body_complete", "transport_error",
    ]
    with (results / "trials.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (results / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (results / "RESULT.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    summary = analyze(args.root)
    print("Analysis generated from {} independently verified records.".format(
        summary["execution_metrics"]["recorded_attempts"]))


if __name__ == "__main__":
    main()
