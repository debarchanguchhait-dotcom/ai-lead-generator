
import json
import re
import sqlite3
import smtplib
import time
import urllib.parse
from datetime import datetime, timezone
from email.message import EmailMessage

import pandas as pd
import requests
import streamlit as st
from ddgs import DDGS
from google import genai
from google.genai import types


# =====================================================
# NEXORA AUTOMATIONS — AI LEAD AGENT 2.0
# =====================================================

st.set_page_config(
    page_title="NEXORA | AI Lead Agent",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 NEXORA AUTOMATIONS")
st.subheader("AI Lead Generation & Interest Alert Agent")
st.caption("Prospecting • Lead Management • Instant Email Notifications")

DB_PATH = "nexora_leads.db"


# =====================================================
# 1. SECURE CONFIGURATION
# =====================================================

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


GEMINI_KEY = get_secret("GEMINI_API_KEY")
GEMINI_MODEL = get_secret("GEMINI_MODEL", "gemini-2.5-flash")

OWNER_EMAIL = get_secret("OWNER_EMAIL")
SMTP_HOST = get_secret("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(get_secret("SMTP_PORT", 587))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_APP_PASSWORD")

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")

NTFY_TOPIC = get_secret("NTFY_TOPIC")
TG_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TG_CHAT = get_secret("TELEGRAM_CHAT_ID")

COMPANY_NAME = get_secret("COMPANY_NAME", "NEXORA AUTOMATIONS")
OFFER_DESC = get_secret(
    "OFFER_DESC",
    "AI automation and lead management services"
)

BOOKING_LINK = get_secret("BOOKING_LINK")

GOOGLE_SHEET_ID = get_secret("GOOGLE_SHEET_ID")


# =====================================================
# 2. DATABASE
# =====================================================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                name TEXT,
                email TEXT,
                company TEXT,
                message TEXT,
                intent_score INTEGER,
                source TEXT,
                status TEXT
            )
        """)


def save_lead(lead):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO leads (
                created_at, name, email, company,
                message, intent_score, source, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("company", ""),
            lead.get("message", ""),
            lead.get("intent_score", 0),
            lead.get("source", "Website"),
            "New"
        ))


def get_leads():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT * FROM leads ORDER BY id DESC",
            conn
        )


def update_lead_status(lead_id, status):
    allowed = ["New", "Contacted", "Interested", "Converted", "Closed"]

    if status not in allowed:
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE leads SET status=? WHERE id=?",
            (status, int(lead_id))
        )


init_db()


# =====================================================
# 3. GEMINI AI
# =====================================================

def get_gemini_client():
    if not GEMINI_KEY:
        raise RuntimeError(
            "Gemini API key is missing from Streamlit Secrets."
        )

    return genai.Client(api_key=GEMINI_KEY)


def ask_gemini(prompt):
    client = get_gemini_client()

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            if not response.text:
                raise RuntimeError("Gemini returned an empty response.")

            text = response.text.strip()

            if text.startswith("```"):
                text = re.sub(
                    r"^```(?:json)?\s*|\s*```$",
                    "",
                    text,
                    flags=re.IGNORECASE
                )

            return json.loads(text)

        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)

    raise RuntimeError("AI service unavailable.")


# =====================================================
# 4. EMAIL NOTIFICATIONS
# =====================================================

def email_is_configured():
    return bool(
        OWNER_EMAIL and SMTP_USER and SMTP_PASSWORD
    )


def send_email(subject, body, reply_to=None):

    if not email_is_configured():
        raise RuntimeError(
            "Email is not configured. Check Streamlit Secrets."
        )

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = SMTP_USER
    message["To"] = OWNER_EMAIL

    if reply_to:
        message["Reply-To"] = reply_to

    message.set_content(body)

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT,
        timeout=20
    ) as server:

        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)

        server.send_message(message)

    return True


# =====================================================
# 5. OPTIONAL PUSH NOTIFICATIONS
# =====================================================

def send_push_alert(text):

    sent = []

    if NTFY_TOPIC:

        try:
            topic = NTFY_TOPIC.strip()

            # Topic must be a simple topic name, not a URL.
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", topic):
                raise ValueError("Invalid ntfy topic.")

            response = requests.post(
                f"https://ntfy.sh/{topic}",
                data=text.encode("utf-8"),
                headers={"Title": "NEXORA - New Lead"},
                timeout=10
            )

            if response.ok:
                sent.append("ntfy")

        except Exception:
            pass

    if TG_TOKEN and TG_CHAT:

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={
                    "chat_id": TG_CHAT,
                    "text": text
                },
                timeout=10
            )

            if response.ok:
                sent.append("Telegram")

        except Exception:
            pass

    return sent


# =====================================================
# 6. LEAD SCORING
# =====================================================

def score_inquiry(message):

    text = message.lower()

    strong_words = [
        "pricing", "price", "quote", "hire",
        "interested", "automation", "project",
        "consultation", "start", "services"
    ]

    medium_words = [
        "information", "details", "business",
        "help", "contact", "demo"
    ]

    score = 2

    score += sum(
        1 for word in strong_words if word in text
    )

    score += sum(
        1 for word in medium_words if word in text
    )

    return min(score, 10)


# =====================================================
# 7. OPTIONAL GOOGLE SHEETS STORAGE
# =====================================================

def save_to_google_sheets(lead):

    if not GOOGLE_SHEET_ID:
        return False

    try:
        import gspread

        if "gcp_service_account" not in st.secrets:
            return False

        credentials = dict(st.secrets["gcp_service_account"])

        gc = gspread.service_account_from_dict(credentials)

        sheet = gc.open_by_key(GOOGLE_SHEET_ID)

        try:
            worksheet = sheet.worksheet("Leads")
        except gspread.WorksheetNotFound:
            worksheet = sheet.add_worksheet(
                title="Leads",
                rows=1000,
                cols=9
            )

        if not worksheet.row_values(1):
            worksheet.append_row([
                "Date",
                "Name",
                "Email",
                "Company",
                "Message",
                "Score",
                "Source",
                "Status"
            ])

        worksheet.append_row([
            datetime.now(timezone.utc).isoformat(),
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("company", ""),
            lead.get("message", ""),
            lead.get("intent_score", 0),
            lead.get("source", "Website"),
            "New"
        ])

        return True

    except Exception:
        return False


# =====================================================
# 8. INBOUND INTEREST CAPTURE
# =====================================================

def valid_email(email):
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            email.strip()
        )
    )


def process_inquiry(name, email, company, message):

    score = score_inquiry(message)

    lead = {
        "name": name.strip(),
        "email": email.strip(),
        "company": company.strip(),
        "message": message.strip(),
        "intent_score": score,
        "source": "Website"
    }

    # Save first, so an email failure does not lose the lead.
    save_lead(lead)

    # Optional durable backup.
    sheet_saved = save_to_google_sheets(lead)

    alert = (
        "NEW NEXORA CLIENT ENQUIRY\n\n"
        f"Name: {lead['name']}\n"
        f"Email: {lead['email']}\n"
        f"Business: {lead['company']}\n"
        f"Intent Score: {score}/10\n\n"
        f"Message:\n{lead['message']}\n\n"
        "Please review and contact the client."
    )

    email_sent = False
    email_error = None

    try:
        send_email(
            subject=f"New Client Enquiry - {lead['name']}",
            body=alert,
            reply_to=lead["email"]
        )

        email_sent = True

    except Exception as error:
        email_error = str(error)

    push_sent = send_push_alert(alert)

    return {
        "lead": lead,
        "email_sent": email_sent,
        "email_error": email_error,
        "push_sent": push_sent,
        "sheet_saved": sheet_saved
    }


# =====================================================
# 9. PUBLIC WEBSITE CONTACT FORM
# =====================================================

def show_contact_form():

    st.header("📩 Start Your Automation Project")

    st.write(
        "Tell us about your business. "
        "The NEXORA team will review your enquiry."
    )

    with st.form("nexora_contact_form"):

        name = st.text_input("Full Name *")

        email = st.text_input("Email Address *")

        company = st.text_input("Business Name (Optional)")

        message = st.text_area(
            "What would you like to automate? *",
            height=130
        )

        consent = st.checkbox(
            "I agree to submit these details so NEXORA "
            "can respond to my enquiry."
        )

        submitted = st.form_submit_button(
            "🚀 Submit Enquiry",
            type="primary",
            use_container_width=True
        )

    if submitted:

        if not name.strip() or not email.strip() or not message.strip():
            st.warning("Please complete all required fields.")

        elif len(name) > 100 or len(message) > 3000:
            st.warning("Please shorten your submitted information.")

        elif not valid_email(email):
            st.warning("Please enter a valid email address.")

        elif not consent:
            st.warning("Please agree before submitting.")

        else:

            try:
                result = process_inquiry(
                    name, email, company, message
                )

                st.success(
                    "Your enquiry has been recorded successfully."
                )

                if result["email_sent"]:
                    st.success(
                        "The NEXORA owner has received an email notification."
                    )
                else:
                    st.error(
                        "Your enquiry was saved, but the email notification "
                        "failed. The owner should check the app logs."
                    )

                if result["push_sent"]:
                    st.caption(
                        "Additional push alert sent: "
                        + ", ".join(result["push_sent"])
                    )

                if result["sheet_saved"]:
                    st.caption("Lead backup saved to Google Sheets.")

            except Exception as error:
                st.error(f"Unable to process enquiry: {error}")


# =====================================================
# 10. OUTBOUND LEAD FINDER
# =====================================================

def find_business_prospects(audience, number):

    with DDGS() as search:

        results = list(
            search.text(
                audience,
                max_results=20
            )
        )

    if not results:
        raise RuntimeError(
            "No search results. Try another business category."
        )

    prompt = f"""
