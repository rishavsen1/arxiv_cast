import collections
import importlib.util
import json
import os
import psutil
import requests
import glob
from flask import Flask, render_template, jsonify, request, Response

app = Flask(__name__)
INTEL_STACK_DIR = os.path.join(os.path.dirname(__file__), "intel-stack")

# Load arxiv_intel from intel-stack (optional; fails only when calling podcast without OPENROUTER_KEY)
def _arxiv_intel():
    path = os.path.join(os.path.dirname(__file__), "intel-stack", "arxiv_intel.py")
    spec = importlib.util.spec_from_file_location("arxiv_intel", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Buffer for the live telemetry chart (last 10 mins)
history = collections.deque(maxlen=300) 

def get_stats():
    # Get Thermal Data
    temp = os.popen("vcgencmd measure_temp").readline()
    temp_val = float(temp.replace("temp=","").replace("'C\n",""))
    
    # Get Pi-hole Stats (Ads Blocked)
    ads_blocked = 0
    try:
        r = requests.get("http://localhost:8000/api/summary", timeout=0.5)
        ads_blocked = r.json().get('queries_blocked', 0)
    except:
        ads_blocked = "OFFLINE"

    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent,
        "temp": temp_val,
        "ads_blocked": ads_blocked
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/intel')
def intel():
    return render_template('intel.html')

@app.route('/api/stats')
def stats():
    current = get_stats()
    history.append(current)
    return jsonify({"current": current, "history": list(history)})

@app.route('/api/archive')
def get_archive():
    files = glob.glob('/home/rishav/weblogger/static/archive/*.mp3')
    filenames = [os.path.basename(f) for f in files]
    filenames.sort(reverse=True)
    return jsonify(filenames)

# ArxivCast: serve generated matrix HTML from intel-stack (on-demand)
@app.route('/api/arxiv/matrix-html')
def arxiv_matrix_html():
    path = os.path.join(INTEL_STACK_DIR, "arxiv_intel.html")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response(
        '<p class="text-slate-500 text-sm p-6">No data yet. Choose categories and date, then click <strong>Search &amp; Populate</strong> to fetch papers.</p>',
        mimetype="text/html; charset=utf-8"
    )

# ArxivCast: serve generated synopsis HTML from intel-stack (on-demand)
@app.route('/api/arxiv/synopsis-html')
def arxiv_synopsis_html():
    path = os.path.join(INTEL_STACK_DIR, "arxiv_synopsis.html")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response(
        '<p class="text-slate-500 text-sm">No transcript yet. Generate a podcast from the options above.</p>',
        mimetype="text/html; charset=utf-8"
    )

# ArxivCast: fetch papers and regenerate matrix
@app.route('/api/arxiv/fetch', methods=['POST'])
def arxiv_fetch():
    data = request.get_json(force=True, silent=True) or {}
    categories = data.get("categories")
    papers_per_tag = data.get("papers_per_tag")
    limit = data.get("limit", 120)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    # Explicit date in payload = use that day; missing/null = use latest (no date filter)
    date = data.get("date")
    if date is not None and date != "":
        if date > today:
            return jsonify({"ok": False, "error": "Date cannot be in the future. Choose today or earlier."}), 400
    else:
        date = None
    if categories is not None and not isinstance(categories, list):
        categories = [c.strip() for c in str(categories).split(",") if c.strip()]
    try:
        mod = _arxiv_intel()
        mod.init_db()
        result = mod.fetch_and_store(categories=categories, papers_per_tag=papers_per_tag, date=date)
        mod.generate_html(limit=limit, date=date)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ArxivCast: generate podcast with style and length
@app.route('/api/arxiv/podcast', methods=['POST'])
def arxiv_podcast():
    data = request.get_json(force=True, silent=True) or {}
    style = data.get("style", "easy")
    length = data.get("length", "medium")
    custom_style = data.get("custom_style") or None
    date = data.get("date")
    try:
        mod = _arxiv_intel()
        result = mod.generate_podcast_and_synopsis(style=style, length=length, custom_style=custom_style, date=date)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ArxivCast: list available categories for the UI
@app.route('/api/arxiv/categories')
def arxiv_categories():
    try:
        mod = _arxiv_intel()
        return jsonify({"categories": mod.CATEGORIES})
    except Exception:
        return jsonify({"categories": [
            "cs.LG", "cs.AI", "cs.SY", "cs.RO", "cs.NE", "cs.CE",
            "eess.SY", "eess.SP", "math.OC", "stat.ML", "econ.EM", "physics.soc-ph"
        ]})

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    app.run(host='0.0.0.0', port=5000)