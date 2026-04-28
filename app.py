from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "name": "MR1 BOT LIVE"
    })

@app.route("/api/test")
def test():
    return jsonify({
        "success": True
    })
