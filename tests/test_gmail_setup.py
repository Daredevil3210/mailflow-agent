"""Exercise OAuth setup and read-only checks with no real credentials or network."""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from googleapiclient.errors import HttpError
from httplib2 import Response


SCRIPTS = Path(__file__).resolve().parents[1] / "src/email_assistant/tools/gmail"


def load_script(name, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(f"gmail_test_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # setup_gmail adjusts sys.path at import; retain the test environment afterward.
    original_path = sys.path[:]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    monkeypatch.setattr(module, "__file__", str(tmp_path / f"{name}.py"))
    monkeypatch.setattr(sys, "argv", [f"{name}.py"])
    return module


def create_fake_token(tmp_path):
    folder = tmp_path / ".secrets"
    folder.mkdir(exist_ok=True)
    token = folder / "token.json"
    token.write_text("{}", encoding="utf-8")
    return token


def mock_read_client(module, monkeypatch, *, messages=None, headers=None, valid=True):
    credentials = Mock()
    credentials.valid = valid
    credentials.refresh_token = "dummy-refresh"
    credentials.to_json.return_value = '{"test_only": true}'
    loader = Mock(return_value=credentials)
    monkeypatch.setattr(module.Credentials, "from_authorized_user_file", loader)
    service = Mock()
    message_api = service.users.return_value.messages.return_value
    message_api.list.return_value.execute.return_value = {"messages": messages or []}
    message_api.get.return_value.execute.return_value = {"payload": {"headers": headers or []}}
    client = Mock()
    client.__enter__ = Mock(return_value=service)
    client.__exit__ = Mock(return_value=False)
    build = Mock(return_value=client)
    monkeypatch.setattr(module, "build", build)
    return credentials, loader, message_api, build


def test_setup_missing_application_credentials_does_not_start_oauth(tmp_path, monkeypatch):
    module = load_script("setup_gmail", tmp_path, monkeypatch)
    flow = Mock()
    monkeypatch.setattr(module, "InstalledAppFlow", flow)
    assert module.main() == 1
    flow.from_client_secrets_file.assert_not_called()
    assert not (tmp_path / ".secrets/token.json").exists()


def test_setup_passes_scopes_to_browser_flow_and_saves_authorization(tmp_path, monkeypatch):
    module = load_script("setup_gmail", tmp_path, monkeypatch)
    folder = tmp_path / ".secrets"
    folder.mkdir()
    (folder / "secrets.json").write_text('{"installed": {}}', encoding="utf-8")
    credentials = SimpleNamespace(
        token="dummy-access", refresh_token="dummy-refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client", client_secret="test-secret",
        scopes=["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar"],
        expiry=datetime(2030, 1, 1),
    )
    flow = Mock()
    flow.run_local_server.return_value = credentials
    factory = Mock(return_value=flow)
    monkeypatch.setattr(module.InstalledAppFlow, "from_client_secrets_file", factory)
    assert module.main() == 0
    factory.assert_called_once_with(str(folder / "secrets.json"), credentials.scopes)
    flow.run_local_server.assert_called_once_with(port=0)
    saved = json.loads((folder / "token.json").read_text(encoding="utf-8"))
    assert saved["token"] == "dummy-access"
    assert saved["refresh_token"] == "dummy-refresh"
    assert saved["expiry"] == "2030-01-01T00:00:00Z"


def test_read_missing_token_stops_before_api_client_creation(tmp_path, monkeypatch):
    module = load_script("check_gmail_read", tmp_path, monkeypatch)
    build = Mock()
    monkeypatch.setattr(module, "build", build)
    assert module.main() == 1
    build.assert_not_called()


def test_read_no_matches_is_success_with_bounded_test_query(tmp_path, monkeypatch, capsys):
    module = load_script("check_gmail_read", tmp_path, monkeypatch)
    token = create_fake_token(tmp_path)
    credentials, loader, api, build = mock_read_client(module, monkeypatch)
    assert module.main() == 0
    loader.assert_called_once_with(str(token))
    credentials.refresh.assert_not_called()
    build.assert_called_once_with("gmail", "v1", credentials=credentials, cache_discovery=False)
    api.list.assert_called_once_with(userId="me", q="subject:MailFlow-Read-Test newer_than:7d", maxResults=3)
    api.get.assert_not_called()
    assert "connection succeeded" in capsys.readouterr().out


def test_read_refreshes_token_and_fetches_metadata_without_mail_writes(tmp_path, monkeypatch, capsys):
    module = load_script("check_gmail_read", tmp_path, monkeypatch)
    token = create_fake_token(tmp_path)
    headers = [{"name": "sUbJeCt", "value": "MailFlow-Read-Test"},
               {"name": "From", "value": "sender@example.com"}]
    credentials, _, api, _ = mock_read_client(
        module, monkeypatch, messages=[{"id": "test-message"}], headers=headers, valid=False,
    )
    monkeypatch.setattr(module, "Request", Mock(return_value="fake-transport"))
    assert module.main() == 0
    credentials.refresh.assert_called_once_with("fake-transport")
    assert json.loads(token.read_text(encoding="utf-8")) == {"test_only": True}
    api.get.assert_called_once_with(
        userId="me", id="test-message", format="metadata",
        metadataHeaders=["From", "To", "Subject", "Date"],
    )
    assert {call[0] for call in api.method_calls} == {"list", "get"}
    output = capsys.readouterr().out
    assert "Subject: MailFlow-Read-Test" in output
    assert "To: (missing)" in output
    assert "dummy-refresh" not in output


def test_api_failure_reports_status_without_printing_response_body(tmp_path, monkeypatch, capsys):
    module = load_script("check_gmail_read", tmp_path, monkeypatch)
    create_fake_token(tmp_path)
    _, _, api, _ = mock_read_client(module, monkeypatch)
    api.list.return_value.execute.side_effect = HttpError(
        Response({"status": "403"}), b'{"error":{"message":"private test detail"}}',
    )
    assert module.main() == 1
    output = capsys.readouterr().out
    assert "HTTP 403" in output
    assert "private test detail" not in output
