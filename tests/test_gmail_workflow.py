"""Exercise Gmail review flow with real checkpoints and fake external clients."""
import base64
import importlib
from email import message_from_bytes
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command


@pytest.fixture
def agent():
    with patch('email_assistant.models.create_chat_model'):
        return importlib.import_module('email_assistant.email_assistant_hitl_memory_gmail')


def test_gmail_tools_replace_mock_actions_without_changing_the_default_registry(agent):
    from email_assistant.tools import get_tools
    assert {tool.name for tool in agent.tools} == {
        'send_email_tool', 'schedule_meeting_tool', 'check_calendar_tool', 'Question', 'Done'}
    assert {tool.name for tool in get_tools(['write_email', 'schedule_meeting'])} == {
        'write_email', 'schedule_meeting'}


@pytest.mark.parametrize('names,expected', [
    ([], '__end__'), (['Done'], 'mark_as_read_node'),
    (['check_calendar_tool', 'send_email_tool'], 'interrupt_handler'),
    (['Done', 'send_email_tool'], 'error'), (['send_email_tool', 'Done'], 'error'),
])
def test_done_routes_to_mark_read_only_when_separate(agent, names, expected):
    calls = [{'name': name, 'args': {}, 'id': str(i)} for i, name in enumerate(names)]
    state = {'messages': [AIMessage(content='', tool_calls=calls)]}
    if expected == 'error':
        with pytest.raises(ValueError, match='Done must be called separately'):
            agent.should_continue(state)
    else:
        assert agent.should_continue(state) == expected


EMAIL = {'from': 'Sender <sender@example.com>', 'to': 'Owner <owner@example.com>',
         'subject': 'MailFlow-Test-Offline', 'body': 'Please confirm receipt.', 'id': 'test-message'}
UPDATED = 'Use short acknowledgments and sign off as Alex.'


