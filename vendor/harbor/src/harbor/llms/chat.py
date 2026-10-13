import copy
from pathlib import Path
from typing import Any

from harbor.llms.base import BaseLLM, LLMResponse
from harbor.models.agent.rollout_detail import RolloutDetail


class Chat:
    def __init__(self, model: BaseLLM, interleaved_thinking: bool = False):
        self._model = model
        self._messages = []
        self._cumulative_input_tokens = 0
        self._cumulative_output_tokens = 0
        self._cumulative_cache_tokens = 0
        self._cumulative_cost = 0.0
        self._prompt_token_ids_list: list[list[int]] = []
        self._completion_token_ids_list: list[list[int]] = []
        self._logprobs_list: list[list[float]] = []
        self._extra_list: list[dict[str, Any]] = []
        self._interleaved_thinking = interleaved_thinking
        self._last_response_id: str | None = None

    @property
    def total_input_tokens(self) -> int:
        return self._cumulative_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._cumulative_output_tokens

    @property
    def total_cache_tokens(self) -> int:
        return self._cumulative_cache_tokens

    @property
    def total_cost(self) -> float:
        return self._cumulative_cost

    @property
    def messages(self) -> list[Any]:
        return self._messages

    def dump_state(self) -> dict[str, Any]:
        """Return a versioned copy of the conversation messages."""
        return {
            "schema_version": 1,
            "messages": copy.deepcopy(self._messages),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore messages into a fresh Chat without restoring usage or provider state."""
        if (
            self._messages
            or self._cumulative_input_tokens
            or self._cumulative_output_tokens
            or self._cumulative_cache_tokens
            or self._cumulative_cost
            or self._prompt_token_ids_list
            or self._completion_token_ids_list
            or self._logprobs_list
            or self._extra_list
        ):
            raise ValueError("Chat state can only be loaded into a fresh Chat")
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise ValueError("Unsupported Chat state schema")
        messages = state.get("messages")
        if not isinstance(messages, list):
            raise ValueError("Chat state messages must be a list")
        pending_tool_calls: set[str] = set()
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"Chat state message {index} must be an object")
            role = message.get("role")
            if not isinstance(role, str) or not role:
                raise ValueError(f"Chat state message {index} must have a role")
            if role != "tool" and pending_tool_calls:
                raise ValueError(
                    f"Chat state message {index} starts before prior tool results"
                )
            if role == "assistant":
                tool_calls = message.get("tool_calls") or []
                if not isinstance(tool_calls, list):
                    raise ValueError(
                        f"Chat state message {index} tool_calls must be a list"
                    )
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict) or not isinstance(
                        tool_call.get("id"), str
                    ):
                        raise ValueError(
                            f"Chat state message {index} has an invalid tool call"
                        )
                    call_id = tool_call["id"]
                    if call_id in pending_tool_calls:
                        raise ValueError(
                            f"Chat state message {index} repeats tool call {call_id}"
                        )
                    pending_tool_calls.add(call_id)
            elif role == "tool":
                call_id = message.get("tool_call_id")
                if call_id not in pending_tool_calls:
                    raise ValueError(
                        f"Chat state message {index} has an orphan tool result"
                    )
                pending_tool_calls.remove(call_id)
        if pending_tool_calls:
            raise ValueError("Chat state ends before all tool results")
        self._messages = copy.deepcopy(messages)
        self.reset_response_chain()

    @property
    def rollout_details(self) -> list[RolloutDetail]:
        """Get detailed rollout information from all chat interactions.

        Returns:
            List containing a single RolloutDetail representing the complete
            linear chat history, or an empty list if no rollout data was collected.

            TODO: consider multiple rollout details for non-linear chat histories, e.g.
            subagents, summarization, etc.
        """
        if (
            not self._prompt_token_ids_list
            and not self._completion_token_ids_list
            and not self._logprobs_list
            and not self._extra_list
        ):
            return []

        rollout_detail: RolloutDetail = {}

        if self._prompt_token_ids_list:
            rollout_detail["prompt_token_ids"] = self._prompt_token_ids_list

        if self._completion_token_ids_list:
            rollout_detail["completion_token_ids"] = self._completion_token_ids_list

        if self._logprobs_list:
            rollout_detail["logprobs"] = self._logprobs_list

        if self._extra_list:
            # Pivot per-turn dicts to per-field lists for consistent indexing
            all_keys = {k for d in self._extra_list for k in d}
            rollout_detail["extra"] = {
                key: [turn.get(key) for turn in self._extra_list]
                for key in sorted(all_keys)
            }

        return [rollout_detail]

    async def chat(
        self,
        prompt: str,
        logging_path: Path | None = None,
        **kwargs,
    ) -> LLMResponse:
        llm_response: LLMResponse = await self._model.call(
            prompt=prompt,
            message_history=self._messages,
            logging_path=logging_path,
            previous_response_id=self._last_response_id,
            **kwargs,
        )

        # Track response chain for Responses API
        if llm_response.response_id is not None:
            self._last_response_id = llm_response.response_id

        # Get token usage and cost from the LLM response
        usage = llm_response.usage
        if usage is not None:
            self._cumulative_input_tokens += usage.prompt_tokens
            self._cumulative_output_tokens += usage.completion_tokens
            self._cumulative_cache_tokens += usage.cache_tokens
            self._cumulative_cost += usage.cost_usd

        # Accumulate rollout details from the response
        self._accumulate_rollout_details(llm_response)

        # Build assistant message with optional reasoning content
        assistant_message = {"role": "assistant", "content": llm_response.content}
        if self._interleaved_thinking and llm_response.reasoning_content:
            assistant_message["reasoning_content"] = llm_response.reasoning_content

        self._messages.extend(
            [
                {"role": "user", "content": prompt},
                assistant_message,
            ]
        )
        return llm_response

    def reset_response_chain(self) -> None:
        """Reset the response chain so the next call sends full message history.

        Call this whenever chat._messages is directly modified (e.g., after
        summarization or unwinding) to ensure the next Responses API call
        doesn't use a stale previous_response_id.
        """
        self._last_response_id = None

    def _accumulate_rollout_details(self, llm_response: LLMResponse) -> None:
        """Accumulate rollout details from an LLM response.

        Args:
            llm_response: The LLM response containing token IDs and logprobs
        """
        # Accumulate prompt token IDs per turn
        if llm_response.prompt_token_ids:
            self._prompt_token_ids_list.append(llm_response.prompt_token_ids)

        # Accumulate completion token IDs per turn
        if llm_response.completion_token_ids:
            # Store completion token IDs for this turn
            self._completion_token_ids_list.append(llm_response.completion_token_ids)

            # Store logprobs for this turn (if available)
            if llm_response.logprobs:
                self._logprobs_list.append(llm_response.logprobs)

        # Accumulate extra provider-specific fields per turn
        if llm_response.extra:
            self._extra_list.append(llm_response.extra)
