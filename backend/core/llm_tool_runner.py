# backend/core/llm_tool_runner.py
import os
import json
import logging
from typing import Any, Dict, List, Callable, Optional, Tuple
from openai import AzureOpenAI

logger = logging.getLogger("llm")
logger.setLevel(logging.INFO)

# backend/core/llm_tool_runner.py
def get_azure_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )

def _max_tokens_kwargs(max_tokens: Optional[int]) -> Dict[str, Any]:
    if max_tokens is None:
        return {}
    # Use max_tokens for chat.completions consistently
    return {"max_completion_tokens": max_tokens}

class LLMToolRunner:
    def __init__(
        self,
        client: AzureOpenAI,
        model: str,
        tool_specs: List[Dict[str, Any]],
        tool_registry: Dict[str, Callable[..., Any]],
        temperature: float = 0.2,
        parallel_tool_calls: bool = True,
        max_tokens: Optional[int] = 1000,
        max_tool_rounds: int = 6,
    ) -> None:
        self.client = client
        self.model = model
        self.tool_specs = tool_specs
        self.tool_registry = tool_registry
        self.temperature = temperature
        self.parallel_tool_calls = parallel_tool_calls
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds

    def run(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Returns (final_assistant_message, executed_tool_calls)
        final_assistant_message: {"role": "assistant", "content": "...", "raw": <choice dict>}
        executed_tool_calls: list of {"name", "id", "args", "result"}
        """
        executed_calls: List[Dict[str, Any]] = []
        rounds = 0
        while True:
            rounds += 1
            logger.info("LLM round %s: messages=%s", rounds, _safe_preview(messages))
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tool_specs if self.tool_specs else None,
                    tool_choice="auto" if self.tool_specs else "none",
                    temperature=self.temperature,
                    parallel_tool_calls=self.parallel_tool_calls,
                    **_max_tokens_kwargs(self.max_tokens),
                )
            except Exception as e:
                logger.exception("Azure OpenAI call failed")
                raise

            choice = resp.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            tool_calls = getattr(choice.message, "tool_calls", None)
            content = getattr(choice.message, "content", None)

            logger.info("LLM finish_reason=%s, has_tool_calls=%s", finish_reason, bool(tool_calls))

            if tool_calls:
                if rounds > self.max_tool_rounds:
                    logger.warning("Max tool rounds reached; returning partial result")
                    return (
                        {"role": "assistant", "content": content or "(no content)", "raw": choice.model_dump()},
                        executed_calls,
                    )

                # Execute tools
                for call in tool_calls:
                    fn_name = call.function.name
                    arg_str = call.function.arguments or "{}"
                    try:
                        args = json.loads(arg_str)
                    except Exception:
                        args = {"_raw_args": arg_str}

                    tool_fn = self.tool_registry.get(fn_name)
                    if tool_fn is None:
                        result = {"error": f"Unknown tool: {fn_name}", "args": args}
                        logger.error("Unknown tool: %s", fn_name)
                    else:
                        try:
                            result = tool_fn(**args)
                        except Exception as e:
                            logger.exception("Tool %s failed", fn_name)
                            result = {"error": str(e), "args": args}

                    executed_calls.append(
                        {"name": fn_name, "id": call.id, "args": args, "result": result}
                    )
                    # Inject tool result back to model
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": fn_name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                # Loop again so the model can use tool results
                continue

            # No tool calls -> return final message
            if not content:
                # Avoid “please rephrase” fallbacks; surface real state when empty
                msg = {
                    "role": "assistant",
                    "content": "(empty content)",
                    "raw": choice.model_dump(),
                }
                return msg, executed_calls

            return {"role": "assistant", "content": content, "raw": choice.model_dump()}, executed_calls

def _safe_preview(messages: List[Dict[str, Any]], limit: int = 1500) -> str:
    try:
        txt = json.dumps(messages, ensure_ascii=False)
        if len(txt) > limit:
            return txt[:limit] + "...(truncated)"
        return txt
    except Exception:
        return "(unserializable messages)"