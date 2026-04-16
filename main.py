import os, logging, requests, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY       = os.environ.get("GROQ_API_KEY")
TAVILY_KEY     = os.environ.get("TAVILY_KEY")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
PORT           = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)

SYSTEM = """Eres JARVIS, el asistente privado de inversion de Miguel (Miki).
Eres analista financiero senior, gestor de carteras y asesor value investor.

CARTERA REAL DE MIKI (34145 euros, +22.03%):
- Alphabet GOOGL: 6071 eur | +77.44% | peso 17.78% | Alta conviccion
- Fidelity SP500: 5118 eur | +24.10% | peso 14.99% | Alta conviccion
- iShares Europe: 4288 eur | +23.34% | peso 12.56% | Alta conviccion
- Vanguard SmallCap: 3900 eur | +24.48% | peso 11.42% | Alta conviccion
- Moncler MONC: 2596 eur | -3.79% | peso 7.60% | Alta conviccion
- Johnson & Johnson JNJ: 1883 eur | +61.36% | peso 5.51% | Alta conviccion
- Apple AAPL: 1793 eur | +20.61% | peso 5.25% | Alta conviccion
- Microsoft MSFT: 1522 eur | -12.48% | peso 4.46% | Vigilar
- SS&C Technologies SSNC: 1420 eur | +5.50% | peso 4.16% | Media-Alta
- MSCI India: 1287 eur | -7.40% | peso 3.77% | Media-Alta
- Vaneck Real Estate TRET: 1265 eur | +6.88% | peso 3.70% | Media
- Texas Roadhouse TXRH: 898 eur | -4.14% | peso 2.63% | Media-Alta
- Invesco Gold 8PSG: 787 eur | +41.91% | peso 2.30% | Media-Alta
- Zegona ZEG: 694 eur | +70.78% | peso 2.03% | Media
- Nike NKE: 438 eur | -42.63% | peso 1.28% | CRITICO
- Celsius CELH: 186 eur | +20.85% | peso 0.54% | Media

PRINCIPIOS DE ANALISIS (aplica siempre):
1. Verifica en minimo 2 fuentes antes de dar señal
2. Nunca inventes datos — si no tienes el dato, dilo y busca
3. Da siempre señal clara: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER
4. Analiza siempre: FCF, ROIC, margenes, deuda, PER, EV/FCF, valor intrinseco, margen de seguridad
5. Detecta red flags: directiva, contabilidad, guidance imposible, insiders vendiendo
6. Aplica mentalidad value: precio vs valor intrinseco es lo que importa
7. Habla en español, directo, sin relleno, como analista senior real
8. Prioridad alertas por peso: Nike > Microsoft > Moncler > MSCI India

CUANDO ANALICES UNA EMPRESA dame siempre:
- Precio actual vs valor intrinseco estimado
- Margen de seguridad
- PER actual vs historico
- FCF y tendencia
- Red flags si existen
- Señal final con justificacion
- Proyeccion 2025-2027"""

history = {}

# ── SUPABASE MEMORIA ─────────────────────────────────────────────────────────
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
            json={
                "chat_id": str(chat_id),
                "role": role,
                "content": content[:2000],
                "created_at": datetime.utcnow().isoformat()
            },
            timeout=5
        )
    except Exception as e:
        logging.error(f"Supabase save: {e}")

def load_memory(chat_id, limit=12):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            },
            params={
                "chat_id": f"eq.{chat_id}",
                "order": "created_at.desc",
                "limit": limit
            },
            timeout=5
        )
        rows = r.json()
        if isinstance(rows, list):
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return []
    except Exception as e:
        logging.error(f"Supabase load: {e}")
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
        return "\n".join([f"{x['title']}: {x['content'][:300]}" for x in results[:4]])
    except:
        return ""

# ── GROQ ──────────────────────────────────────────────────────────────────────
def ask_groq(chat_id, text):
    persistent = load_memory(chat_id, limit=12)
    if chat_id not in history:
        history[chat_id] = []

    web_data = search_web(text)
    full_text = f"{text}\n\nDATOS WEB ACTUALES:\n{web_data}" if web_data else text

    history[chat_id].append({"role": "user", "content": full_text})
    all_messages = persistent[-8:] + history[chat_id][-10:]

    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": SYSTEM}] + all_messages
        },
        timeout=30
    )
    reply = r.json()["choices"][0]["message"]["content"]
    history[chat_id].append({"role": "assistant", "content": reply})

    save_memory(chat_id, "user", text)
    save_memory(chat_id, "assistant", reply)

    return reply

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10
    )

