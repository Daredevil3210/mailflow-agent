"""Exercise resume input recovery without model or email service calls."""

import json
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from email_assistant.human_review import request_human_review


REQUEST = {
    "action_request": {"action": "Question", "args": {"content": "Test question"}},
    "config": {
        "allow_respond": True,
        "allow_ignore": True,
        "allow_accept": False,
        "allow_edit": False,
    },
    "description": "Local test request",
}


class ReviewState(TypedDict):
    response: dict


def build_graph(handler, saver=None):
    return (
        StateGraph(ReviewState)
        .add_node("review", handler)
        .add_edge(START, "review")
        .add_edge("review", END)
        .compile(checkpointer=saver if saver is not None else InMemorySaver())
    )


def handle_review(state):
    return {"response": request_human_review(REQUEST)}


@pytest.mark.parametrize("format", ["array", "object", "json_text"])
def test_valid_resume_formats(format):
    graph = build_graph(handle_review)
    config = {"configurable": {"thread_id": format}}
    assert "__interrupt__" in graph.invoke({"response": {}}, config)
    response = {"type": "response", "args": "Answer"}
    value = {"array": [response], "object": response, "json_text": json.dumps([response])}[format]
    result = graph.invoke(Command(resume=value), config)
    assert result["response"] == response
    assert graph.get_state(config).next == ()


@pytest.mark.parametrize("invalid", ["", "plain text", [], [{"type": "accept"}], [{"type": "response"}]])
def test_invalid_input_reprompts_instead_of_crashing(invalid):
    graph = build_graph(handle_review)
    config = {"configurable": {"thread_id": "invalid"}}
    graph.invoke({"response": {}}, config)
    result = graph.invoke(Command(resume=invalid), config)
    assert "__interrupt__" in result
    assert "Resume input needs correction" in result["__interrupt__"][0].value[0]["description"]
    response = {"type": "response", "args": "Corrected answer"}
    assert graph.invoke(Command(resume=[response]), config)["response"] == response


@pytest.mark.parametrize("corrected_after_failure", [False, True])
def test_recovers_string_already_saved_by_original_failed_handler(corrected_after_failure):
    def original_handler(state):
        response = interrupt([REQUEST])[0]
        return {"response": {"type": response["type"]}}

    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "existing-failed-thread"}}
    original = build_graph(original_handler, saver)
    original.invoke({"response": {}}, config)
    with pytest.raises(TypeError, match="string indices"):
        original.invoke(Command(resume="bad input"), config)
    response = {"type": "response", "args": "Recovered answer"}
    if corrected_after_failure:
        with pytest.raises(TypeError, match="string indices"):
            original.invoke(Command(resume=[response]), config)

    fixed = build_graph(handle_review, saver)
    retry = fixed.invoke(None, config)
    if corrected_after_failure:
        # The later correction is already saved at the second interrupt index.
        assert retry["response"] == response
    else:
        assert "__interrupt__" in retry
        assert "Resume input needs correction" in retry["__interrupt__"][0].value[0]["description"]
        assert fixed.invoke(Command(resume=[response]), config)["response"] == response
