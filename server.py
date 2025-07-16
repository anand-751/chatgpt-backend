import os
import time
import requests
import json
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

# === CONFIG ===
load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_KEY environment variable not set")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set")

app = Flask(__name__)
CORS(app, origins=["https://anand-751.github.io/Ai-ChatBot/"])

# === Root route ===
@app.route('/')
def home():
    return "✅ Flask backend is working! Use POST /api/realtime"

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
        links = []
        org = data.get("organic_results")
        if not org:
            return []
        for result in org[:max_results]:
            link = result.get("link")
            if link:
                links.append(link)
        return links
    except Exception:
        return []

def scrape_links(links, load_timeout=5):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(load_timeout)

    extracted = ""
    for url in links:
        try:
            driver.get(url)
        except (TimeoutException, WebDriverException):
            continue
        time.sleep(3)

        try:
            elems = driver.find_elements("xpath", "//h1 | //h2 | //h3 | //p | //a")
            for el in elems:
                tag_name = el.tag_name.lower()
                text = el.text.strip()
                if tag_name == "a":
                    href = el.get_attribute("href")
                    if text and href:
                        extracted += f"[{text}]({href})\n"
                elif is_valid_text(text):
                    extracted += text + "\n"
        except Exception as e:
            print(f"[ERROR] Failed while extracting elements: {e}")

        try:
            tables = driver.find_elements("tag name", "table")
            for table in tables:
                rows = table.find_elements("tag name", "tr")
                for row in rows:
                    cells = row.find_elements("tag name", "th") + row.find_elements("tag name", "td")
                    texts = [cell.text.strip() for cell in cells]
                    if any(texts):
                        line = "\t".join(texts)
                        extracted += line + "\n"
        except Exception:
            pass

    driver.quit()
    return extracted

def query_gemini(user_question, scraped_text, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    prompt = (
        "You are an AI assistant helping the user answer a question using only the provided web data and If no data found answer the question with your intelligence.\n"
        "=== Scraped Web Content Start ===\n"
        f"{scraped_text}\n"
        "=== Scraped Web Content End ===\n\n"
        f"User's question: {user_question}\n"
        "- Only answer using the content above.\n"
        "- Be short, clear, and precise.\n"
        "- Also don't give references to the scrapped text given above\n"
        "- If no data found answer the question with your intelligence.\n"
        " If the user asked for links, answer with those URLs (as clickable Markdown links).\n"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload))
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            return f"Error from Gemini: {resp.status_code}"
    except Exception as e:
        return f"Error querying Gemini: {e}"

# === Main API Route ===
@app.route('/api/realtime', methods=['POST'])
def handle_query():
    data = request.get_json()
    question = data.get("question", "")

    if not question:
        return jsonify({"error": "Missing 'question' in request."}), 400

    links = get_links_from_serpapi(question, SERPAPI_KEY)
    if not links:
        return jsonify({"answer": "❌ No search results found."})

    scraped = scrape_links(links)
    if not scraped.strip():
        return jsonify({"answer": "❌ No content could be extracted from links."})

    response = query_gemini(question, scraped, GEMINI_API_KEY)
    return jsonify({"answer": response})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use PORT from environment if available
    app.run(debug=True, host='0.0.0.0', port=port)
