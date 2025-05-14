import os
import time
import requests
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup

# === CONFIG ===
load_dotenv()

SERPAPI_KEY    = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_KEY environment variable not set")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://zak-beta.vercel.app"}})

# === Helper Functions ===
def is_valid_text(text):
    return text and len(text.strip()) > 0 and not text.strip().startswith("By ")

def get_links_from_serpapi(query, api_key, max_results=5):
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": max_results,
        "gl": "IN",
        "hl": "en",
        "location": "India",
    }
    try:
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        org = data.get("organic_results", [])
        return [r.get("link") for r in org[:max_results] if r.get("link")]
    except Exception:
        return []

def scrape_links(links, timeout=10):
    extracted = ""
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in links:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # extract headings & paragraphs
        for tag in soup.select("h1, h2, h3, p"):
            text = tag.get_text(strip=True)
            if is_valid_text(text):
                extracted += text + "\n"

        # extract anchors as markdown links
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True) or a["href"]
            href = a["href"]
            if href.startswith("http"):
                extracted += f"[{text}]({href})\n"

        # extract table rows
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                texts = [cell.get_text(strip=True) for cell in cells]
                if any(texts):
                    # join cell texts with tabs
                    extracted += "\t".join(texts) + "\n"

    return extracted


def query_gemini(user_question, scraped_text, api_key):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={api_key}"
    )
    headers = {"Content-Type": "application/json"}
    prompt = (
        "You are an AI assistant. Use only the data provided below.\n\n"
        "=== Source URLs ===\n"
        + "\n".join(f"- {u}" for u in get_links_from_serpapi(user_question, SERPAPI_KEY)) +
        "\n\n=== Scraped Content ===\n"
        f"{scraped_text}\n\n"
        f"User's question: {user_question}\n"
        "- If the user asked for links, answer with those URLs (as Markdown links).\n"
        "- Otherwise, answer using only the scraped content.\n"
        "- Be concise and precise.\n"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"Error querying Gemini: {e}"

# === API Route ===
@app.route('/api/realtime', methods=['POST'])
def handle_query():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify(error="Missing 'question'"), 400

    links = get_links_from_serpapi(question, SERPAPI_KEY)
    if not links:
        return jsonify(answer="❌ No search results found.")

    scraped = scrape_links(links)
    if not scraped.strip():
        return jsonify(answer="❌ No content could be extracted from links.")

    answer = query_gemini(question, scraped, GEMINI_API_KEY)
    return jsonify(answer=answer)

# === MAIN ===
if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))

    
    
    
#prompt = (
 #       "You are an AI assistant helping the user answer a question using only the provided web data and If no data found answer the question with your intelligence.\n"
 #       "=== Scraped Web Content Start ===\n"
 #       f"{scraped_text}\n"
 #       "=== Scraped Web Content End ===\n\n"
 #       f"User's question: {user_question}\n"
 #       "- Only answer using the content above.\n"
 #       "- Be short, clear, and precise.\n"
 #       "- Also don't give references to the scrapped text given above\n"
 #       "- If no data found answer the question with your intelligence.\n"
 #       " If the user asked for links, answer with those URLs (as clickable Markdown links).\n"
#
 #   )