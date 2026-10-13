"""Read human review values from Notebook clients and the Studio raw editor."""

import json
from typing import Any

from langgraph.types import interrupt


def _parse_response(value: Any, config: dict) -> dict:
    """Validate one response without treating raw text as tool approval."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Use a JSON response object or a one-item array.") from exc
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError("Provide exactly one response for this request.")
        value = value[0]
    if not isinstance(value, dict):
        raise ValueError("The response must be an object with a 'type' field.")

    response_type = value.get("type")
    options = {
        "response": "allow_respond",
        "accept": "allow_accept",
        "edit": "allow_edit",
        "ignore": "allow_ignore",
    }
    if not isinstance(response_type, str) or response_type not in options:
        raise ValueError("Choose response, accept, edit, or ignore.")
    if not config.get(options[response_type], False):
        raise ValueError(f"'{response_type}' is not allowed for this request.")
    if response_type == "response" and not isinstance(value.get("args"), str):
        raise ValueError("For response, 'args' must contain your feedback text.")
    if response_type == "edit":
        args = value.get("args")
        if not isinstance(args, dict) or not isinstance(args.get("args"), dict):
            raise ValueError("For edit, use {'args': {'args': {tool parameters}}}.")
    return value


def request_human_review(request: dict) -> dict:
    """Pause again on bad input, including a bad value saved by a failed run."""
    current_request = request
    while True:
        value = interrupt([current_request])
        try:
            return _parse_response(value, request["config"])
        except ValueError as exc:
            # Failed resume values are replayed from the checkpoint. Advance to
            # another interrupt instead of raising against the same saved value.
            current_request = {
                **request,
                "description": (
                    request.get("description", "")
                    + "\n\n**Resume input needs correction:** "
                    + str(exc)
                    + '\nExample: [{"type": "response", "args": "Your feedback"}]'
                ),
            }
