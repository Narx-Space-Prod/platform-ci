"""HTTP dependency fixture for component tests; no real payment provider or AWS."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRODUCT = {
    "id": "ci-book",
    "name": "CI book",
    "price": 12900,
    "currency": "INR",
    "emoji": "B",
    "stock": 5,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/products", "/catalogue/products"):
            body = [PRODUCT]
        elif self.path == "/products/ci-book":
            body = PRODUCT
        elif self.path.startswith("/carts/"):
            body = {"items": []}
        elif self.path == "/health/ready":
            body = {"status": "ok"}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
