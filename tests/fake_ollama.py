"""Stand-in for Ollama, for testing the setup without a real model.

It speaks just enough of the Ollama HTTP API for Open WebUI to index documents
and run a chat. Embeddings are a hashed bag of words, so retrieval finds chunks
that share words with the question. Chat replies repeat back the prompt the
"model" received, so a test can check that retrieved document text reached it.

It is a test double only: it never produces a real answer.
"""

import hashlib
import json
import math
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EMBEDDING_DIMENSIONS = 256
REQUEST_LOG = []


def embed(text):
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.md5(word.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS] += 1.0
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / length for value in vector]


def model_entry(name):
    return {
        "name": name,
        "model": name,
        "modified_at": "2026-01-01T00:00:00Z",
        "size": 1,
        "digest": hashlib.sha256(name.encode()).hexdigest(),
        "details": {"family": "fake", "parameter_size": "1B", "quantization_level": "Q4"},
    }


def echo_reply(body):
    """Repeat the prompt back so tests can see what reached the model."""
    parts = []
    for message in body.get("messages", []):
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        parts.append(f"[{message.get('role')}] {content}")
    return "ECHO " + " ".join(parts)


class Handler(BaseHTTPRequestHandler):
    models = []

    def log_message(self, *args):
        return

    def send_json(self, payload, status=200):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        REQUEST_LOG.append({"method": "GET", "path": self.path})
        if self.path == "/__requests":
            return self.send_json(REQUEST_LOG)
        if self.path in ("/", "/api/version"):
            return self.send_json({"version": "0.0.0-fake"})
        if self.path == "/api/tags":
            return self.send_json({"models": [model_entry(name) for name in self.models]})
        if self.path == "/api/ps":
            return self.send_json({"models": []})
        return self.send_json({"error": f"fake ollama: no GET {self.path}"}, 404)

    def do_POST(self):
        body = self.read_body()
        REQUEST_LOG.append({"method": "POST", "path": self.path, "body": body})
        if self.path == "/api/show":
            return self.send_json({"details": {"family": "fake"}, "capabilities": ["completion", "tools"], "model_info": {}})
        if self.path == "/api/embed":
            inputs = body.get("input", [])
            inputs = [inputs] if isinstance(inputs, str) else inputs
            return self.send_json({"model": body.get("model"), "embeddings": [embed(text) for text in inputs]})
        if self.path == "/api/embeddings":
            return self.send_json({"embedding": embed(body.get("prompt", ""))})
        if self.path == "/api/chat":
            return self.chat(body)
        return self.send_json({"error": f"fake ollama: no POST {self.path}"}, 404)

    def chat(self, body):
        reply = {
            "model": body.get("model"),
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": echo_reply(body)},
            "done": True,
            "done_reason": "stop",
        }
        if body.get("stream", True):
            data = (json.dumps(reply) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_json(reply)


if __name__ == "__main__":
    port = int(sys.argv[1])
    Handler.models = sys.argv[2:]
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
