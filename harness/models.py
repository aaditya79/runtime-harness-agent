from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import hashlib, json, time, uuid


class EnforcementAction(Enum):
    PASS = "pass"
    BLOCK = "block"
    REVISE = "revise"
    ESCALATE = "escalate"


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationResult:
    passed: bool
    checks: list[ValidationCheck]

    def failed_checks(self):
        return [c for c in self.checks if not c.passed]


@dataclass
class ToolCallLog:
    tool: str
    inputs: dict
    output: Any
    latency_ms: float


@dataclass
class AgentStateLog:
    agent_id: str
    state: dict


@dataclass
class TraceRecord:
    run_id: str
    timestamp: float
    tool_calls: list[ToolCallLog]
    agent_states: list[AgentStateLog]
    final_output: Any

    def hash(self) -> str:
        payload = json.dumps({
            "run_id": self.run_id,
            "tool_calls": [{"tool": t.tool, "inputs": t.inputs} for t in self.tool_calls],
            "final_output": str(self.final_output)
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class HarnessResult:
    validation: ValidationResult
    trace: TraceRecord
    action: EnforcementAction
    final_output: Any
    trace_hash: str = ""

    def __post_init__(self):
        self.trace_hash = self.trace.hash()
