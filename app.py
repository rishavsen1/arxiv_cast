import collections
import glob
import os
import psutil
import requests
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# ArxivCast is a separate module; dashboard only links to it at /intel
from arxvicast import arxvicast_bp

app.register_blueprint(arxvicast_bp)

# Buffer for the live telemetry chart (last 10 mins)
history = collections.deque(maxlen=300)


def get_stats():
    # Get Thermal Data
    temp = os.popen("vcgencmd measure_temp").readline()
    temp_val = float(temp.replace("temp=", "").replace("'C\n", ""))

    # Get Pi-hole Stats (Ads Blocked)
    ads_blocked = 0
    try:
        r = requests.get("http://localhost:8000/api/summary", timeout=0.5)
        ads_blocked = r.json().get("queries_blocked", 0)
    except Exception:
        ads_blocked = "OFFLINE"

    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent,
        "temp": temp_val,
        "ads_blocked": ads_blocked,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    current = get_stats()
    history.append(current)
    return jsonify({"current": current, "history": list(history)})


@app.route("/api/archive")
def get_archive():
    files = glob.glob("/home/rishav/weblogger/static/archive/*.mp3")
    filenames = [os.path.basename(f) for f in files]
    filenames.sort(reverse=True)
    return jsonify(filenames)


if __name__ == "__main__":
    if not os.path.exists("templates"):
        os.makedirs("templates")
    app.run(host="0.0.0.0", port=5000)
