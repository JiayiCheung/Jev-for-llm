"""Classify every entry in a source-audited vLLM HTML checklist.

This is an inventory audit, not a runtime support or safe-range certification.
The suggested step rules are research proposals for the current Python controller.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

QUALITY_STEPS = {
    "temperature": "control[0,2]/20",
    "top_p": "control[0.01,1]/100",
    "top_k": "integer_control[1,101]/20; 0 and -1 are separate disable values",
    "repetition_penalty": "control[1,1.5]/20",
    "min_p": "control[0,1]/100",
    "presence_penalty": "control[-2,2]/100",
    "frequency_penalty": "control[-2,2]/100",
}

STOPPING = {"stop", "stop_token_ids", "ignore_eos", "min_tokens"}
TOKEN_CONSTRAINTS = {"bad_words", "allowed_token_ids", "logit_bias"}
OBSERVATION = {"logprobs", "prompt_logprobs", "logprob_token_ids", "flat_logprobs"}
OUTPUT_FORMAT = {
    "detokenize",
    "skip_special_tokens",
    "spaces_between_special_tokens",
    "include_stop_str_in_output",
    "output_kind",
    "stream_interval",
    "output_text_buffer_length",
}
RUNNER_OWNED = {"n", "seed", "max_tokens"}

FIELDS = [
    "id",
    "batch",
    "group",
    "route",
    "name",
    "declared_type",
    "declared_default",
    "declared_domain",
    "entry_kind",
    "execution_stage",
    "value_family",
    "nullable",
    "value_action_family",
    "generic_step_eligibility",
    "controller_class",
    "in_parameters_json",
    "choice_pattern",
    "step_rule",
    "classification_note",
]


def extract_json_element(source, element_id):
    pattern = rf'<script\b(?=[^>]*\bid="{re.escape(element_id)}")[^>]*>(.*?)</script>'
    match = re.search(pattern, source, re.DOTALL)
    if match is None:
        raise ValueError(f"Missing JSON script element: {element_id}")
    return json.loads(match.group(1))


def extract_groups(source):
    match = re.search(r"\bgroups=(\{.*?\});\s*const groupEntries", source, re.DOTALL)
    if match is None:
        raise ValueError("Missing checklist group definitions")
    return json.loads(match.group(1))


def strip_hash_comments(source):
    pattern = r'"(?:\\.|[^"\\])*"|#[^\r\n]*'
    return re.sub(
        pattern,
        lambda match: (
            " " * len(match.group()) if match.group().startswith("#") else match.group()
        ),
        source,
    )


def value_family(declared_type):
    value = declared_type.strip()
    nullable = bool(re.search(r"(?:^|\s\|\s)None(?:$|\s\|\s)", value))
    without_null = re.sub(r"\s*\|\s*None\b|\bNone\s*\|\s*", "", value).strip()
    if re.fullmatch(r"bool", without_null):
        family = "boolean"
    elif re.fullmatch(r"int", without_null):
        family = "integer"
    elif re.fullmatch(r"float", without_null):
        family = "float"
    elif re.fullmatch(r"str", without_null):
        family = "string"
    elif re.search(r"\b(?:dict|Mapping|OrderedDict)\s*\[", without_null):
        family = "mapping"
    elif (
        re.search(r"\b(?:list|tuple|set|Sequence|Iterable)\s*\[", without_null)
        and " | " in without_null
    ):
        family = "union_with_collection"
    elif re.search(r"\b(?:list|tuple|set|Sequence|Iterable)\s*\[", without_null):
        family = "collection"
    elif "Literal[" in without_null or "Enum" in without_null:
        family = "discrete"
    elif " | " in without_null:
        family = "union_or_structured"
    elif re.search(r"\b(?:Callable|type|Protocol)\b", without_null):
        family = "callable_or_type"
    else:
        family = "structured_or_unverified"
    return family, nullable


def value_action_family(family, nullable):
    """Describe a type's possible edit shape without granting route eligibility."""
    if family == "boolean":
        action, step = "keep/turn_on/turn_off", "no_numeric_step"
    elif family == "float":
        action, step = (
            "keep/increase/decrease",
            "requires_verified_bounds_and_control_window",
        )
    elif family == "integer":
        action, step = (
            "keep/increase/decrease",
            "requires_integer_quantization_and_verified_bounds",
        )
    elif family == "discrete":
        action, step = "keep/select_verified_option", "no_numeric_step"
    elif family == "string":
        action, step = "keep/set_verified_string/clear", "no_numeric_step"
    elif family == "collection":
        action, step = "keep/add_verified_item/remove_item/clear", "no_numeric_step"
    elif family == "mapping":
        action, step = (
            "keep/set_verified_entry/remove_entry/clear",
            "nested_values_need_separate_review",
        )
    elif family == "union_with_collection":
        action, step = (
            "keep/select_union_variant/edit_verified_items",
            "variant_specific_review",
        )
    else:
        action, step = "manual_schema_review", "no_generic_step"
    if nullable:
        action += "/disable_with_null"
    return action, step