You are a careful B2B prospect research assistant.

Agency:
{COMPANY_NAME}

Agency offer:
{OFFER_DESC}

Target business audience:
{audience}

Search results:
{json.dumps(results[:20], ensure_ascii=False)}

Return a JSON array containing up to {number} distinct businesses.

Each object must contain:
- lead_name
- contact_email
- website
- fit_score (integer 1 to 10)
- fit_reason
- email_subject
- email_body

STRICT RULES:
1. Only identify businesses supported by the supplied search results.
2. Never invent company names, emails or websites.
3. Only provide an email if it appears explicitly in the supplied results.
4. If no email is shown, return an empty string.
5. Prefer publicly listed business contact details.
6. Do not guess personal email addresses.
7. Generate a polite, personalized draft.
8. Do not claim to have contacted the business.
9. Do not generate bulk unsolicited marketing.
10. Return valid JSON only.
"""

    return ask_gemini(prompt)


def show_outbound_finder():

    st.header("🚀 AI Outbound Lead Finder")

    audience = st.text_input(
        "Describe your ideal customer",
        placeholder="Small coaching institutes in Kolkata"
    )

    number = st.slider(
        "Number of businesses to research",
        1, 10, 3
    )

    if st.button(
        "🔍 Find Business Prospects",
        type="primary"
    ):

        if not GEMINI_KEY:
            st.error("Configure Gemini API key in Streamlit Secrets.")

        elif not audience.strip():
            st.warning("Enter your target business audience.")

        else:

            try:

                with st.spinner("Researching businesses..."):

                    prospects = find_business_prospects(
                        audience, number
                    )

                if not isinstance(prospects, list):
                    raise ValueError("Unexpected AI response format.")

                df = pd.DataFrame(prospects)

                if df.empty:
                    st.info("No suitable prospects found.")
                else:

                    st.dataframe(
                        df,
                        use_container_width=True
                    )

                    for i, lead in enumerate(prospects):

                        with st.expander(
                            f"{lead.get('lead_name', 'Business')} "
                            f"— {lead.get('fit_score', 0)}/10"
                        ):

                            st.write(
                                lead.get("fit_reason", "")
                            )

                            st.write(
                                "Website:",
                                lead.get("website", "Not found")
                            )

                            email = lead.get("contact_email", "")

                            if email:
                                st.write("Public email:", email)
                            else:
                                st.info(
                                    "No verified public email found. "
                                    "Use the business's official contact page."
                                )

                            subject = st.text_input(
                                "Email subject",
                                value=lead.get("email_subject", ""),
                                key=f"subject_{i}"
                            )

                            body = st.text_area(
                                "Personalized email draft",
                                value=lead.get("email_body", ""),
                                height=150,
                                key=f"body_{i}"
                            )

                            if email:
                                gmail_url = (
                                    "https://mail.google.com/mail/?view=cm&fs=1"
                                    + "&to=" + urllib.parse.quote(email)
                                    + "&su=" + urllib.parse.quote(subject)
                                    + "&body=" + urllib.parse.quote(body)
                                )

                                st.link_button(
                                    "✉️ Review Draft in Gmail",
                                    gmail_url
                                )

                    st.download_button(
                        "📥 Download Prospects CSV",
                        data=df.to_csv(index=False).encode("utf-8"),
                        file_name="nexora_prospects.csv",
                        mime="text/csv"
                    )

            except Exception as error:
                st.error(f"Lead research failed: {error}")


# =====================================================
# 11. ADMIN DASHBOARD
# =====================================================

def show_admin_dashboard():

    st.header("📊 NEXORA Admin Dashboard")

    df = get_leads()

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Leads", len(df))

    if not df.empty:

        col2.metric(
            "New Leads",
            int((df["status"] == "New").sum())
        )

        col3.metric(
            "Interested",
            int((df["status"] == "Interested").sum())
        )

        st.subheader("Recent Enquiries")

        st.dataframe(
            df,
            use_container_width=True
        )

        st.subheader("Update Lead Status")

        selected_id = st.selectbox(
            "Select lead ID",
            df["id"].tolist()
        )

        new_status = st.selectbox(
            "New status",
            ["New", "Contacted", "Interested", "Converted", "Closed"]
        )

        if st.button("Update Status"):
            update_lead_status(selected_id, new_status)
            st.success("Lead status updated.")
            st.rerun()

        st.download_button(
            "Download All Leads",
            df.to_csv(index=False).encode("utf-8"),
            "nexora_leads.csv",
            "text/csv"
        )

    else:
        col2.metric("New Leads", 0)
        col3.metric("Interested", 0)
        st.info("No enquiries have arrived yet.")

    st.caption(
        "Database: local SQLite. For durable cloud storage, "
        "configure Google Sheets integration."
    )


# =====================================================
# 12. APPLICATION NAVIGATION
# =====================================================

with st.sidebar:

    s
