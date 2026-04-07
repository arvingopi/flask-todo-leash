"""
Leash MCP Gmail Chat — Flask app that connects to the Leash Gmail MCP server
and provides a chat interface powered by Claude to interact with your emails.
"""

import os
import json
import httpx
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

PLATFORM_URL = os.environ.get("LEASH_PLATFORM_URL", "https://leash.build")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MCP_GMAIL_URL = f"{PLATFORM_URL}/mcp/gmail"


def get_leash_user(cookies):
    """Decode leash-auth JWT from cookie (no verification — trusted platform cookie)."""
    token = cookies.get("leash-auth")
    if not token:
        return None
    import base64
    try:
        payload = token.split(".")[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return {"name": data.get("name"), "email": data.get("email")}
    except Exception:
        return None


def call_mcp_tool(tool_name, arguments, leash_auth_token):
    """Call a tool on the Leash Gmail MCP server."""
    # MCP Streamable HTTP: send a JSON-RPC request
    rpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    resp = httpx.post(
        MCP_GMAIL_URL,
        json=rpc_request,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"leash-auth={leash_auth_token}",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        return {"error": f"MCP server returned {resp.status_code}: {resp.text}"}

    result = resp.json()
    if "error" in result:
        return {"error": result["error"]}

    # Extract text content from MCP response
    content = result.get("result", {}).get("content", [])
    for item in content:
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                return {"text": item["text"]}

    return {"text": str(content)}


def list_mcp_tools(leash_auth_token):
    """List available tools from the MCP server."""
    rpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }

    resp = httpx.post(
        MCP_GMAIL_URL,
        json=rpc_request,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"leash-auth={leash_auth_token}",
        },
        timeout=15,
    )

    if resp.status_code != 200:
        return []

    result = resp.json()
    return result.get("result", {}).get("tools", [])


def chat_with_claude(user_message, leash_auth_token):
    """
    Send user message to Claude with MCP Gmail tools available.
    Claude decides which tools to call, we execute them, and return the final response.
    """
    if not ANTHROPIC_API_KEY:
        return "ANTHROPIC_API_KEY not configured on this app."

    # Get available MCP tools
    mcp_tools = list_mcp_tools(leash_auth_token)

    # Convert MCP tools to Claude tool format
    claude_tools = []
    for tool in mcp_tools:
        claude_tools.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
        })

    messages = [{"role": "user", "content": user_message}]

    # Call Claude
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": "You are a helpful email assistant. Use the Gmail tools to help the user with their emails. Be concise.",
            "tools": claude_tools,
            "messages": messages,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        return f"Claude API error: {resp.status_code} {resp.text}"

    response = resp.json()

    # Process tool use blocks
    result_text = ""
    tool_results = []

    for block in response.get("content", []):
        if block["type"] == "text":
            result_text += block["text"]
        elif block["type"] == "tool_use":
            # Execute the MCP tool
            tool_result = call_mcp_tool(block["name"], block["input"], leash_auth_token)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(tool_result),
            })

    # If there were tool calls, send results back to Claude for final answer
    if tool_results and response.get("stop_reason") == "tool_use":
        messages.append({"role": "assistant", "content": response["content"]})
        messages.append({"role": "user", "content": tool_results})

        resp2 = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": "You are a helpful email assistant. Summarize results concisely.",
                "tools": claude_tools,
                "messages": messages,
            },
            timeout=30,
        )

        if resp2.status_code == 200:
            resp2_data = resp2.json()
            result_text = ""
            for block in resp2_data.get("content", []):
                if block["type"] == "text":
                    result_text += block["text"]

    return result_text or "No response from Claude."


@app.route("/")
def index():
    user = get_leash_user(request.cookies)
    if not user:
        return """
        <html><body style="font-family: system-ui; max-width: 600px; margin: 40px auto; padding: 0 20px;">
        <h1>Leash MCP Gmail Chat</h1>
        <p>Not authenticated. <a href="https://leash.build/login">Log in to Leash</a> first.</p>
        </body></html>
        """

    return f"""
    <html>
    <head><title>Gmail Chat</title></head>
    <body style="font-family: system-ui; max-width: 700px; margin: 40px auto; padding: 0 20px;">
        <h1>Gmail Chat</h1>
        <p>Signed in as <strong>{user['name']}</strong> ({user['email']})</p>
        <p style="color: #666; font-size: 14px;">Ask questions about your emails. Powered by Claude + Leash MCP.</p>

        <div id="chat" style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; min-height: 300px; max-height: 500px; overflow-y: auto; margin-bottom: 16px; background: #fafafa;">
            <p style="color: #999;">Try: "What are my latest emails?" or "Do I have anything from Georgia Tech?"</p>
        </div>

        <form onsubmit="sendMessage(event)" style="display: flex; gap: 8px;">
            <input id="input" type="text" placeholder="Ask about your emails..."
                   style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 16px;"
                   autocomplete="off" />
            <button type="submit" id="btn"
                    style="padding: 10px 20px; background: #4F46E5; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px;">
                Send
            </button>
        </form>

        <script>
        async function sendMessage(e) {{
            e.preventDefault();
            const input = document.getElementById('input');
            const chat = document.getElementById('chat');
            const btn = document.getElementById('btn');
            const msg = input.value.trim();
            if (!msg) return;

            // Show user message
            chat.innerHTML += '<div style="margin: 8px 0; padding: 8px 12px; background: #E8E8FF; border-radius: 8px;"><strong>You:</strong> ' + msg + '</div>';
            input.value = '';
            btn.disabled = true;
            btn.textContent = 'Thinking...';

            // Show loading
            const loadingId = 'loading-' + Date.now();
            chat.innerHTML += '<div id="' + loadingId + '" style="margin: 8px 0; color: #999;">Thinking...</div>';
            chat.scrollTop = chat.scrollHeight;

            try {{
                const res = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: msg}})
                }});
                const data = await res.json();
                document.getElementById(loadingId).remove();
                chat.innerHTML += '<div style="margin: 8px 0; padding: 8px 12px; background: #F0F0F0; border-radius: 8px;"><strong>Assistant:</strong> ' + (data.response || data.error || 'No response') + '</div>';
            }} catch(err) {{
                document.getElementById(loadingId).remove();
                chat.innerHTML += '<div style="margin: 8px 0; color: red;">Error: ' + err.message + '</div>';
            }}

            btn.disabled = false;
            btn.textContent = 'Send';
            chat.scrollTop = chat.scrollHeight;
        }}
        </script>
    </body>
    </html>
    """


@app.route("/chat", methods=["POST"])
def chat():
    leash_token = request.cookies.get("leash-auth")
    if not leash_token:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    response = chat_with_claude(message, leash_token)
    return jsonify({"response": response})


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "app": "leash-mcp-gmail-chat"})
