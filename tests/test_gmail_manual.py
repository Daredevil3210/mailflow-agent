import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('manual_test_helper', Path(__file__).resolve().parents[1] / 'src/email_assistant/tools/gmail/manual_test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RECORDS = tmp_path / 'records.json'
    monkeypatch.setitem(sys.modules, 'run_ingest', SimpleNamespace(extract_email_data=lambda m: {
        'from_email': 'sender@example.com', 'to_email': 'owner@example.com', 'subject': 'MailFlow-Test-Offline',
        'page_content': 'Test only', 'id': m['id'], 'thread_id': m['threadId']}))
    # submit adds an import path; restore it after each test.
    monkeypatch.setattr(sys, 'path', list(sys.path))
    return module


def args(subject='MailFlow-Test-Offline'):
    return SimpleNamespace(subject=subject, sender='sender@example.com', recipient='owner@example.com')


def test_rejects_non_test_subject_without_accessing_services(helper):
    helper.gmail = Mock(side_effect=AssertionError('Must not access Gmail'))
    with pytest.raises(ValueError):
        helper.submit(args('Personal mail'))
    helper.gmail.assert_not_called()


def test_repeated_subject_does_not_create_another_run(helper):
    helper.records = lambda: {'MailFlow-Test-Offline': {'thread_id': 'existing-thread'}}
    helper.gmail = Mock(side_effect=AssertionError('Must not access Gmail'))
    helper.client = Mock(side_effect=AssertionError('Must not start another run'))
    helper.submit(args())
    helper.gmail.assert_not_called()
    helper.client.assert_not_called()


def fake_gmail(helper, subject):
    service = Mock()
    service.__enter__ = Mock(return_value=service)
    service.__exit__ = Mock(return_value=False)
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {'messages': [{'id': 'test-mail'}]}
    messages.get.return_value.execute.return_value = {
        'id': 'test-mail', 'threadId': 'gmail-thread', 'payload': {'headers': [
            {'name': 'Subject', 'value': subject}, {'name': 'From', 'value': 'sender@example.com'},
            {'name': 'To', 'value': 'owner@example.com'}]}}
    helper.gmail = Mock(return_value=service)
    return messages


def test_near_subject_match_is_not_submitted(helper):
    fake_gmail(helper, 'MailFlow-Test-Offline-Other')
    helper.client = Mock(side_effect=AssertionError('Wrong mail must not be submitted'))
    with pytest.raises(RuntimeError):
        helper.submit(args())
    helper.client.assert_not_called()


def test_exact_mail_creates_one_run_and_saves_record(helper):
    messages = fake_gmail(helper, 'MailFlow-Test-Offline')
    c = Mock()
    c.runs.create.return_value = {'run_id': 'test-run', 'status': 'pending'}
    helper.client = Mock(return_value=c)
    helper.submit(args())
    c.threads.create.assert_called_once()
    c.runs.create.assert_called_once()
    call = c.runs.create.call_args
    assert call.kwargs['input']['email_input']['id'] == 'test-mail'
    assert 'command' not in call.kwargs
    assert helper.records()['MailFlow-Test-Offline']['run_id'] == 'test-run'
    assert 'in:inbox' in messages.list.call_args.kwargs['q']


def test_nested_state_visits_subgraph_tasks(helper):
    nested = {'values': {}, 'tasks': [{'name': 'interrupt_handler', 'interrupts': [{'id': 'review'}]}]}
    root = {'tasks': [{'name': 'response_agent', 'state': nested}]}
    parts = list(helper.state_parts(root))
    assert any(p.get('name') == 'interrupt_handler' for p in parts)