def classify(row, current_names, groups):
    route = row.get("route", "")
    name = row.get("name", "")
    kind = row.get("kind", "")
    family, nullable = value_family(row.get("type", ""))
    value_action, generic_step = value_action_family(family, nullable)
    step = "none"

    if kind == "Excluded internal" or row.get("batch") == "X1":
        stage, category, note = (
            "excluded",
            "excluded_internal",
            "Internal or derived state; never offer as an external adjustment.",
        )
    elif row.get("batch") == "X0":
        stage, category, note = (
            "controller_only",
            "project_integration",
            "Project test, not a native vLLM parameter.",
        )
    elif kind == "Procedure":
        stage, category, note = (
            "procedure",
            "test_procedure",
            "Test procedure rather than a parameter value.",
        )
    elif route == "Python / SamplingParams":
        stage = "per_generation_python"
        if name.startswith("_"):
            category, note = (
                "derived_sampling_state",
                "Derived or private sampling field; do not expose as a controller action.",
            )
        elif name in QUALITY_STEPS:
            category, step, note = (
                "quality_numeric",
                QUALITY_STEPS[name],
                "Proposed control window and step; runtime effect remains unverified.",
            )
        elif name in STOPPING:
            category, note = (
                "termination_control",
                "Use typed actions; effects and per-call budgets require separate checks.",
            )
            if name == "min_tokens":
                step = "integer_control[0,128]/20; cap by next call max_tokens"
        elif name in TOKEN_CONSTRAINTS:
            category, note = (
                "token_constraint",
                "Requires verified words, token IDs, or mapping entries; no generic step.",
            )
        elif name in OBSERVATION:
            category, note = (
                "observation_only",
                "Changes returned diagnostics, not the intended answer-quality control.",
            )
        elif name in OUTPUT_FORMAT:
            category, note = (
                "output_representation",
                "Controls returned text or delivery; not a score-driven quality knob.",
            )
        elif name in RUNNER_OWNED:
            category, note = (
                "runner_owned",
                "Controlled by experiment design, not by Jev parameter adaptation.",
            )
        else:
            category, note = (
                "conditional_sampling_feature",
                "Inspect feature prerequisites and source validators before proposing actions.",
            )
    elif route == "Python / BeamSearchParams" or "beam_search" in route:
        stage, category, note = (
            "alternate_python_path",
            "beam_search_path",
            "Separate generation algorithm; not a SamplingParams action in the current runner.",
        )
    elif route.startswith("Python input"):
        stage, category, note = (
            "python_input_construction",
            "prompt_input",
            "Builds input content or metadata; not a sampling step.",
        )
    elif route == "Python / LLM.__init__":
        stage, category, note = (
            "model_initialization",
            "startup_only",
            "Requires model or engine initialization; cannot change between current chunks.",
        )
    elif route.startswith("Python / LLM."):
        stage, category, note = (
            "python_call_setup",
            "generation_entry_argument",
            "Entry-point argument; applicability depends on this call path.",
        )
    elif (
        route.startswith("EngineArgs")
        or route.startswith("AsyncEngineArgs")
        or route.startswith("Frontend startup")
    ):
        stage, category, note = (
            "engine_or_frontend_startup",
            "startup_only",
            "Requires a separate startup configuration and usually a restart.",
        )
    elif route.startswith("Frontend CLI") or kind == "CLI switch":
        stage, category, note = (
            "frontend_cli_startup",
            "startup_only",
            "CLI switch for a different entry point; not a Python chunk action.",
        )
    elif route.startswith("Nested config"):
        stage, category, note = (
            "owning_engine_configuration",
            "nested_startup_config",
            "Use through the owning configuration object; not a flat live parameter.",
        )
    elif route.startswith("Nested schema"):
        stage, category, note = (
            "owning_request_construction",
            "nested_request_schema",
            "Use through its owning request object; route compatibility is separate.",
        )
    elif route.startswith("Qwen template"):
        stage, category, note = (
            "chat_template_rendering",
            "model_template_option",
            "Changes template rendering; not a vLLM sampling parameter.",
        )
    elif route.startswith("/tokenize") or route == "/detokenize":
        stage, category, note = (
            "tokenization_request",
            "tokenization_interface",
            "Separate tokenization endpoint; not a Python generation sampling action.",
        )
    elif route.startswith("/v1/"):
        stage, category, note = (
            "http_request",
            "other_interface_request",
            "HTTP-route field; do not forward as a native Python SamplingParams keyword.",
        )
    else:
        stage, category, note = (
            "route_review_needed",
            "unclassified_route",
            "Inspect the owning interface before assigning an adjustment policy.",
        )

    if stage != "per_generation_python":
        choice_pattern = "not_in_current_chunk_controller"
    elif category == "quality_numeric":
        choice_pattern = (
            "keep/increase/decrease; then choose one of three legal magnitudes"
        )
    elif name == "min_tokens":
        choice_pattern = "conditional keep/increase/decrease; cap by next call length"
    elif name == "ignore_eos":
        choice_pattern = "keep/turn_on/turn_off"
    elif category in {"termination_control", "token_constraint"}:
        choice_pattern = "keep/set/add/remove/clear from verified values"
    elif category == "observation_only":
        choice_pattern = "instrumentation setting; not score-driven"
    elif category == "output_representation":
        choice_pattern = "fixed display setting; not score-driven"
    elif category == "runner_owned":
        choice_pattern = "fixed by experiment protocol"
    else:
        choice_pattern = "feature-specific source review required"

    return {
        "id": row["id"],
        "batch": row["batch"],
        "group": groups[row["batch"]][0],
        "route": route,
        "name": name,
        "declared_type": row.get("type", ""),
        "declared_default": row.get("default", ""),
        "declared_domain": row.get("domain", ""),
        "entry_kind": kind,
        "execution_stage": stage,
        "value_family": family,
        "nullable": str(nullable).lower(),
        "value_action_family": value_action,
        "generic_step_eligibility": generic_step,
        "controller_class": category,
        "in_parameters_json": str(
            route == "Python / SamplingParams" and name in current_names
        ).lower(),
        "choice_pattern": choice_pattern,
        "step_rule": step,
        "classification_note": note,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.checklist.read_text(encoding="utf-8-sig")
    rows = extract_json_element(source, "catalog")
    groups = extract_groups(source)
    parameters = json.loads(
        strip_hash_comments(args.parameters.read_text(encoding="utf-8-sig"))
    )
    current_names = {item["name"] for item in parameters}

    if len(rows) != len({row["id"] for row in rows}):
        raise ValueError("Checklist entry IDs are not unique")
    classified = [classify(row, current_names, groups) for row in rows]
    if len(classified) != 1181:
        raise ValueError(f"Expected 1181 checklist entries; found {len(classified)}")
    if any(row["controller_class"] == "unclassified_route" for row in classified):
        raise ValueError("Some checklist routes still need classification")
    if {
        row["name"] for row in classified if row["in_parameters_json"] == "true"
    } != current_names:
        raise ValueError("Some configured parameters are missing from SamplingParams")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(classified)

    print(f"Catalog entries: {len(classified)}")
    print(f"Current project parameters: {len(current_names)}")
    for category, count in sorted(
        Counter(row["controller_class"] for row in classified).items()
    ):
        print(f"{category}: {count}")


if __name__ == "__main__":
    main()
