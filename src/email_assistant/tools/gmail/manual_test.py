"""Submit one named test mail or inspect results; never accepts or sends mail."""
import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RECORDS = ROOT / '.local-backups/manual-gmail-tests.json'
URL = 'http://127.0.0.1:2024'
GRAPH = 'email_assistant_hitl_memory_gmail'


def client():
    from langgraph_sdk import get_sync_client
    return get_sync_client(url=URL, api_key=None)


def gmail():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    path = ROOT / 'src/email_assistant/tools/gmail/.secrets/token.json'
    credentials = Credentials.from_authorized_user_file(str(path))
    if not credentials.valid:
        if not credentials.refresh_token:
            raise RuntimeError('Missing refresh token; run setup_gmail.py first')
        credentials.refresh(Request())
        path.write_text(credentials.to_json(), encoding='utf-8')
    return build('gmail', 'v1', credentials=credentials, cache_discovery=False)


def records():
    return json.loads(RECORDS.read_text(encoding='utf-8')) if RECORDS.exists() else {}


def record(subject):
    result = records().get(subject)
    if result is None:
        raise RuntimeError('This subject has not been submitted by this helper')
    return result


def print_link(item):
    print('Thread ID:', item['thread_id'])
    print('Studio: https://smith.langchain.com/studio/thread?baseUrl=http%3A%2F%2F127.0.0.1%3A2024'
          f"&threadId={item['thread_id']}&assistantId={GRAPH}&render=interact&mode=graph")


def submit(args):
    if not args.subject.startswith('MailFlow-Test-'):
        raise ValueError('Test subjects must start with MailFlow-Test-')
    saved = records()
    if args.subject in saved:
        print('Already submitted; use this existing thread. For a repeat, send a new unique subject.')
        print_link(saved[args.subject])
        return
    sys.path.insert(0, str(ROOT / 'src/email_assistant/tools/gmail'))
    from run_ingest import extract_email_data
    from email.utils import parseaddr
    with gmail() as service:
        query = f'in:inbox subject:"{args.subject}" from:{args.sender} to:{args.recipient} newer_than:7d'
        matches = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
        exact = []
        for match in matches.get('messages', []):
            mail = service.users().messages().get(userId='me', id=match['id'], format='metadata',
                metadataHeaders=['Subject', 'From', 'To']).execute()
            headers = {h['name'].lower(): h['value'] for h in mail.get('payload', {}).get('headers', [])}
            if (headers.get('subject') == args.subject
                    and parseaddr(headers.get('from', ''))[1].lower() == args.sender.lower()
                    and parseaddr(headers.get('to', ''))[1].lower() == args.recipient.lower()):
                exact.append(match)
        if len(exact) != 1 or matches.get('nextPageToken'):
            raise RuntimeError(f'Expected exactly one matching test mail; found {len(exact)}. Use a unique subject.')
        message = service.users().messages().get(userId='me', id=exact[0]['id']).execute()
        data = extract_email_data(message)
    c = client()
    thread_id = str(uuid.uuid4())
    c.threads.create(thread_id=thread_id, metadata={'purpose': 'manual-gmail-test', 'subject': args.subject})
    run = c.runs.create(thread_id, GRAPH, input={'email_input': {
        'from': data['from_email'], 'to': data['to_email'], 'subject': data['subject'],
        'body': data['page_content'], 'id': data['id']}}, config={'recursion_limit': 20})
    item = {'thread_id': thread_id, 'run_id': run['run_id'], 'email_id': data['id'],
            'gmail_thread_id': data['thread_id']}
    saved[args.subject] = item
    RECORDS.parent.mkdir(parents=True, exist_ok=True)
    RECORDS.write_text(json.dumps(saved, indent=2), encoding='utf-8')
    print('Submitted:', args.subject, '| status:', run['status'])
    print_link(item)


def state_parts(state):
    yield state
    for task in state.get('tasks', []):
        yield task
        nested = task.get('state')
        if isinstance(nested, dict):
            yield from state_parts(nested)


def status(args):
    item = record(args.subject)
    c = client()
    print_link(item)
    runs = c.runs.list(item['thread_id'], limit=3)
    print('Recent run statuses:', [run['status'] for run in runs])
    state = c.threads.get_state(item['thread_id'], subgraphs=True)
    print('Next nodes:', state.get('next', []))
    seen_interrupts, seen_messages = set(), set()
    for part in state_parts(state):
        if part.get('error'):
            print('Task error:', part['error'])
        for interrupt in part.get('interrupts', []):
            key = interrupt.get('id') or json.dumps(interrupt, sort_keys=True)
            if key not in seen_interrupts:
                seen_interrupts.add(key)
                print('Pending review:', json.dumps(interrupt.get('value'), ensure_ascii=False, indent=2))
        for message in part.get('values', {}).get('messages', []):
            if message.get('type') == 'tool' or message.get('role') == 'tool':
                key = message.get('id') or (message.get('tool_call_id'), str(message.get('content')))
                if key not in seen_messages:
                    seen_messages.add(key)
                    print('Tool result:', message.get('content'))
    if not seen_interrupts:
        print('No pending review in saved state; check run status before treating the task as complete.')


def memory(args):
    c = client()
    snapshot = {}
    for name in ('triage_preferences', 'response_preferences', 'cal_preferences'):
        try:
            item = c.store.get_item(['email_assistant', name], 'user_preferences')
            snapshot[name] = item.get('value') if item else None
        except Exception as error:
            response = getattr(error, 'response', None)
            if response is not None and response.status_code == 404:
                snapshot[name] = None
            else:
                raise
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    if args.save:
        if not args.save.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Snapshot labels must contain only letters, digits, hyphens, or underscores')
        path = ROOT / '.local-backups' / f'memory-{args.save}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Snapshot:', path)


def verify(args):
    item = record(args.subject)
    with gmail() as service:
        original = service.users().messages().get(userId='me', id=item['email_id'], format='minimal').execute()
        print('Original marked read:', 'UNREAD' not in original.get('labelIds', []))
        thread = service.users().threads().get(userId='me', id=item['gmail_thread_id'], format='metadata',
            metadataHeaders=['From', 'To', 'Subject', 'Date']).execute()
        sent = []
        for mail in thread.get('messages', []):
            if 'SENT' in mail.get('labelIds', []) and mail['id'] != item['email_id']:
                headers = {h['name'].lower(): h['value'] for h in mail.get('payload', {}).get('headers', [])}
                sent.append({'id': mail['id'], **headers})
        print('Sent replies:', json.dumps(sent, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('submit', help='Submit exactly one test mail to a fresh thread')
    p.add_argument('--subject', required=True)
    p.add_argument('--sender', required=True)
    p.add_argument('--recipient', required=True)
    for name in ('status', 'verify'):
        p = commands.add_parser(name)
        p.add_argument('--subject', required=True)
    p = commands.add_parser('memory', help='Read server preference profiles, optionally saving a snapshot')
    p.add_argument('--save')
    args = parser.parse_args()
    try:
        globals()[args.command](args)
        return 0
    except Exception as error:
        print('Failed:', type(error).__name__)
        if isinstance(error, (RuntimeError, ValueError)):
            print(str(error))
        else:
            print('Check the local server, OAuth setup and network. No automatic resume or retry was performed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
