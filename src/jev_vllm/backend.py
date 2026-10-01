"""Persistent, in-process vLLM engine for segmented token continuation."""

import inspect
import os


class PythonBackend:
    def __init__(self, config):
        # Set this before importing vLLM or starting its worker processes.
        os.environ["VLLM_USE_FLASHINFER_SAMPLER"] = (
            "1" if config["runtime"]["use_flashinfer_sampler"] else "0"
        )
        from vllm import SamplingParams

        self.sampling_class = SamplingParams
        self.fields = set(inspect.signature(SamplingParams).parameters)
        self.config = config
        self.engine = None

    def validate_parameters(self, values):
        missing = set(values) - self.fields
        if missing:
            raise ValueError(f"SamplingParams fields not exposed: {sorted(missing)}")
        values = dict(values)
        if isinstance(values.get("logit_bias"), dict):
            values["logit_bias"] = {int(key): bias for key, bias in values["logit_bias"].items()}
        if isinstance(values.get("output_kind"), str):
            from vllm.sampling_params import RequestOutputKind
            values["output_kind"] = RequestOutputKind[values["output_kind"]]
        values.setdefault("max_tokens", self.config["generation"]["chunk_tokens"])
        return self.sampling_class(**values)

    def load(self):
        if self.engine is None:
            from vllm import LLM

            self.engine = LLM(
                model=self.config["paths"]["model"], **self.config["engine"]
            )
            self.tokenizer = self.engine.get_tokenizer()
        return self.engine

    def tokenize(self, task, enable_thinking):
        self.load()
        tokens = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": task}],
            tokenize=True,
            return_dict=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
        return {
            "tokens": tokens,
            "max_model_len": self.config["engine"]["max_model_len"],
        }

    def decode(self, tokens):
        # Keep raw generated text for evaluation, independently of display settings.
        return self.tokenizer.decode(tokens, skip_special_tokens=False)

    def generate(self, request):
        values = {key: value for key, value in request.items() if key != "prompt"}
        sampling = self.validate_parameters(values)
        self.load()
        output = self.engine.generate(
            [{"prompt_token_ids": request["prompt"]}], sampling, use_tqdm=False
        )[0]
        if len(output.outputs) != 1:
            raise ValueError("Segmented continuation requires exactly one candidate")
        choice = output.outputs[0]
        return {
            "choices": [
                {
                    "token_ids": list(choice.token_ids),
                    "text": choice.text,
                    "finish_reason": choice.finish_reason,
                    "stop_reason": choice.stop_reason,
                    "cumulative_logprob": choice.cumulative_logprob,
                    "logprobs": pack(choice.logprobs),
                }
            ],
            "prompt_logprobs": pack(output.prompt_logprobs),
            "num_cached_tokens": getattr(output, "num_cached_tokens", None),
        }


def pack(value):
    """Preserve native log-probability records in JSON output."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): pack(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [pack(item) for item in value]
    if hasattr(value, "__dict__"):
        return pack(vars(value))
    raise TypeError(f"Unsupported output record: {type(value).__name__}")
