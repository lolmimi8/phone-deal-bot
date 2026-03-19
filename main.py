import subprocess
import sys
import time

while True:
    print("Uruchamiam bota...", flush=True)
    ret = subprocess.run([sys.executable, "bot.py"])
    print(f"Bot zakonczyl sie (kod: {ret.returncode}). Restart za 5s...", flush=True)
    time.sleep(5)
