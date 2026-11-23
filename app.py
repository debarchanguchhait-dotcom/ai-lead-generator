import json
import pandas as pd
import streamlit as st
from ddgs import DDGS
from google import genai
from google.genai import types

st.set_page_config(page_title="AI Lead Generation Agent", page_icon="🎯", layout="wide")

st.title("🎯 AI Lead Generation & Outreach Agent")
st.caption("100% Free Stack • Powered by Google Gemini & Live Web Search")

# --- SIDEBAR: Client Configuration ---
with st.sidebar:
    st.header("1. Client Setup")
    gemini_key = st.text_input(
        "Free Google Gemini API Key",
        type="password",
        help="Get a free key at ://google.com"
    )
    st.markdown("[Get a free Gemini API key →](https://://google.com)")
    
    st.divider()
    st.header("2. Offer & Tone")
    company_name = st.text_input("Your Company Name", placeholder="e.g., Acme Marketing")
    offer_desc = st.text_area(
        "What do you sell?",
        placeholder="e.g., We help B2B SaaS founders book 15+ sales calls/month using AI cold outreach."
    )
    num_leads = st.slider("Number of leads to find", min_value=3, max_value=15, value=5)

# --- MAIN AREA: Search & Run ---
target_audience = st.text_input(
    "Describe your Ideal Customer (ICP)",
    placeholder="e.g., Fintech startup founders in India or B2B marketing agencies in London"
)

if st.button("🚀 Find & Qualify Leads", type="primary"):
    if not gemini_key:
        st.error("Please paste your free Google Gemini API key in the left sidebar.")
    elif not target_audience or not offer_desc:
        st.warning("Please enter both your Ideal Customer and What You Sell.")
    else:
        try:
            client = genai.Client(api_key=gemini_key)
            
            # Step 1: Generate targeted search queries
            with st.status("Searching the web for prospects...", expanded=True) as status:
                st.write("🔍 Generating search queries...")
                query_prompt = f"""
                Generate 3 concise web search queries to find real companies, founders, or decision-makers matching this Ideal Customer Profile: '{target_audience}'.
                Focus on finding company websites, LinkedIn profiles, or business directories.
                Return ONLY a JSON list of 3 strings.
                """
                q_res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=query_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                queries = json.loads(q_res.text)
                
                # Step 2: Run free DuckDuckGo web search
                raw_results = []
                with DDGS() as ddgs:
                    for q in queries:
                        st.write(f"🌐 Searching: `{q}`")
                        results = list(ddgs.text(q, max_results=num_leads))
                        raw_results.extend(results)
                
                if not raw_results:
                    st.error("No results found. Try broadening your target audience description.")
                    st.stop()
                
                # Step 3: Extract, Score & Write Personalized Outreach
                st.write("🧠 Analyzing leads, scoring ICP fit, and drafting emails...")
                extract_prompt = f"""
                You are an expert B2B Lead Generation AI.
                Analyze these web search results and extract up to {num_leads} distinct, real companies or decision-makers that match: '{target_audience}'.
                
                Search Results:
                {json.dumps(raw_results[:25])}
                
                Our Company: {company_name}
                Our Offer: {offer_desc}
                
                Return a JSON array of objects, where each object has:
                - "lead_name": Person or Company Name
                - "role_or_industry": Their role or business niche
                - "website_or_link": URL from the search result
                - "fit_score": Integer from 1 to 10 based on how well they match '{target_audience}'
                - "fit_reason": 1 short sentence explaining why they are a good lead
                - "personalized_email": A short, high-converting 3-sentence cold email tailored to their business
                """
                
                leads_res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=extract_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                leads_data = json.loads(leads_res.text)
                status.update(label="✅ Leads generated successfully!", state="complete", expanded=False)

            # Display & Export Results
            df = pd.DataFrame(leads_data)
            st.subheader(f"Found {len(df)} Qualified Leads")
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Leads as CSV",
                data=csv,
                file_name="qualified_leads.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"Error: {e}")
