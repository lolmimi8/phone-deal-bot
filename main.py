from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

# Serwer HTTP startuje PIERWSZY w głównym wątku tymczasowo
server = HTTPServer(("0.0.0.0", 8080), PingHandler)
print("[HTTP] Serwer nasluchuje na porcie 8080", flush=True)

# Bot startuje w osobnym wątku PO uruchomieniu serwera
def start_bot():
    from bot import main
    main()

bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

# Serwer blokuje główny wątek – działa cały czas
server.serve_forever()
