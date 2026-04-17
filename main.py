import os, logging, requests, threading, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
 
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY       = os.environ.get("TAVILY_KEY")
SUPABASE_URL     = os.environ.get("SUPABASE_URL")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY")
PORT             = int(os.environ.get("PORT", 8080))
 
logging.basicConfig(level=logging.INFO)
 
SYSTEM = """Eres JARVIS, asistente privado de inversion de Miguel (Miki).
Eres analista financiero senior, gestor de carteras y asesor value investor.
 
REGLA ABSOLUTA: USA SOLO datos de la busqueda web. NUNCA inventes precios ni metricas.
Si el dato no esta verificado di exactamente: "No tengo ese dato verificado ahora mismo."
 
CARTERA REAL DE MIKI (actualizada):
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
- Visa V: 636.82 eur | nueva posicion
- Celsius CELH: 186 eur | +20.85% | 0.54%
- Nike NKE: VENDIDA
 
CUANDO ANALICES UNA EMPRESA:
- Usa SOLO datos verificados de la busqueda web
- Precio actual real, PER real, FCF real
- Ultimos resultados reales
- Insiders recientes
- Red flags detectadas
- Señal: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER
- Proyeccion 2025-2027 basada en datos reales
 
Habla en español, directo, como analista senior."""
 
history = {}
 
# ── SUPABASE ──────────────────────────────────────────────────────────────────
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
 
# ── BUSQUEDA WEB ──────────────────────────────────────────────────────────────
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
 
# ── CLAUDE API ────────────────────────────────────────────────────────────────
def ask_claude(chat_id, text):
    persistent = load_memory(chat_id, limit=8)
    if chat_id not in history:
        history[chat_id] = []
 
    web_data = search_web(text)
    full_text = f"{text}\n\nDATOS VERIFICADOS DE INTERNET:\n{web_data}" if web_data else text
 
    history[chat_id].append({"role": "user", "content": full_text})
    all_messages = persistent[-6:] + history[chat_id][-8:]
 
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "system": SYSTEM,
                "messages": all_messages
            },
            timeout=45
        )
 
        data = r.json()
 
        if "error" in data:
            logging.error(f"Claude error: {data['error']}")
            return f"Error Claude: {data['error'].get('message', 'desconocido')}"
 
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text)
        save_memory(chat_id, "assistant", reply)
        return reply
 
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return "Error al conectar con Claude. Intenta de nuevo."
 
# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10
    )
 
def handle_message(chat_id, text):
    cmd = text.strip().lower().split()[0] if text.startswith("/") else None
 
    if cmd == "/start":
        send_telegram(chat_id,
            "JARVIS activo. Claude + busqueda web real.\n\n"
            "Cartera actualizada: Visa añadida, Nike vendida.\n\n"
            "/cartera /alertas /analiza TICKER\n"
            "/earnings /macro /memoria"
        )
    elif cmd == "/cartera":
        send_telegram(chat_id,
            "CARTERA MIKI — actualizada\n\n"
            "GOOGL +77.44% | 17.78%\n"
            "SP500 +24.10% | 14.99%\n"
            "Europe +23.34% | 12.56%\n"
            "SmallCap +24.48% | 11.42%\n"
            "MONC -3.79% | 7.60%\n"
            "JNJ +61.36% | 5.51%\n"
            "AAPL +20.61% | 5.25%\n"
            "MSFT -12.48% | 4.46%\n"
            "SSNC +5.50% | 4.16%\n"
            "India -7.40% | 3.77%\n"
            "TRET +6.88% | 3.70%\n"
            "TXRH -4.14% | 2.63%\n"
            "Gold +41.91% | 2.30%\n"
            "ZEG +70.78% | 2.03%\n"
            "VISA nueva | 636.82 eur\n"
            "CELH +20.85% | 0.54%\n"
            "NKE VENDIDA"
        )
    elif cmd == "/alertas":
        send_telegram(chat_id,
            "ALERTAS:\n\n"
            "VIGILAR: Microsoft MSFT -12.48%\n"
            "VIGILAR: Moncler MONC -3.79%\n"
            "VIGILAR: MSCI India -7.40%\n\n"
            "Nike vendida. Visa nueva posicion."
        )
    elif cmd == "/analiza":
        parts = text.strip().split()
        if len(parts) < 2:
            send_telegram(chat_id, "Uso: /analiza TICKER\nEjemplo: /analiza MSFT")
            return
        ticker = parts[1].upper()
        send_telegram(chat_id, f"Buscando datos reales de {ticker}...")
        reply = ask_claude(chat_id,
            f"Busca en internet ahora mismo: precio actual de {ticker}, "
            f"PER actual, FCF ultimo año, ultimos resultados trimestrales, "
            f"insiders recientes, noticias importantes ultimos 30 dias, red flags. "
            f"Usa SOLO datos verificados. Dame señal clara con justificacion y proyeccion 2025-2027."
        )
        send_telegram(chat_id, reply)
    elif cmd == "/earnings":
        send_telegram(chat_id, "Buscando earnings...")
        reply = ask_claude(chat_id,
            "Busca las fechas exactas de resultados proximos 60 dias de: "
            "GOOGL, AAPL, MSFT, JNJ, TXRH, SSNC, CELH, VISA. "
            "Solo fechas verificadas y actuales."
        )
        send_telegram(chat_id, reply)
    elif cmd == "/macro":
        send_telegram(chat_id, "Analizando macro...")
        reply = ask_claude(chat_id,
            "Busca el estado macro actual de hoy: "
            "decision FED sobre tipos, inflacion actual, nivel del dolar, VIX actual. "
            "Como afecta a la cartera de Miki?"
        )
        send_telegram(chat_id, reply)
    elif cmd == "/memoria":
        mem = load_memory(chat_id, limit=4)
        if mem:
            resumen = "\n\n".join([f"{m['role'].upper()}: {m['content'][:150]}..." for m in mem])
            send_telegram(chat_id, f"Memoria:\n\n{resumen}")
        else:
            send_telegram(chat_id, "Sin memoria guardada.")
    else:
        send_telegram(chat_id, "Analizando...")
        reply = ask_claude(chat_id, text)
        send_telegram(chat_id, reply)
 
# ── POLLING ───────────────────────────────────────────────────────────────────
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
 
# ── SERVER ────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS V6 - Claude activo")
    def log_message(self, *args):
        pass
 
threading.Thread(target=poll_telegram, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
