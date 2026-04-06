from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return """
    <html>
    <head><title>Flask Todo - un.leash'd</title>
    <style>body{font-family:system-ui;max-width:600px;margin:50px auto;padding:20px;}</style>
    </head>
    <body>
        <h1>Flask Todo App</h1>
        <p>Built with Claude Code. Deployed with Leash.</p>
        <p><a href="/api/todos">View API</a> | <a href="/health">Health</a></p>
    </body>
    </html>
    """

@app.route("/api/todos")
def get_todos():
    return jsonify([
        {"id": 1, "title": "Build with Claude", "done": True},
        {"id": 2, "title": "Deploy with Leash", "done": True},
    ])

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "runtime": "python/flask"})
