import os, logging, asyncio, requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
logging.basicConfig(level=logging.INFO)

SYSTEM = "Eres JARVIS, asistente privado de inversion de Miki. Cartera 34145 euros +22.03%. Nike -42.63% CRITICO. Microsoft -12.48%. Habla en espanol, directo, como analista senior. Da siempre senal: COMPRAR/MANTENER/VIGILAR/VENDER."

history = {}

def ask_groq(uid, text):
    if uid not in history:
        history[uid] = []
    history[uid].append({"role": "user", "content": text})
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": SYSTEM}] + history[uid][-20:]}
    )
    reply = r.json()["choices"][0]["message"]["content"]
    history[uid].append({"role": "assistant", "content": reply})
    return reply

async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reply = ask_groq(update.effective_chat.id, update.message.text)
    await update.message.reply_text(reply[:4000])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("JARVIS activo. Cartera 34.145 euros +22.03%. Nike -42.63% requiere atencion urgente. Preguntame lo que quieras.")

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
