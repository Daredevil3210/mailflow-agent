"""Read headers of a few matching Gmail messages to verify local OAuth setup."""

import argparse
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        default="subject:MailFlow-Read-Test newer_than:7d",
        help="Gmail search query; defaults to the dedicated test subject.",
    )
    args = parser.parse_args()
    token_path = Path(__file__).resolve().parent / ".secrets" / "token.json"
    if not token_path.is_file():
        print("Missing .secrets/token.json. Complete setup_gmail.py first.")
        return 1

    try:
        credentials = Credentials.from_authorized_user_file(str(token_path))
        if not credentials.valid:
            if not credentials.refresh_token:
                print("No usable refresh token. Run setup_gmail.py again.")
                return 1
            credentials.refresh(Request())
            token_path.write_text(credentials.to_json(), encoding="utf-8")

        with build("gmail", "v1", credentials=credentials, cache_discovery=False) as service:
            result = service.users().messages().list(
                userId="me", q=args.query, maxResults=3
            ).execute()
            messages = result.get("messages", [])
            if not messages:
                print("Gmail connection succeeded; no messages matched the query.")
                print("Send a message titled MailFlow-Read-Test, then run again.")
                return 0

            for index, item in enumerate(messages, start=1):
                message = service.users().messages().get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()
                headers = {
                    h["name"].lower(): h["value"]
                    for h in message.get("payload", {}).get("headers", [])
                }
                print(f"\nMessage {index}")
                for name in ("From", "To", "Subject", "Date"):
                    print(f"{name}: {headers.get(name.lower(), '(missing)')}")
            print(f"\nRead check passed: {len(messages)} matching message(s).")
        return 0
    except HttpError as error:
        print(f"Gmail API request failed (HTTP {error.resp.status}).")
        print("Check API enablement and the permissions granted during OAuth setup.")
        return 1
    except Exception as error:
        # Do not print credentials, tokens, or arbitrary server response bodies.
        print(f"Read check failed ({type(error).__name__}).")
        print("Check your connection and local OAuth setup, then retry.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
