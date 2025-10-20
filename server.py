import os
import asyncio
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Reuse handlers and helpers from MAIN2
import MAIN2

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

app = FastAPI()
_ptb_app: Application | None = None


@app.on_event("startup")
async def on_startup():
    global _ptb_app
    _ptb_app = Application.builder().token(TOKEN).post_init(MAIN2.post_init).post_shutdown(MAIN2.post_shutdown).build()

    # handlers (reuse the same as polling version)
    _ptb_app.add_handler(CommandHandler("start", MAIN2.start_command))
    _ptb_app.add_handler(CommandHandler("menu", MAIN2.menu_command))
    _ptb_app.add_handler(CommandHandler("usdt", MAIN2.usdt_command))
    _ptb_app.add_handler(CommandHandler("usd", MAIN2.usd_command))
    _ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, MAIN2.handle_message))
    _ptb_app.add_handler(CallbackQueryHandler(MAIN2.button_handler))

    await _ptb_app.initialize()
    await _ptb_app.start()


@app.on_event("shutdown")
async def on_shutdown():
    global _ptb_app
    if _ptb_app is not None:
        await _ptb_app.stop()
        await _ptb_app.shutdown()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    global _ptb_app
    if _ptb_app is None:
        raise HTTPException(status_code=503, detail="Bot not ready")
    if token != TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    data = await request.json()
    update = Update.de_json(data=data, bot=_ptb_app.bot)
    await _ptb_app.process_update(update)
    return Response(status_code=200)
