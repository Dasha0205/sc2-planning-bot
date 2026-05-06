import json
import os
import subprocess
import sys
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

_bot_process = None


def _bot_running():
    global _bot_process
    if _bot_process is None:
        return False
    return _bot_process.poll() is None  # None = still running


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run_bot():
    global _bot_process
    if _bot_running():
        return jsonify({"error": "Bot is already running"}), 409

    data = request.get_json(silent=True) or {}
    goal = data.get("goal", "rush")
    planner = data.get("planner", "fast-downward")

    # Clear old metrics so the UI starts fresh
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "metrics.json")
    if os.path.exists(metrics_path):
        os.remove(metrics_path)

    _bot_process = subprocess.Popen(
        [sys.executable, "run.py", goal, planner],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    return jsonify({"status": "started", "goal": goal, "planner": planner})


@app.route("/status")
def status():
    running = _bot_running()
    result = None
    if _bot_process is not None and not running:
        result = "victory" if _bot_process.returncode == 0 else "defeat"
    return jsonify({"running": running, "result": result})


@app.route("/metrics")
def metrics():
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "metrics.json")
    if not os.path.exists(metrics_path):
        return jsonify({"events": [], "snapshots": []})
    with open(metrics_path) as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    app.run(debug=True, port=5000)