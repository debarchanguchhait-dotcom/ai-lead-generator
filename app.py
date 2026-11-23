import json
import urllib.parse
import requests
import pandas as pd
import streamlit as st
from ddgs import DDGS
from google import genai
from google.genai import types

st.set_page_config(page_title="AI Lead Gen & Alert Agent", page_icon="🎯", layout="wide")
st.title("🎯 AI Lead Generation & Interest Alert Agent")
st.caption("100% Free Stack • Outbound Prospecting + Instant Inbound Alerts")

with st.sidebar:
    st.header("1. AI Setup (Required)")
    gemini_key = st.text_input("Free Google Gemini API Key", type="password")
    st.markdown("[Get a free Gemini API key →](https://google.com)")
    st.divider()
    st.header("2. Business & Booking Info")
    company_name = st.text_input("Business Name", placeholder="e.g., Acme Solutions")
    offer_desc = st.text_area("What do you sell?", placeholder="e.g., AI lead generation systems")
    booking_link = st.text_input("Calendar Link (Optional)", placeholder="https://cal.com")
    st.divider()
    st.header("3. Instant Owner Alerts (Free)")
    alert_email = st.text_input("Owner Notification Email", placeholder="you@yourdomain.com")
    tg_bot_token = st.text_input("Telegram Bot Token (Optional)", type="password")
    tg_chat_id = st.text_input("Telegram Chat ID (Optional)", placeholder="123456789")


def send_owner_alert(lead):
    channels = []
    msg = (
        f"🔥 HOT LEAD ({lead.get('intent_score', 'N/A')}/10)\n"
        f"Name: {lead.get('name')}\nEmail: {lead.get('email')}\n"
        f"Company/Phone: {lead.get('company')}\nNeed: {lead.get('message')}"
    )
    if tg_bot_token and tg_chat_id:
        try:
            requests.post(
                f"https://telegram.org{tg_bot_token}/sendMessage",
                json={"chat_id": tg_chat_id, "text": msg},
                timeout=10
            )
            channels.append("Telegram")
        except Exception:
            pass
    if alert_email:
        try:
            requests.post(
                f"https://formsubmit.co{alert_email}",
                json={"_subject": f"🔥 Hot Lead: {lead.get('name')}", **lead},
                headers={"Accept": "application/json"},
                timeout=10
            )
            channels.append("Email")
        except Exception:
            pass
    return channels


tab1, tab2 = st.tabs(["🚀 Outbound Lead Finder", "📩 Inbound Interest Capture"])

with tab1:
    st.subheader("Find Prospects & Send 1-Click Outreach")
    col1, col2 = st.columns(2)
    with col1:
        target_audience = st.text_input("Describe your Ideal Customer", placeholder="e.g., Real estate agencies in Kolkata")
    with col2:
        num_leads = st.number_input("Leads to find", min_value=3, max_value=15, value=5)

    if st.button("🔍 Find & Qualify Leads", type="primary"):
        if not gemini_key:
            st.error("Open the sidebar (>> top-left) and paste your free Gemini API key first.")
        elif not target_audience or not offer_desc:
            st.warning("Enter your Ideal Customer above and 'What do you sell?' in the sidebar.")
        else:
            try:
                client = genai.Client(api_key=gemini_key)
                with st.status("Searching & qualifying leads...", expanded=True) as status:
                    q_res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"Generate 3 web search queries to find businesses matching '{target_audience}'. Return ONLY a JSON list of 3 strings.",
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    raw_results = []
                    with DDGS() as ddgs:
                        for q in json.loads(q_res.text):
                            st.write(f"🌐 Searching: `{q}`")
                            raw_results.extend(list(ddgs.text(q, max_results=int(num_leads))))

                    if not raw_results:
                        st.error("No results found. Try a broader description.")
                        st.stop()

                    cta = f"End by inviting them to book a call: {booking_link}" if booking_link else "End by asking for a quick 10-min chat."
                    prompt = (
                        f"Extract up to {int(num_leads)} real businesses matching '{target_audience}' from: {json.dumps(raw_results[:20])}. "
                        f"Sender: {company_name}, Offer: {offer_desc}. "
                        f"Return JSON array with keys: lead_name, contact_email, website, fit_score (1-10), fit_reason, email_subject, email_body (3 sentences. {cta})."
                    )
                    leads_res = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    leads_data = json.loads(leads_res.text)
                    status.update(label="✅ Leads ready!", state="complete", expanded=False)

                df = pd.DataFrame(leads_data)
                st.dataframe(df[["lead_name", "contact_email", "website", "fit_score", "fit_reason"]], use_container_width=True)

                for idx, lead in enumerate(leads_data):
                    with st.expander(f"⭐ {lead['fit_score']}/10 — {lead['lead_name']}"):
                        st.write(f"**Why they fit:** {lead['fit_reason']}")
                        st.text_input("Subject", value=lead["email_subject"], key=f"s_{idx}")
                        st.text_area("Email", value=lead["email_body"], height=100, key=f"b_{idx}")
                        to_e = urllib.parse.quote(lead.get("contact_email", ""))
                        sub_e = urllib.parse.quote(lead["email_subject"])
                        bod_e = urllib.parse.quote(lead["email_body"])
                        st.link_button("✉️ Open & Send in Gmail", f"https://google.com{to_e}&su={sub_e}&body={bod_e}")

                st.download_button("📥 Download CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="leads.csv", mime="text/csv")
            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    st.subheader(f"Contact {company_name or 'Us'}")
    with st.form("inbound_form"):
        name = st.text_input("Your Name *")
        email = st.text_input("Work Email *")
        company = st.text_input("Company / Phone")
        message = st.text_area("How can we help you? *")
        submitted = st.form_submit_button("Submit Inquiry", type="primary")

    if submitted:
        if not name or not email or not message:
            st.warning("Please fill in Name, Email, and Message.")
        elif not gemini_key:
            st.error("Owner must add a Gemini API key in the sidebar first.")
        else:
            try:
                client = genai.Client(api_key=gemini_key)
                q_prompt = (
                    f"Qualify this lead for {company_name} ({offer_desc}): Name={name}, Email={email}, Company={company}, Msg={message}. "
                    f"Return JSON with keys: intent_score (1-10), suggested_reply (warm 3-sentence reply)."
                )
                res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=q_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                data = json.loads(res.text)
                channels = send_owner_alert({"name": name, "email": email, "company": company, "message": message, **data})
                st.success("✅ Inquiry received!")
                st.info(data["suggested_reply"])
                if booking_link:
                    st.link_button("📅 Book a Call Directly", booking_link)
                if channels:
                    st.caption(f"🔔 Owner alerted via: {', '.join(channels)}")
            except Exception as e:
                st.error(f"Error: {e}")
        
