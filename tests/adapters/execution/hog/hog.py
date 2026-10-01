"""A unit that answers health and, on GET /v1/hog, takes far more memory than its limit."""

import http.server
import os
import socketserver


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/v1/hog":
            self.send_response(200)
            self.end_headers()
            hog = bytearray(512 * 1024 * 1024)
            self.wfile.write(str(len(hog)).encode())
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ready"}')


port = int(os.environ.get("TAKTUS_UNIT_PORT", "9000"))
socketserver.ThreadingTCPServer.allow_reuse_address = True
# Every interface of its own container: the adapter reaches it from outside.
socketserver.ThreadingTCPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104
