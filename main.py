import os, logging, requests, json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", 8080))
logging.basicConfig(level=logging.INFO)

SYSTEM = "Eres JARVIS, asistente privado de inversion de Miki. Cartera 34145 euros +22.03%. Nike -42.63% CRITICO. Microsoft -12.48%. Habla en espanol, directo, como analista senior. Da siempre senal: COMPRAR/MANTENER/VIGILAR/VENDER."

history = {}

def ask_groq(uid, text):
    if uid not in history:
        history[uid] = []
    history[uid].append({"role":"user","content":text})
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
        json={"model":"llama-3.3-70b-versatile","messages":[{"role":"system","content":SYSTEM}]+history[uid][-20:]})
    reply = r.json()["choices"][0]["message"]["content"]
    history[uid].append({"role":"assistant","content":reply})
    return reply

def send_telegram(chat_id, text):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id":chat_id,"text":text[:4000]})

def poll_telegram():
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset":offset,"timeout":30},timeout=35)
            for update in r.json().get("result",[]):
                offset = update["update_id"] + 1
                msg = update.get("message",{})
                chat_id = msg.get("chat",{}).get("id")
                text = msg.get("text","")
                if chat_id and text:
                    if text == "/start":
                        send_telegram(chat_id,"JARVIS activo. Cartera 34.145 euros +22.03%. Nike -42.63% requiere atencion urgente. Preguntame lo que quieras.")
                    else:
                        reply = ask_groq(chat_id, text)
                        send_telegram(chat_id, reply)
        except Exception as e:
            logging.error(e)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS activo")

threading.Thread(target=poll_telegram, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
