from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Flask Todo v2</h1><p>Updated and redeployed!</p><a href='/health'>Health</a>"

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "runtime": "python/flask", "version": "2"})
