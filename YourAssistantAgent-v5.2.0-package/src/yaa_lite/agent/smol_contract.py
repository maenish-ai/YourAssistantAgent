# Lightweight tool-contract adapter inspired by Hugging Face smolagents.
# Upstream project: https://github.com/huggingface/smolagents
# License: Apache-2.0. See licenses/Apache-2.0-smolagents.txt.
from __future__ import annotations

import inspect
from typing import Any

AUTHORIZED_TYPES = {"string", "boolean", "integer", "number", "array", "object", "any", "null"}


class Tool:
    """Tiny allow-listed tool contract used by the desktop Smart Agent.

    We intentionally vendor only this minimal contract instead of importing the
    full smolagents package. That keeps startup/dependency cost low on 4 GB PCs
    and avoids enabling code-executing agent features we do not want.
    """

    name: str = ""
    description: str = ""
    inputs: dict[str, dict[str, Any]] = {}
    output_type: str = "string"

    def __init__(self, *args, **kwargs):
        self.validate_arguments()

    def validate_arguments(self) -> None:
        if not self.name or not self.name.isidentifier():
            raise ValueError(f"Invalid tool name: {self.name!r}")
        if not self.description:
            raise ValueError(f"Tool {self.name} requires a description")
        if self.output_type not in AUTHORIZED_TYPES:
            raise ValueError(f"Invalid output type for {self.name}: {self.output_type}")
        for key, spec in self.inputs.items():
            if not isinstance(spec, dict) or "type" not in spec or "description" not in spec:
                raise ValueError(f"Invalid input specification {self.name}.{key}")
            types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
            if any(t not in AUTHORIZED_TYPES for t in types):
                raise ValueError(f"Invalid input type for {self.name}.{key}: {types}")
        signature = inspect.signature(self.forward)
        actual = {k for k in signature.parameters if k != "self"}
        expected = set(self.inputs)
        if actual != expected:
            raise ValueError(f"Tool {self.name} forward args {sorted(actual)} != inputs {sorted(expected)}")

    def forward(self, *args, **kwargs):
        raise NotImplementedError

    def __call__(self, **kwargs):
        return self.forward(**kwargs)

    def prompt_description(self) -> str:
        args = ", ".join(self.inputs) or "none"
        return f"{self.name}({args}): {self.description}"