@pytest.mark.parametrize('choice', ['accept', 'edit', 'response', 'ignore'])
def test_gmail_review_never_sends_before_approval_and_marks_read_after_done(agent, monkeypatch, choice):
    executions, updates, reads = [], [], []

    class MemoryModel:
        def with_structured_output(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            updates.append(messages)
            return SimpleNamespace(user_preferences=UPDATED)

    def plan(messages):
        last = messages[-1]
        if isinstance(last, ToolMessage) and 'User gave feedback' not in last.content:
            return AIMessage(content='', tool_calls=[{'name': 'Done', 'args': {'done': True}, 'id': 'done'}])
        revised = UPDATED in messages[0]['content']
        return AIMessage(content='', tool_calls=[{'name': 'send_email_tool', 'id': 'send', 'args': {
            'email_id': EMAIL['id'], 'response_text': 'Short reply, Alex.' if revised else 'Original reply.',
            'email_address': 'owner@example.com'}}])

    def execute(args):
        executions.append(args)
        return 'Fake send completed'

    monkeypatch.setattr(agent, 'create_chat_model', lambda **kwargs: MemoryModel())
    monkeypatch.setattr(agent, 'llm_router', SimpleNamespace(invoke=lambda _: SimpleNamespace(classification='respond')))
    monkeypatch.setattr(agent, 'llm_with_tools', SimpleNamespace(invoke=plan))
    monkeypatch.setattr(agent, 'tools_by_name', {'send_email_tool': SimpleNamespace(invoke=execute)})
    monkeypatch.setattr(agent, 'mark_as_read', lambda message_id: reads.append(message_id))
    store = InMemoryStore()
    graph = agent.overall_workflow.compile(store=store, checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': choice}}
    first = graph.invoke({'email_input': EMAIL}, config)
    request = first['__interrupt__'][0].value[0]['action_request']
    assert request['action'] == 'send_email_tool'
    assert executions == reads == updates == []
    original = store.get(('email_assistant', 'response_preferences'), 'user_preferences').value
    response = {'type': choice}
    if choice == 'edit':
        response['args'] = {'args': {**request['args'], 'response_text': 'Short reply, Alex.'}}
    elif choice == 'response':
        response['args'] = UPDATED
    result = graph.invoke(Command(resume=[response]), config)
    if choice == 'response':
        assert executions == reads == []
        assert result['__interrupt__'][0].value[0]['action_request']['args']['response_text'] == 'Short reply, Alex.'
        result = graph.invoke(Command(resume=[{'type': 'accept'}]), config)
    assert graph.get_state(config).next == ()
    if choice == 'ignore':
        assert executions == reads == []
        assert store.get(('email_assistant', 'triage_preferences'), 'user_preferences').value == UPDATED
    else:
        assert len(executions) == 1
        assert reads == [EMAIL['id']]
        assert executions[0]['response_text'] == ('Original reply.' if choice == 'accept' else 'Short reply, Alex.')
    if choice in ('edit', 'response'):
        assert len(updates) == 1
        assert store.get(('email_assistant', 'response_preferences'), 'user_preferences').value == UPDATED
    elif choice == 'accept':
        assert not updates
        assert store.get(('email_assistant', 'response_preferences'), 'user_preferences').value == original


def test_question_answers_stay_in_thread_and_done_uses_original_gmail_id(agent, monkeypatch):
    def plan(messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content='', tool_calls=[{'name': 'Done', 'args': {'done': True}, 'id': 'done'}])
        return AIMessage(content='', tool_calls=[{'name': 'Question', 'args': {'content': 'Which build?'}, 'id': 'question'}])

    update, mark_read = Mock(), Mock()
    monkeypatch.setattr(agent, 'update_memory', update)
    monkeypatch.setattr(agent, 'mark_as_read', mark_read)
    monkeypatch.setattr(agent, 'llm_router', SimpleNamespace(invoke=lambda _: SimpleNamespace(classification='respond')))
    monkeypatch.setattr(agent, 'llm_with_tools', SimpleNamespace(invoke=plan))
    graph = agent.overall_workflow.compile(store=InMemoryStore(), checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'question'}}
    graph.invoke({'email_input': EMAIL}, config)
    result = graph.invoke(Command(resume=[{'type': 'response', 'args': 'Use test-build-007.'}]), config)
    assert any(isinstance(m, ToolMessage) and 'test-build-007' in m.content for m in result['messages'])
    update.assert_not_called()
    mark_read.assert_called_once_with(EMAIL['id'])


def test_send_builds_reply_using_original_message_and_gmail_thread(monkeypatch):
    from email_assistant.tools.gmail import gmail_tools as tools
    monkeypatch.setattr(tools, 'GMAIL_API_AVAILABLE', True)
    monkeypatch.setattr(tools, 'get_credentials', Mock(return_value=object()))
    service = Mock()
    api = service.users.return_value.messages.return_value
    api.get.return_value.execute.return_value = {'threadId': 'test-thread', 'payload': {'headers': [
        {'name': 'Subject', 'value': 'Test subject'}, {'name': 'From', 'value': 'Sender <sender@example.com>'}]}}
    api.send.return_value.execute.return_value = {'id': 'fake-sent-message'}
    monkeypatch.setattr(tools, 'build', Mock(return_value=service))
    assert tools.send_email('test-message', 'Received.', 'owner@example.com', ['cc@example.com'])
    body = api.send.call_args.kwargs['body']
    assert body['threadId'] == 'test-thread'
    message = message_from_bytes(base64.urlsafe_b64decode(body['raw']))
    assert message['To'] == 'Sender <sender@example.com>'
    assert message['Subject'] == 'Re: Test subject'
    assert message['Cc'] == 'cc@example.com'
    assert message.get_payload(decode=True).decode('utf-8') == 'Received.'


def test_mark_read_changes_only_the_target_messages_unread_label(monkeypatch):
    from email_assistant.tools.gmail import gmail_tools as tools
    monkeypatch.setattr(tools, 'get_credentials', Mock(return_value=object()))
    service = Mock()
    monkeypatch.setattr(tools, 'build', Mock(return_value=service))
    tools.mark_as_read('test-message')
    service.users.return_value.messages.return_value.modify.assert_called_once_with(
        userId='me', id='test-message', body={'removeLabelIds': ['UNREAD']})
