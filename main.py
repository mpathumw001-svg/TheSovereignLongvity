import os
import requests
import psycopg2
import json

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_pubmed_abstract():
    # Fetch 1 latest PubMed paper on Longevity / Neuroscience
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=longevity+OR+neuroscience+OR+circadian+rhythm&retmode=json&retmax=1"
    res = requests.get(search_url).json()
    id_list = res.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return None, None
    
    pmid = id_list[0]
    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
    sum_res = requests.get(summary_url).json()
    title = sum_res.get("result", {}).get(pmid, {}).get("title", "No Title")
    return pmid, title

def analyze_with_gemini(pmid, title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    You are an expert Medical Synthesizer for SovereignLab.
    Analyze this research paper:
    Title: {title}
    PMID: {pmid}

    Provide a JSON output with strictly these keys:
    {{
      "core_insight": "2 sentences on biological mechanism from first principles.",
      "practical_protocol": "1 actionable daily protocol.",
      "youtube_short_script": "Hook (1.5s), Biological Mechanism, Actionable Protocol, CTA to SovereignLab.",
      "target_biomarker": "Primary biomarker or system"
    }}
    Return only valid JSON. Do not add markdown formatting or extra prose.
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    res_data = response.json()
    
    try:
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Clean markdown codeblocks if present
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
        return json.loads(raw_text)
    except Exception as e:
        print("Error parsing Gemini response:", e)
        return None

def save_to_neon(pmid, title, data):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    query = """
    INSERT INTO research_vault (pubmed_id, title, core_scientific_insight, practical_human_protocol, youtube_short_script, target_biomarker)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (pubmed_id) DO NOTHING;
    """
    cursor.execute(query, (
        pmid, title, 
        data.get("core_insight"), 
        data.get("practical_protocol"), 
        data.get("youtube_short_script"), 
        data.get("target_biomarker")
    ))
    conn.commit()
    cursor.close()
    conn.close()

def send_telegram_msg(pmid, title, data):
    message = f"""
🧠 *SovereignLab Daily Research Alert*

📌 *Title:* {title}
🔬 *Biomarker:* {data.get('target_biomarker')}

💡 *Core Insight:*
{data.get('core_insight')}

⚡ *Actionable Protocol:*
{data.get('practical_protocol')}

🎬 *YouTube Short Script:*
{data.get('youtube_short_script')}
    """
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(tg_url, json=payload)

def main():
    pmid, title = fetch_pubmed_abstract()
    if not pmid:
        print("No paper found.")
        return
    
    data = analyze_with_gemini(pmid, title)
    if data:
        save_to_neon(pmid, title, data)
        send_telegram_msg(pmid, title, data)
        print("Success! Sent to Telegram and saved to Neon DB.")

if __name__ == "__main__":
    main()
