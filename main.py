import os, logging, requests, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_KEY     = os.environ.get("OPENAI_KEY")
TAVILY_KEY     = os.environ.get("TAVILY_KEY")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
PORT           = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)

SYSTEM = """Eres JARVIS, el asistente privado de inversion de Miguel (Miki).
Eres analista financiero senior, gestor de carteras y asesor value investor.

REGLA CRITICA: NUNCA inventes precios, PER, FCF ni ninguna metrica financiera.
Usa SOLO los datos que vienen en la busqueda web. Si no tienes el dato, dilo.

CARTERA REAL DE MIKI (34145 euros, +22.03%):
- Alphabet GOOGL: 6071 eur | +77.44% | 17.78%
- Fidelity SP500: 5118 eur | +24.10% | 14.99%
- iShares Europe: 4288 eur | +23.34% | 12.56%
- Vanguard SmallCap: 3900 eur | +24.48% | 11.42%
- Moncler MONC: 2596 eur | -3.79% | 7.60%
- J&J JNJ: 1883 eur | +61.36% | 5.51%
- Apple AAPL: 1793 eur | +20.61% | 5.25%
- Microsoft MSFT: 1522 eur | -12.48% | 4.46%
- SS&C SSNC: 1420 eur | +5.50% | 4.16%
- MSCI India: 1287 eur | -7.40% | 3.77%
- Vaneck RE TRET: 1265 eur | +6.88% | 3.70%
- Texas Roadhouse TXRH: 898 eur | -4.14% | 2.63%
- Invesco Gold 8PSG: 787 eur | +41.91% | 2.30%
- Zegona ZEG: 694 eur | +70.78% | 2.03%
- Nike NKE: 438 eur | -42.63% | 1.28% CRITICO
- Celsius CELH: 186 eur | +20.85% | 0.54%

Da siempre señal clara: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER
Habla en español, directo, como analista senior real."""

history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={"chat_id": str(chat_id), "role": role, "content": content[:2000], "created_at": datetime.utcnow().isoformat()},
            timeout=5
        )
    except Exception as e:
        logging.error(f"Supabase save: {e}")

def load_memory(chat_id, limit=10):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5
        )
        rows = r.json()
        if isinstance(rows, list):
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return []
    except:
        return []

def search_web(query):
    if not TAVILY_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": query, "max_results": 5},
            timeout=10
        )
        results = r.json().get("results", [])
        return "\n\n".join([f"FUENTE: {x['url']}\n{x['title']}: {x['content'][:400]}" for x in results[:4]])
    except:
        return ""

def ask_openai(chat_id, text):
    persistent = load_memory(chat_id, limit=10)
    if chat_id not in history:
        history[chat_id] = []

    web_data = search_web(text)
    full_text = f"{text}\n\nDATOS VERIFICADOS DE INTERNET:\n{web_data}" if web_data else f"{text}\n\nNOTA: No se encontraron datos web."

    history[chat_id].append({"role": "user", "content": full_text})
    all_messages = persistent[-6:] + history[chat_id][-8:]

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "system", "content": SYSTEM}] + all_messages, "temperature": 0.3},
        timeout=45
    )

    data = r.json()
    if "error" in data:
        return f"Error: {data['error'].get('message', 'desconocido')}"

    reply = data["choices"][0]["message"]["content"]
    history[chat_id].append({"role": "assistant", "content": reply})
    save_memory(chat_id, "user", text)
    save_memory(chat_id, "assistant", reply)
    return reply

def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10
    )

def handle_message(chat_id, text):
    cmd = text.strip().lower().split()[0] if text.startswith("/") else None

    if cmd == "/start":
        send_telegram(chat_id, "JARVIS V4 activo. GPT-4o + datos reales.\n\nCartera: 34.145 eur +22.03%\nCRITICO: Nike -42.63%\n\n/cartera /alertas /analiza TICKER /earnings /macro /memoria")
    elif cmd == "/cartera":
        send_telegram(chat_id, "CARTERA MIKI — 34.145 eur | +22.03%\n\nGOOGL +77.44% | 17.78%\nSP500 +24.10% | 14.99%\nEurope +23.34% | 12.56%\nSmallCap +24.48% | 11.42%\nMONC -3.79% | 7.60%\nJNJ +61.36% | 5.51%\nAAPL +20.61% | 5.25%\nMSFT -12.48% | 4.46%\nSSNC +5.50% | 4.16%\nIndia -7.40% | 3.77%\nTRET +6.88% | 3.70%\nTXRH -4.14% | 2.63%\nGold +41.91% | 2.30%\nZEG +70.78% | 2.03%\nNKE -42.63% | 1.28% CRITICO\nCELH +20.85% | 0.54%")
    elif cmd == "/alertas":
        send_telegram(chat_id, "ALERTAS:\n\nCRITICO: Nike NKE -42.63%\nVIGILAR: Microsoft MSFT -12.48%\nVIGILAR: Moncler MONC -3.79%\nVIGILAR: MSCI India -7.40%")
    elif cmd == "/analiza":
        parts = text.strip().split()
        if len(parts) < 2:
            send_telegram(chat_id, "Uso: /analiza TICKER\nEjemplo: /analiza NKE")
            return
        ticker = parts[1].upper()
        send_telegram(chat_id, f"Buscando datos reales de {ticker}...")
        reply = ask_openai(chat_id, f"Analiza {ticker} hoy con datos reales: precio actual, PER, FCF, ultimos resultados, insiders recientes, red flags. Solo datos verificados. Señal clara.")
        send_telegram(chat_id, reply)
    elif cmd == "/earnings":
        send_telegram(chat_id, "Buscando earnings...")
        reply = ask_openai(chat_id, "Fechas exactas de resultados proximos 60 dias: GOOGL, AAPL, MSFT, NKE, JNJ, TXRH, SSNC, CELH. Solo fechas verificadas.")
        send_telegram(chat_id, reply)
    elif cmd == "/macro":
        send_telegram(chat_id, "Analizando macro...")
        reply = ask_openai(chat_id, "Estado macro actual verificado: tipos FED, inflacion, dolar, VIX hoy. Como afecta a la cartera de Miki?")
        send_telegram(chat_id, reply)
    elif cmd == "/memoria":
        mem = load_memory(chat_id, limit=4)
        if mem:
            resumen = "\n\n".join([f"{m['role'].upper()}: {m['content'][:150]}..." for m in mem])
            send_telegram(chat_id, f"Memoria:\n\n{resumen}")
        else:
            send_telegram(chat_id, "Sin memoria guardada.")
    else:
        send_telegram(chat_id, "Buscando datos reales...")
        reply = ask_openai(chat_id, text)
        send_telegram(chat_id, reply)

def poll_telegram():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if chat_id and text:
                    handle_message(chat_id, text)
        except Exception as e:
            logging.error(f"Poll error: {e}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS V4 activo")
    def log_message(self, *args):
        pass

threading.Thread(target=poll_telegram, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
