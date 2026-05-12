import time
import uuid
from contextlib import contextmanager
from .models import ToolCallLog, AgentStateLog, TraceRecord


class Tracer:
    def __init__(self):
        self.run_id = str(uuid.uuid4())
        self.tool_calls: list[ToolCallLog] = []
        self.agent_states: list[AgentStateLog] = []

    @contextmanager
    def trace_tool(self, tool_name: str, inputs: dict):
        t0 = time.time()
        result = {"output": None}
        try:
            yield result
        finally:
            self.tool_calls.append(ToolCallLog(
                tool=tool_name,
                inputs=inputs,
                output=result.get("output"),
                latency_ms=round((time.time() - t0) * 1000, 2)
            ))

    def log_agent_state(self, agent_id: str, state: dict):
        self.agent_states.append(AgentStateLog(agent_id=agent_id, state=state))

    def finalize(self, output) -> TraceRecord:
        return TraceRecord(
            run_id=self.run_id,
            timestamp=time.time(),
            tool_calls=self.tool_calls,
            agent_states=self.agent_states,
            final_output=output
        )