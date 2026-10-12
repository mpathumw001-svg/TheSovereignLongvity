import os
import requests
import psycopg2
import json

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_pubmed_abstract():
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=neuroscience+OR+longevity+OR+autophagy+OR+circadian&sort=pub_date&retmode=json&retmax=5"
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
    # Updated to gemini-3.8-flash endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"You are Andrew Huberman for SovereignLab. Synthesize this paper: Title: {title}, PMID: {pmid}. CRITICAL: Keep exact scientific terms (e.g. Beta-Amyloid, Glymphatic System, BDNF, Autophagy, Microglia), but immediately explain them using a simple visual story or real-world analogy. Provide JSON output with strictly these keys: 'core_insight' (mechanism with exact terms explained via visual story), 'practical_protocol' (1 simple daily action step), 'youtube_short_script' (Hook, Story-driven Science with exact Scientific Terms, Protocol, CTA to SovereignLab), 'target_biomarker' (System/Biomarker name). Return ONLY valid JSON, no markdown codeblocks."
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    res_data = response.json()
    
    if "error" in res_data:
        print("Gemini API Error:", res_data["error"])
        return None

    try:
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        return json.loads(raw_text)
    except Exception as e:
        print("Error parsing Gemini response:", e)
        print("Raw Response was:", res_data)
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
    message = f"🧠 *The Sovereign Longevity - Story-Driven Science*\n\n📌 *Title:* {title}\n🔬 *System:* {data.get('target_biomarker')}\n\n💡 *Scientific Story:*\n{data.get('core_insight')}\n\n⚡ *Actionable Protocol:*\n{data.get('practical_protocol')}\n\n🎬 *YouTube Short Script:*\n{data.get('youtube_short_script')}"
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
    print(f"Fetched PubMed ID: {pmid}")
    data = analyze_with_gemini(pmid, title)
    if data:
        save_to_neon(pmid, title, data)
        send_telegram_msg(pmid, title, data)
        print("Success! Sent story-driven science to Telegram and saved to Neon DB.")
    else:
        print("Failed to generate data from Gemini.")

if __name__ == "__main__":
    main()
