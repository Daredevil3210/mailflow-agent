"""Check preference storage and review flow without external model calls."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command


@pytest.fixture
def agent():
    # Model construction is replaced before import; no API credentials are needed.
    with patch("email_assistant.models.create_chat_model"):
        return importlib.import_module("email_assistant.email_assistant_hitl_memory")


def test_default_is_initialized_once_and_saved_edits_are_preserved(agent):
    store = InMemoryStore()
    namespace = ("email_assistant", "cal_preferences")
    assert agent.get_memory(store, namespace, "Default") == "Default"
    store.put(namespace, "user_preferences", "Updated")
    assert agent.get_memory(store, namespace, "Different default") == "Updated"
    assert len(store.search(namespace)) == 1


def test_namespaces_keep_preference_profiles_separate(agent):
    store = InMemoryStore()
    calendar = ("email_assistant", "cal_preferences")
    response = ("email_assistant", "response_preferences")
    agent.get_memory(store, calendar, "30-minute meetings")
    agent.get_memory(store, response, "Concise emails")
    store.put(calendar, "user_preferences", "Afternoons")
    assert agent.get_memory(store, response) == "Concise emails"


def test_update_sends_old_profile_and_feedback_then_replaces_same_key(agent, monkeypatch):
    store = InMemoryStore()
    namespace = ("email_assistant", "cal_preferences")
    store.put(namespace, "user_preferences", "Prefer afternoons; meetings last 45 minutes.")
    new_profile = "Prefer afternoons; meetings last 30 minutes."
    model = Mock()
    model.with_structured_output.return_value = model
    model.invoke.return_value = SimpleNamespace(user_preferences=new_profile)
    monkeypatch.setattr(agent, "create_chat_model", Mock(return_value=model))
    feedback = [{"role": "user", "content": "Make meetings 30 minutes."}]
    agent.update_memory(store, namespace, feedback)
    sent = model.invoke.call_args.args[0]
    assert "meetings last 45 minutes" in sent[0]["content"]
    assert sent[1:] == feedback
    assert store.get(namespace, "user_preferences").value == new_profile
    assert len(store.search(namespace)) == 1


def test_llm_call_reads_latest_preferences_without_mutating_message_history(agent, monkeypatch):
    store = InMemoryStore()
    calendar = ("email_assistant", "cal_preferences")
    response = ("email_assistant", "response_preferences")
    store.put(calendar, "user_preferences", "Calendar preference A")
    store.put(response, "user_preferences", "Response preference A")
    model = Mock()
    model.invoke.return_value = AIMessage(content="Finished")
    monkeypatch.setattr(agent, "llm_with_tools", model)
    state = {"messages": [{"role": "user", "content": "Test task"}]}
    agent.llm_call(state, store)
    store.put(calendar, "user_preferences", "Calendar preference B")
    store.put(response, "user_preferences", "Response preference B")
    agent.llm_call(state, store)
    prompt = model.invoke.call_args.args[0][0]["content"]
    assert "Calendar preference B" in prompt
    assert "Response preference B" in prompt
    assert state["messages"] == [{"role": "user", "content": "Test task"}]


@pytest.mark.parametrize(
    "names, expected",
    [([], "__end__"), (["Done"], "__end__"),
     (["check_calendar_availability", "schedule_meeting"], "interrupt_handler"),
     (["Done", "write_email"], "error"), (["write_email", "Done"], "error")],
)
def test_routing_checks_all_requests(agent, names, expected):
    calls = [{"name": name, "args": {}, "id": str(i)} for i, name in enumerate(names)]
    state = {"messages": [AIMessage(content="", tool_calls=calls)]}
    if expected == "error":
        with pytest.raises(ValueError, match="Done must be called separately"):
            agent.should_continue(state)
    else:
        assert agent.should_continue(state) == expected


EMAIL = {
    "author": "Project Manager <pm@example.com>",
    "to": "User <user@example.com>",
    "subject": "Meeting request",
    "email_thread": "Can we meet for 45 minutes next week?",
}
UPDATED = "Prefer 30-minute meetings strictly after 2pm."


@pytest.mark.parametrize("choice", ["accept", "edit", "response", "ignore"])
def test_review_execution_and_memory_updates_with_real_checkpoints(agent, monkeypatch, choice):
    executions, updates, prompts = [], [], []

    class MemoryModel:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            updates.append(messages)
            return SimpleNamespace(user_preferences=UPDATED)

    class PlanningModel:
        def invoke(self, messages):
            prompts.append(messages)
            last = messages[-1]
            if isinstance(last, ToolMessage) and "User gave feedback" not in last.content:
                return AIMessage(content="", tool_calls=[{
                    "name": "Done", "args": {"done": True}, "id": "done",
                }])
            updated = UPDATED in messages[0]["content"]
            return AIMessage(content="", tool_calls=[{
                "name": "schedule_meeting", "id": "meeting",
                "args": {
                    "attendees": ["pm@example.com", "user@example.com"],
                    "subject": "Meeting", "duration_minutes": 30 if updated else 45,
                    "preferred_day": "2030-01-01", "start_time": 16 if updated else 14,
                },
            }])

    def execute(args):
        executions.append(args)
        return "Mock meeting scheduled"

    monkeypatch.setattr(agent, "create_chat_model", lambda **kwargs: MemoryModel())
    monkeypatch.setattr(agent, "llm_router", SimpleNamespace(invoke=lambda _: SimpleNamespace(classification="respond")))
    monkeypatch.setattr(agent, "llm_with_tools", PlanningModel())
    monkeypatch.setattr(agent, "tools_by_name", {"schedule_meeting": SimpleNamespace(invoke=execute)})
    store = InMemoryStore()
    graph = agent.overall_workflow.compile(store=store, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": choice}}
    first = graph.invoke({"email_input": EMAIL}, config)
    request = first["__interrupt__"][0].value[0]["action_request"]
    assert request["action"] == "schedule_meeting"
    assert executions == []
    assert updates == []
    calendar = ("email_assistant", "cal_preferences")
    initial = store.get(calendar, "user_preferences").value
    response = {"type": choice}
    if choice == "edit":
        response["args"] = {"args": {**request["args"], "duration_minutes": 30, "start_time": 16}}
    elif choice == "response":
        response["args"] = "Please use 30 minutes and a time strictly after 2pm."
    result = graph.invoke(Command(resume=[response]), config)
    if choice == "response":
        assert executions == []  # Giving feedback never executes the old proposal.
        revised = result["__interrupt__"][0].value[0]["action_request"]["args"]
        assert revised["duration_minutes"] == 30
        assert revised["start_time"] == 16
        result = graph.invoke(Command(resume=[{"type": "accept"}]), config)
        # A new thread shares preferences, but starts with its own message history.
        other = graph.invoke({"email_input": EMAIL}, {"configurable": {"thread_id": "another-thread"}})
        assert other["__interrupt__"][0].value[0]["action_request"]["args"]["duration_minutes"] == 30
        assert len(prompts[-1]) == 2
    assert graph.get_state(config).next == ()
    if choice in ("edit", "response"):
        assert len(executions) == 1
        assert executions[0]["duration_minutes"] == 30
        assert executions[0]["start_time"] == 16
        assert len(updates) == 1
        assert store.get(calendar, "user_preferences").value == UPDATED
    elif choice == "accept":
        assert len(executions) == 1
        assert executions[0]["duration_minutes"] == 45
        assert updates == []
        assert store.get(calendar, "user_preferences").value == initial
    else:
        assert executions == []
        assert len(updates) == 1
        assert store.get(("email_assistant", "triage_preferences"), "user_preferences").value == UPDATED
        assert store.get(calendar, "user_preferences").value == initial


def test_answering_question_does_not_update_long_term_preferences(agent, monkeypatch):
    def plan(messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="", tool_calls=[{"name": "Done", "args": {"done": True}, "id": "done"}])
        return AIMessage(content="", tool_calls=[{"name": "Question", "args": {"content": "Which food?"}, "id": "question"}])

    update = Mock()
    monkeypatch.setattr(agent, "update_memory", update)
    monkeypatch.setattr(agent, "llm_router", SimpleNamespace(invoke=lambda _: SimpleNamespace(classification="respond")))
    monkeypatch.setattr(agent, "llm_with_tools", SimpleNamespace(invoke=plan))
    graph = agent.overall_workflow.compile(store=InMemoryStore(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "question"}}
    graph.invoke({"email_input": EMAIL}, config)
    result = graph.invoke(Command(resume=[{"type": "response", "args": "Indian tonight."}]), config)
    assert "Indian tonight." in result["messages"][-2].content
    update.assert_not_called()
