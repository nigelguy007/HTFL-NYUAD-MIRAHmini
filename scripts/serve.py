"""Starts the chat software with the side routes to the model closed.

The chat software offers several ways to reach the model that skip MIRAH's
consent gate, its instructions and its libraries: a pass-through to Ollama and
a few helper endpoints. Nothing in MIRAH uses them, so they are refused for
everyone. Run by ./privatellm start, with the chat software's own Python.
"""

from __future__ import annotations

import json
import os
import re
import sys

os.environ["FROM_INIT_PY"] = "true"  # what `open-webui serve` sets, so it finds its bundled website

import uvicorn  # noqa: E402
from open_webui.env import UVICORN_WS_PER_MESSAGE_DEFLATE  # noqa: E402
from open_webui.main import app  # noqa: E402

SIDE_ROUTES = re.compile(
    r"^/(?:"
    r"ollama/(?:api/(?:chat|generate|embed|embeddings)|v1/(?:chat/completions|completions|embeddings|messages|responses))(?:/\d+)?"
    r"|openai/(?:chat/completions|responses)"
    r"|api/v1/tasks/\w+/completions"
    r")/?$"
)
REFUSAL = json.dumps({"detail": "This route is switched off. Ask MIRAH in the chat instead."}).encode()


class CloseSideRoutes:
    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and SIDE_ROUTES.match(scope["path"]):
            headers = [(b"content-type", b"application/json"), (b"content-length", str(len(REFUSAL)).encode())]
            await send({"type": "http.response.start", "status": 403, "headers": headers})
            await send({"type": "http.response.body", "body": REFUSAL})
            return
        await self.inner(scope, receive, send)


if __name__ == "__main__":
    app.add_middleware(CloseSideRoutes)
    uvicorn.run(
        app,
        host=sys.argv[1],
        port=int(sys.argv[2]),
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "*"),
        ws_per_message_deflate=UVICORN_WS_PER_MESSAGE_DEFLATE,
    )
