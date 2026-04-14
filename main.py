import os, logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
groq = Groq(api_key=GROQ_KEY)
logging.basicConfig(level=logging.INFO)

SYSTEM = """Eres JARVIS, asistente privado de inversión de Miki. Cartera: €34.145 (+22.03%). Nike -42.63% CRÍTICO. Microsoft -12.48%. Habla en español, directo, como analista senior. Da siempre señal: COMPRAR/MANTENER/VIGILAR/VENDER."""

history = {}

async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if uid not in history: history[uid] = []
    history[uid].append({"role":"user","content":update.message.text})
    r = groq.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"system","content":SYSTEM}]+history[uid][-20:])
    reply = r.choices[0].message.content
    history[uid].append({"role":"assistant","content":reply})
    await update.message.reply_text(reply[:4000])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 JARVIS activo. Cartera €34.145 | +22.03%\n🔴 Nike -42.63% requiere atención.\n\nPregúntame lo que quieras.")

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
app.run_polling()
