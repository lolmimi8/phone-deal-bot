from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"PhoneDealBot is alive!")
    def log_message(self, *args):
        pass

def keep_alive():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("[KeepAlive] Serwer HTTP nasluchuje na :8080")
