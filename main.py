from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from bot import main

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

# Bot działa w osobnym wątku
bot_thread = threading.Thread(target=main, daemon=True)
bot_thread.start()

# Serwer HTTP działa w głównym wątku (wymagane przez Back4app)
server = HTTPServer(("0.0.0.0", 8080), PingHandler)
print("[HTTP] Serwer nasluchuje na porcie 8080")
server.serve_forever()
