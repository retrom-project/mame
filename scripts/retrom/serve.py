#!/usr/bin/env python3
"""Local-only PoC server, with immutable compressed WASM and request evidence."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit


def serve(root, port):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
            if name == "__requests":
                data = json.dumps(requests).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
            else:
                path = (root / name).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    self.send_error(404)
                    return
                encoding = None
                accepted = self.headers.get("Accept-Encoding", "")
                for candidate in ("br", "gzip"):
                    compressed = Path(str(path) + (".br" if candidate == "br" else ".gz"))
                    if candidate in accepted and compressed.is_file():
                        path, encoding = compressed, candidate
                        break
                data = path.read_bytes()
                self.send_response(200)
                kind = "application/wasm" if name.endswith(".wasm") else mimetypes.guess_type(name)[0]
                self.send_header("Content-Type", kind or "application/octet-stream")
                self.send_header("Vary", "Accept-Encoding")
                self.send_header("Cache-Control", "public,max-age=31536000,immutable" if name.endswith((".wasm", ".mjs")) and len(name.split(".")) > 2 else "no-store")
                if encoding:
                    self.send_header("Content-Encoding", encoding)
                requests.append({"path": name, "encoding": encoding, "transferredBytes": len(data)})
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    print(f"PoC: http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=4785)
    args = parser.parse_args()
    serve(args.root.resolve(), args.port)
