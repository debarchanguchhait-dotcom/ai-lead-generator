import json
import urllib.parse
import requests
import pandas as pd
import streamlit as st
from ddgs import DDGS
from google import genai
from google.genai import types

st.set_page_config(page_title="AI Lead Generation & Alert Agent", page_icon="🎯", layout="wide")

st.title("🎯 AI Lead Generation & Interest Alert Agent")
st.caption("100% Free Stack • Outbound Prospecting + Instant Inbound Alerts")

with st.sidebar:
    st.header("1. AI Setup (Required)")
    gemini_key = st.text_input(
        "Free Google Gemini API Key",
        type="password",
        help="Get a free key at ://google.com"
    )
    st.markdown("[Get a free Gemini API key →](https://://google.com)")

    st.divider()
    st.header("2. Business & Booking Info")
    company_name = st.text_input("Business Name", placeholder="e.g., Acme Solutions")
    offer_desc = st.text_area(
        "What do you sell?",
        placeholder="e.g., We help B2B companies automate lead generation and book 15+ calls/month."
    )
    booking_link = st.text_input(
        "Calendar Booking Link (Optional)",
        placeholder="e.g., https://cal.com"
    )

    st.divider()
    st.header("3. Instant Owner Alerts (Free)")
    st.caption("Get notified immediately when an inbound lead is interested:")
    alert_email = st.text_input("Owner Notification Email", placeholder="you@yourdomain.com")
    tg_bot_token = st.text_input("Telegram Bot Token (Optional)", type="password")
    tg_chat_id = st.text_input("Telegram Chat ID (Optional)", placeholder="e.g., 123456789")


def send_owner_alert(lead_info: dict):
    sent_channels = []
    summary_text = (
        f"🔥 NEW INTERESTED LEAD ({lead_info.get('intent_score', 'N/A')}/10)\n"
        f"Name: {lead_info.get('name')}\n"
        f"Email: {lead_info.get('email')}\n"
        f"Phone/Company: {lead_info.get('company')}\n"
        f"Need: {lead_info.get('message')}\n"
        f"AI Summary: {lead_info.get('ai_summary')}"
    )

    if tg_bot_token and tg_chat_id:
        try:
            tg_url = f"https://telegram.org{tg_bot_token}/sendMessage"
            requests.post(tg_url, json={"chat_id": tg_chat_id, "text": summary_text}, timeout=10)
            sent_channels.append("Telegram")
        except Exception:
            pass

    if alert_email:
        try:
            mail_url = f"https://formsubmit.co{alert_email}"
            requests.post(
                mail_url,
                json={
                    "_subject": f"🔥 Hot Lead Alert: {lead_info.get('name')}",
                    "Lead Name": lead_info.get("name"),
                    "Lead Email": lead_info.get("email"),
                    "Company / Phone": lead_info.get("company"),
                    "Interest Score": f"{lead_info.get('intent_score')}/10",
                    "Message": lead_info.get("message"),
                    "Suggested Reply": lead_info.get("suggested_reply")
                },
                headers={"Accept": "application/json"},
                timeout=10
            )
            sent_channels.append("Email")
        except Exception:
            pass

    return sent_channels


tab1, tab2 = st.tabs(["🚀 Outbound Lead Finder", "📩 Inbound Interest Capture"])

