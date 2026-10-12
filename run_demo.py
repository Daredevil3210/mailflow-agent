"""Run one email through the basic assistant with simulated email tools."""

from email_assistant.models import load_project_env


def main() -> None:
    load_project_env()
    from email_assistant.email_assistant import email_assistant

    email = {
        "author": "Alice <alice@example.com>",
        "to": "Lance Martin <lance@company.com>",
        "subject": "Please confirm receipt of the API document",
        "email_thread": (
            "Hi Lance, I sent you the updated API document. "
            "Please reply to confirm receipt. No meeting is needed."
        ),
    }
    result = email_assistant.invoke(
        {"email_input": email}, config={"recursion_limit": 20}
    )
    print("Classification:", result.get("classification_decision"))
    for message in result.get("messages", []):
        message.pretty_print()


if __name__ == "__main__":
    main()
