from keep_alive import keep_alive
from bot import main

if __name__ == "__main__":
    keep_alive()   # uruchamia serwer HTTP w tle (wymagany przez Render)
    main()         # uruchamia główną pętlę bota
