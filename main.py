from typing import Final
import os
import urllib.request
import urllib.parse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters




TOKEN: Final = os.getenv("TOKEN")
BOT_USERNAME: Final = "@magnetusdt_bot"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("안녕하세요! 저는 MagnetUSDT 봇입니다! /help 명령어를 사용해보세요!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("명령어 라고 말해주시면 메뉴가 나옵니다./ custom 명령어")

async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("아직 테스트중입니다. ")



def handle_response(text: str):
    process: str = text.lower()

    if '코인구매' in process:
        return"코인구매 실행합니다!"
    if '명령어' in process:
        return" 안녕하세요 테스트 중입니다. \n (코인판매) 혹은 \n (코인구매) 라고 말씀해주세요!"
    if '코인판매' in process:
        return"코인판매 실행합니다!"
    
    return "이해하지 못한 명령어 입니다."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text: str = update.message.text or ""
    response = handle_response(text)
    await update.message.reply_text(response)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')


if __name__ == "__main__":
    print("Starting bot...")
    if not TOKEN:
        raise RuntimeError("Missing TOKEN environment variable. Set TOKEN to your Telegram bot token.")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("custom", custom_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Starting...")
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "8443")),
            url_path=os.getenv("WEBHOOK_PATH", ""),
            webhook_url=webhook_url
        )
    else:
        try:
            base = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
            qs = urllib.parse.urlencode({"drop_pending_updates": "true"})
            urllib.request.urlopen(f"{base}?{qs}")
        except Exception:
            pass
        app.run_polling(drop_pending_updates=True)



