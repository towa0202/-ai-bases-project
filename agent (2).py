import os
import time
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google import genai

# ============================================================
#  CONFIG
# ============================================================
MY_NAME       = "Sheikh Mohammad Abdullah"
MY_ROLE       = "Software Engineering Student | ML & Data Science"
FB_LINK       = "https://www.facebook.com/Sheikhabdullah00099"
LINKEDIN_LINK = "https://www.linkedin.com/in/abdullah-mahin-14112428"

# Environment variable থেকে key নাও (নিচে দেখো কিভাবে set করতে হয়)
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

CHECK_INTERVAL = 30

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

SKIP_KEYWORDS = [
    "noreply", "no-reply", "newsletter", "notifications",
    "alerts", "donotreply", "linkedin", "canva", "aliexpress",
    "amazon", "facebook", "instagram", "twitter", "bayt.com",
    "support@", "notify@", "engage.", "classroom.google",
    "cvwizard", "product@"
]
# ============================================================


def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def get_unread_emails(service):
    result = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        q="is:unread newer_than:7d",
        maxResults=20
    ).execute()
    return result.get("messages", [])


def get_email_details(service, msg_id):
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = msg["payload"].get("headers", [])
    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
    sender  = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
    thread_id = msg["threadId"]

    body = ""
    payload = msg["payload"]
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                break
    elif "body" in payload:
        data = payload["body"].get("data", "")
        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    return subject, sender, body[:2000], thread_id


def generate_reply(subject, sender, body):
    client = genai.Client(api_key=GEMINI_KEY)

    prompt = f"""You are an email reply assistant for {MY_NAME}, who is a {MY_ROLE}.

Write a professional and friendly auto-reply email for the incoming email below.

RULES:
- Start by thanking them for reaching out
- Briefly acknowledge their email topic
- Invite them to connect via Facebook and LinkedIn (mention both links naturally)
- End with a warm sign-off using {MY_NAME}'s name
- Keep it concise — 3 to 4 short paragraphs max
- Do NOT use placeholder text

INCOMING EMAIL:
From: {sender}
Subject: {subject}
Body: {body if body else '(No body content)'}

SOCIAL LINKS TO INCLUDE:
Facebook: {FB_LINK}
LinkedIn: {LINKEDIN_LINK}

Write only the email reply text. No extra commentary."""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text


def send_reply(service, thread_id, sender_email, subject, reply_text):
    if "<" in sender_email:
        to_address = sender_email.split("<")[1].replace(">", "").strip()
    else:
        to_address = sender_email.strip()

    mime_msg = MIMEText(reply_text)
    mime_msg["to"]      = to_address
    mime_msg["subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id}
    ).execute()


def mark_as_read(service, msg_id):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def main():
    print("=" * 50)
    print("  Gmail Auto-Reply Agent — Sheikh Mohammad Abdullah")
    print("  Powered by Gemini AI (Free)")
    print("=" * 50)
    print(f"  Checking every {CHECK_INTERVAL} seconds...\n")

    service = get_gmail_service()
    print("✅ Gmail connected successfully!\n")

    replied_ids = set()

    while True:
        try:
            emails = get_unread_emails(service)

            if emails:
                print(f"📬 {len(emails)} unread email(s) found.")
            else:
                print("📭 No new emails. Waiting...")

            for email in emails:
                msg_id = email["id"]
                if msg_id in replied_ids:
                    continue

                subject, sender, body, thread_id = get_email_details(service, msg_id)
                print(f"\n  → From: {sender}")
                print(f"    Subject: {subject}")

                if any(kw in sender.lower() for kw in SKIP_KEYWORDS):
                    print("    ⏭️  Skipping (noreply/newsletter)")
                    mark_as_read(service, msg_id)
                    replied_ids.add(msg_id)
                    continue

                print("    🤖 Generating AI reply...")

                try:
                    reply_text = generate_reply(subject, sender, body)
                    send_reply(service, thread_id, sender, subject, reply_text)
                    mark_as_read(service, msg_id)
                    replied_ids.add(msg_id)
                    print("    ✅ Reply sent!")

                except Exception as e:
                    if "RESOURCE_EXHAUSTED" in str(e):
                        print("    ⏳ Quota exceeded. Waiting 60 seconds...")
                        time.sleep(60)
                    else:
                        print(f"    ❌ Gemini Error: {e}")
                        mark_as_read(service, msg_id)
                        replied_ids.add(msg_id)

        except Exception as e:
            print(f"\n❌ Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