with tab1:
    st.subheader("Find Prospects & Send 1-Click Outreach")
    col1, col2 = st.columns([3, 1])
    with col1:
        target_audience = st.text_input(
            "Describe your Ideal Customer (ICP)",
            placeholder="e.g., Real estate agencies in Kolkata or SaaS founders in Bengaluru"
        )
    with col2:
        num_leads = st.number_input("Leads to find", min_value=3, max_value=15, value=5)

    if st.button("🔍 Find & Qualify Leads", type="primary"):
        if not gemini_key:
            st.error("Open the sidebar (>> top-left) and paste your free Google Gemini API key first.")
        elif not target_audience or not offer_desc:
            st.warning("Please enter your Ideal Customer above and 'What do you sell?' in the sidebar.")
        else:
            try:
                client = genai.Client(api_key=gemini_key)
                with st.status("Searching live web & qualifying leads...", expanded=True) as status:
                    q_prompt = (
                        f"Generate 3 targeted web search queries to find real companies, founders, "
                        f"and public contact emails matching: '{target_audience}'. "
                        f"Return ONLY a JSON array of 3 strings."
                    )
                    q_res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=q_prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    queries = json.loads(q_res.text)

                    raw_results = []
                    with DDGS() as ddgs:
                        for q in queries:
                            st.write(f"🌐 Searching: `{q}`")
                            raw_results.extend(list(ddgs.text(q, max_results=int(num_leads))))

                    if not raw_results:
                        st.error("No results found. Try a broader description.")
                        st.stop()

                    cta_instruction = (
                        f"End the email by inviting them to book a quick call here: {booking_link}"
                        if booking_link
                        else "End the email by asking if they are open to a quick 10-minute chat this week."
                    )

                    extract_prompt = f"""
                    Analyze these search results and extract up to {int(num_leads)} real businesses/decision-makers matching '{target_audience}'.
                    Search Results: {json.dumps(raw_results[:25])}

                    Sender Company: {company_name}
                    Sender Offer: {offer_desc}

                    Return a JSON array of objects with exact keys:
                    - "lead_name": Company or person name
                    - "contact_email": Public email found in snippet (or "" if none found)
                    - "website": URL from snippet
                    - "fit_score": Integer 1-10
                    - "fit_reason": 1 short sentence why they fit
                    - "email_subject": Short catchy subject line
                    - "email_body": 3-sentence personalized cold email. {cta_instruction}
                    """
                    leads_res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=extract_prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    leads_data = json.loads(leads_res.text)
                    status.update(label="✅ Leads ready!", state="complete", expanded=False)

                df = pd.DataFrame(leads_data)
                st.dataframe(
                    df[["lead_name", "contact_email", "website", "fit_score", "fit_reason"]],
                    use_container_width=True
                )

                st.subheader("📬 1-Click Outreach & Replies")
                st.caption("Click 'Open & Send in Gmail' to send directly from your inbox.")

                for idx, lead in enumerate(leads_data):
                    with st.expander(f"⭐ {lead['fit_score']}/10 — {lead['lead_name']} ({lead['website']})"):
                        st.write(f"**Why they fit:** {lead['fit_reason']}")
                        st.text_input("Subject", value=lead["email_subject"], key=f"subj_{idx}")
                        st.text_area("Drafted Email", value=lead["email_body"], height=120, key=f"body_{idx}")

                        to_email = urllib.parse.quote(lead.get("contact_email", ""))
                        subj_enc = urllib.parse.quote(lead["email_subject"])
                        body_enc = urllib.parse.quote(lead["email_body"])
                        gmail_url = f"https://google.com{to_email}&su={subj_enc}&body={body_enc}"

                        st.link_button("✉️ Open & Send in Gmail", gmail_url)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download All Leads (CSV)",
                    data=csv,
                    file_name="qualified_leads.csv",
                    mime="text/csv"
                )

            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    st.subheader(f"Get in Touch with {company_name or 'Us'}")
    st.write("Tell us what you're looking for, and our AI assistant will qualify your request and alert our team immediately.")

    with st.form("inbound_lead_form"):
        lead_name = st.text_input("Your Name *")
        lead_email = st.text_input("Work Email *")
        lead_company = st.text_input("Company Name / Phone Number")
        lead_message = st.text_area("How can we help you? (Project details, budget, timeline) *")
        submitted = st.form_submit_button("Submit Inquiry", type="primary")

    if submitted:
        if not lead_name or not lead_email or not lead_message:
            st.warning("Please fill in your Name, Email, and Message.")
        elif not gemini_key:
            st.error("Setup incomplete: Owner must add a Gemini API key in the sidebar.")
        else:
            try:
                client = genai.Client(api_key=gemini_key)
                qualify_prompt = f"""
                A potential customer submitted an inquiry for {company_name} (Offer: {offer_desc}).
                Name: {lead_name}
                Email: {lead_email}
                Company/Phone: {lead_company}
                Message: {lead_message}

                Return a JSON object with:
                - "intent_score": Integer 1-10 (10 = ready to buy now)
            