def handle_command(chat_id, text):
    cmd = text.strip().lower().split()[0]

    if cmd == "/start":
        send_telegram(chat_id,
            "JARVIS activo. Cartera 34.145 eur +22.03%.\n\n"
            "ALERTA: Nike -42.63% requiere revision urgente.\n\n"
            "Comandos disponibles:\n"
            "/cartera — resumen completo\n"
            "/alertas — posiciones en riesgo\n"
            "/analiza TICKER — analisis profundo\n"
            "/earnings — proximas fechas de resultados\n"
            "/macro — situacion macro actual\n"
            "/memoria — ver historial guardado\n\n"
            "O escribe lo que quieras analizar."
        )

    elif cmd == "/cartera":
        send_telegram(chat_id,
            "CARTERA MIKI — 34.145 eur | +22.03%\n\n"
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
            "NKE -42.63% | 1.28% CRITICO\n"
            "CELH +20.85% | 0.54%"
        )

    elif cmd == "/alertas":
        send_telegram(chat_id,
            "ALERTAS ACTIVAS:\n\n"
            "CRITICO: Nike NKE -42.63% — tesis bajo revision\n"
            "VIGILAR: Microsoft MSFT -12.48% — guidance Azure\n"
            "VIGILAR: Moncler MONC -3.79% — sector lujo presionado\n"
            "VIGILAR: MSCI India -7.40% — macro volatil\n\n"
            "Escribe /analiza NKE para analisis completo de Nike."
        )

    elif cmd == "/analiza":
        parts = text.strip().split()
        if len(parts) < 2:
            send_telegram(chat_id, "Uso: /analiza TICKER\nEjemplo: /analiza NKE")
            return
        ticker = parts[1].upper()
        send_telegram(chat_id, f"Analizando {ticker} con datos reales...")
        reply = ask_groq(chat_id,
            f"Analiza {ticker} en profundidad. Busca precio actual, ultimos resultados, "
            f"FCF, ROIC, margenes, deuda, PER vs historico, valor intrinseco, margen de seguridad, "
            f"red flags, insider activity, proximos earnings. Dame señal clara y proyeccion 2025-2027."
        )
        send_telegram(chat_id, reply)

    elif cmd == "/earnings":
        send_telegram(chat_id, "Buscando proximos earnings...")
        reply = ask_groq(chat_id,
            "Busca las fechas de presentacion de resultados de los proximos 60 dias de: "
            "GOOGL, AAPL, MSFT, NKE, JNJ, TXRH, SSNC, CELH, MONC, ZEG, SSNC. "
            "Ordena por fecha mas proxima primero."
        )
        send_telegram(chat_id, reply)

    elif cmd == "/macro":
        send_telegram(chat_id, "Analizando macro...")
        reply = ask_groq(chat_id,
            "Dame el estado macro actual: FED y tipos de interes, inflacion, dolar, VIX, "
            "petroleo, situacion geopolitica. Como afecta a la cartera de Miki?"
        )
        send_telegram(chat_id, reply)

    elif cmd == "/memoria":
        mem = load_memory(chat_id, limit=6)
        if mem:
            resumen = "\n\n".join([f"{m['role'].upper()}: {m['content'][:150]}..." for m in mem[-4:]])
            send_telegram(chat_id, f"Ultimos recuerdos guardados:\n\n{resumen}")
        else:
            send_telegram(chat_id, "No hay memoria guardada todavia.")

    else:
        send_telegram(chat_id, "Buscando datos reales...")
        reply = ask_groq(chat_id, text)
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
                    if text.startswith("/"):
                        handle_command(chat_id, text)
                    else:
                        send_telegram(chat_id, "Analizando...")
                        reply = ask_groq(chat_id, text)
                        send_telegram(chat_id, reply)
        except Exception as e:
            logging.error(f"Poll error: {e}")

# ── SERVER ────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS V3 activo")
    def log_message(self, *args):
        pass

threading.Thread(target=poll_telegram, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
