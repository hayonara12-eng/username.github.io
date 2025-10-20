from typing import Final
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
import httpx

TOKEN: Final = os.getenv("BOT_TOKEN", "8411851385:AAGm6zy0sqygpHii6RSrsHGxgyLPYyuLpt8")
ADMIN_CHAT_ID: Final = int((os.getenv("ADMIN_CHAT_ID") or "0"))

# UI: 공통 인라인 메뉴
def build_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("코인구매", callback_data="BUY"), InlineKeyboardButton("코인판매", callback_data="SELL")],
        [InlineKeyboardButton("테더가격", callback_data="USDT_PRICE"), InlineKeyboardButton("달러가격", callback_data="USD_PRICE")],
        [InlineKeyboardButton("도움말", callback_data="HELP")],
    ]
    return InlineKeyboardMarkup(keyboard)

MENU_PROMPT = "안녕하세요 ! usdt korea_bot 입니다. \n명령어를 선택하세요: )"
HELP_TEXT = "아직준비중입니다. 좋은 모습으로 뵙겠습니다"
MENUPANEL_TEXT = """
안녕하세요 ! 현재 작업이 진행중인상태입니다.
제가 원하는것은 이 봇을 통해해사람들이 불법자금에 대한 의심없이
코인을 P2P로
거래할수 있도록 하는것입니다.
"""

# 테더 가격 조회 (Bithumb: USDT_KRW) - KRW만 반환
async def fetch_tether_krw(session: httpx.AsyncClient):
    url = "https://api.bithumb.com/public/ticker/USDT_KRW"
    try:
        print("[fetch_tether_krw] GET", url)
        resp = await session.get(url)
        print("[fetch_tether_krw] status:", resp.status_code)
        if resp.status_code != 200:
            try:
                txt = (await resp.aread())[:200]
                print("[fetch_tether_krw] body:", txt)
            except Exception:
                pass
            raise RuntimeError(f"bithumb status {resp.status_code}")
        try:
            data = resp.json()
        except Exception as je:
            txt = (await resp.aread())[:200]
            print("[fetch_tether_krw] json error:", je, "body:", txt)
            raise
        # print a small preview
        print("[fetch_tether_krw] data keys:", list(data.keys())[:5])
        closing = data.get("data", {}).get("closing_price")
        if not closing:
            raise RuntimeError("bithumb missing closing_price")
        return float(closing)
    except Exception as e:
        print("[fetch_tether_krw] error (bithumb):", e)
        # Fallback: Coingecko tether->KRW
        cg = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=krw"
        try:
            print("[fetch_tether_krw] fallback GET", cg)
            r2 = await session.get(cg)
            print("[fetch_tether_krw] fallback status:", r2.status_code)
            if r2.status_code != 200:
                try:
                    txt2 = (await r2.aread())[:200]
                    print("[fetch_tether_krw] fallback body:", txt2)
                except Exception:
                    pass
                return None
            data2 = r2.json()
            price = data2.get("tether", {}).get("krw")
            if price:
                return float(price)
            return None
        except Exception as e2:
            print("[fetch_tether_krw] fallback error (coingecko):", e2)
            return None

# Minimal admin notification (only used for BUY/SELL)
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)
        except Exception as e:
            print("[notify_admin] error:", e)

# 달러 환율(USD->KRW) 조회 헬퍼 (exchangerate.host)
async def fetch_usdkrw_rate(session: httpx.AsyncClient, bot_data: dict, ttl_seconds: int = 60):
    # 캐시 사용
    cache = bot_data.setdefault("usdkrw_cache", {})
    now = datetime.now(timezone.utc).timestamp()
    if cache.get("ts") and (now - cache["ts"] <= ttl_seconds):
        return cache.get("value")
    # 1) 기본: exchangerate.host
    url1 = "https://api.exchangerate.host/latest?base=USD&symbols=KRW"
    # 2) 백업: open.er-api.com
    url2 = "https://open.er-api.com/v6/latest/USD"
    # 3) 보조 백업: frankfurter.app
    url3 = "https://api.frankfurter.app/latest?from=USD&to=KRW"

    # 시도 1
    try:
        print("[fetch_usdkrw_rate] primary GET", url1)
        resp = await session.get(url1)
        print("[fetch_usdkrw_rate] primary status:", resp.status_code)
        if resp.status_code != 200:
            try:
                txt = (await resp.aread())[:200]
                print("[fetch_usdkrw_rate] primary body:", txt)
            except Exception:
                pass
            raise RuntimeError(f"status {resp.status_code}")
        try:
            data = resp.json()
        except Exception as je:
            txt = (await resp.aread())[:200]
            print("[fetch_usdkrw_rate] primary json error:", je, "body:", txt)
            raise
        rate = float(data["rates"]["KRW"])  # 1 USD in KRW
        cache.update({"value": rate, "ts": now})
        return rate
    except Exception as e:
        print("[fetch_usdkrw_rate] primary failed:", e)
    # 시도 2
    try:
        print("[fetch_usdkrw_rate] fallback GET", url2)
        resp = await session.get(url2)
        print("[fetch_usdkrw_rate] fallback status:", resp.status_code)
        if resp.status_code != 200:
            try:
                txt = (await resp.aread())[:200]
                print("[fetch_usdkrw_rate] fallback body:", txt)
            except Exception:
                pass
            raise RuntimeError(f"status {resp.status_code}")
        try:
            data = resp.json()
        except Exception as je:
            txt = (await resp.aread())[:200]
            print("[fetch_usdkrw_rate] fallback json error:", je, "body:", txt)
            raise
        rate = float(data["rates"]["KRW"])  # 1 USD in KRW
        cache.update({"value": rate, "ts": now})
        return rate
    except Exception as e:
        print("[fetch_usdkrw_rate] fallback failed:", e)
    # 시도 3
    try:
        print("[fetch_usdkrw_rate] second fallback GET", url3)
        resp = await session.get(url3)
        print("[fetch_usdkrw_rate] second fallback status:", resp.status_code)
        if resp.status_code != 200:
            try:
                txt = (await resp.aread())[:200]
                print("[fetch_usdkrw_rate] second fallback body:", txt)
            except Exception:
                pass
            return None
        try:
            data = resp.json()
        except Exception as je:
            txt = (await resp.aread())[:200]
            print("[fetch_usdkrw_rate] second fallback json error:", je, "body:", txt)
            return None
        # frankfurter: {"amount":1.0,"base":"USD","date":"...","rates":{"KRW":xxxx}}
        rate = float(data["rates"]["KRW"])  # 1 USD in KRW
        cache.update({"value": rate, "ts": now})
        return rate
    except Exception as e:
        print("[fetch_usdkrw_rate] second fallback failed:", e)
        return None

# KST 타임스탬프 포맷
def kst_now_str():
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENU_PROMPT, reply_markup=build_menu())

async def usdt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session: httpx.AsyncClient = await ensure_http_session(context.application)
    krw = await fetch_tether_krw(session)
    if krw:
        ts = kst_now_str()
        await update.message.reply_text(f"테더 가격 (Bithumb): 1 USDT = ₩{krw:,.0f}\n조회시각(KST): {ts}")
    else:
        # Fallback: use USD→KRW rate as ~USDT price
        rate = await fetch_usdkrw_rate(session, context.application.bot_data)
        if rate:
            ts = kst_now_str()
            await update.message.reply_text(f"테더 가격(근사): 1 USDT ≈ ₩{rate:,.0f}\n(거래소 API 실패로 환율로 근사)\n조회시각(KST): {ts}")
        else:
            await update.message.reply_text("테더 가격을 가져오지 못했습니다. (로그 확인)")

async def usd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session: httpx.AsyncClient = await ensure_http_session(context.application)
    rate = await fetch_usdkrw_rate(session, context.application.bot_data)
    if rate:
        ts = kst_now_str()
        await update.message.reply_text(f"달러 환율: 1 USD = ₩{rate:,.0f}\n조회시각(KST): {ts}")
    else:
        await update.message.reply_text("달러 환율을 가져오지 못했습니다. (로그 확인)")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENU_PROMPT, reply_markup=build_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 어떤 말을 하더라도 처음엔 메뉴를 보여줌. 이미 보여줬다면 다시 보내지 않음.
    text = (update.message.text or "")
    if "메뉴" in text:
        await update.message.reply_text(MENU_PROMPT, reply_markup=build_menu())
        return
    if ("테더가격" in text) or ("테더" in text and "가격" in text):
        session: httpx.AsyncClient = await ensure_http_session(context.application)
        krw_task = asyncio.create_task(fetch_tether_krw(session))
        rate_task = asyncio.create_task(fetch_usdkrw_rate(session, context.application.bot_data))
        krw, rate = await asyncio.gather(krw_task, rate_task)
        if krw or rate:
            ts = kst_now_str()
            if krw and rate:
                usd = krw / rate
                usd_str = f"{usd:.4f}".rstrip('0').rstrip('.')
                await update.message.reply_text(f"테더 가격 (Bithumb): 1 USDT = ₩{krw:,.0f} (≈ ${usd_str})\n조회시각(KST): {ts}")
            elif not krw and rate:
                await update.message.reply_text(f"테더 가격(근사): 1 USDT ≈ ₩{rate:,.0f}\n(거래소 API 실패로 환율로 근사)\n조회시각(KST): {ts}")
            else:
                await update.message.reply_text(f"테더 가격 (Bithumb): 1 USDT = ₩{krw:,.0f}\n(달러 환율 조회 실패로 USD 미표시)\n조회시각(KST): {ts}")
        else:
            await update.message.reply_text("테더 가격을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
        return
    if ("달러가격" in text) or ("달러" in text and "가격" in text):
        session: httpx.AsyncClient = await ensure_http_session(context.application)
        rate = await fetch_usdkrw_rate(session, context.application.bot_data)
        if rate:
            ts = kst_now_str()
            await update.message.reply_text(f"달러 환율: 1 USD = ₩{rate:,.0f}\n조회시각(KST): {ts}")
        else:
            await update.message.reply_text("달러 환율을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
        return
    if not context.chat_data.get("menu_shown"):
        context.chat_data["menu_shown"] = True
        await update.message.reply_text(MENU_PROMPT, reply_markup=build_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    if data in ("BUY", "SELL"):
        # '아직 준비중입니다'를 표시하고, 같은 메뉴를 유지
        try:
            user = query.from_user
            uid = user.id if user else "?"
            name = user.full_name if user else "?"
            uname = (user.username or "") if user else ""
            handle = f"@{uname}" if uname else f"id={uid}"
            action_text = "코인구매 원합니다" if data == "BUY" else "코인판매 원합니다"
            if isinstance(uid, int) and can_notify_buy_sell(context.application, uid):
                await notify_admin(context, f"[알림] {name} ({handle}) — {action_text}")
        except Exception:
            pass
        try:
            await query.edit_message_text("관리자가 연락 드리겠습니다", reply_markup=build_menu())
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat.id, text="관리자가 연락 드리겠습니다", reply_markup=build_menu())
    elif data == "HELP":
        # 도움말: 새 메시지로 메뉴판 전송 + 메뉴 UI 재표시
        await context.bot.send_message(chat_id=query.message.chat.id, text=MENUPANEL_TEXT)
        await context.bot.send_message(chat_id=query.message.chat.id, text=MENU_PROMPT, reply_markup=build_menu())
    elif data == "USDT_PRICE":
        session: httpx.AsyncClient = await ensure_http_session(context.application)
        krw_task = asyncio.create_task(fetch_tether_krw(session))
        rate_task = asyncio.create_task(fetch_usdkrw_rate(session, context.application.bot_data))
        krw, rate = await asyncio.gather(krw_task, rate_task)
        if krw or rate:
            ts = kst_now_str()
            if krw and rate:
                usd = krw / rate
                usd_str = f"{usd:.4f}".rstrip('0').rstrip('.')
                await context.bot.send_message(chat_id=query.message.chat.id, text=f"테더 가격 (Bithumb): 1 USDT = ₩{krw:,.0f} (≈ ${usd_str})\n조회시각(KST): {ts}", reply_markup=build_menu())
            elif not krw and rate:
                await context.bot.send_message(chat_id=query.message.chat.id, text=f"테더 가격(근사): 1 USDT ≈ ₩{rate:,.0f}\n(거래소 API 실패로 환율로 근사)\n조회시각(KST): {ts}", reply_markup=build_menu())
            else:
                await context.bot.send_message(chat_id=query.message.chat.id, text=f"테더 가격 (Bithumb): 1 USDT = ₩{krw:,.0f}\n(달러 환율 조회 실패로 USD 미표시)\n조회시각(KST): {ts}", reply_markup=build_menu())
        else:
            await context.bot.send_message(chat_id=query.message.chat.id, text="테더 가격을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.", reply_markup=build_menu())
    elif data == "USD_PRICE":
        session: httpx.AsyncClient = await ensure_http_session(context.application)
        rate = await fetch_usdkrw_rate(session, context.application.bot_data)
        if rate:
            ts = kst_now_str()
            await context.bot.send_message(chat_id=query.message.chat.id, text=f"달러 환율: 1 USD = ₩{rate:,.0f}\n조회시각(KST): {ts}", reply_markup=build_menu())
        else:
            await context.bot.send_message(chat_id=query.message.chat.id, text="달러 환율을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.", reply_markup=build_menu())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')

async def post_init(application: Application):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PTB-Bot/1.0"}
    # Harden client: disable http2, follow redirects, and disable TLS verify temporarily for diagnosis
    session = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        headers=headers,
        http2=False,
        follow_redirects=True,
        verify=False,
    )
    application.bot_data["http"] = session

async def post_shutdown(application: Application):
    session: httpx.AsyncClient = application.bot_data.get("http")
    if session:
        await session.aclose()

# Lazy factory to ensure HTTP client exists even if post_init didn't run yet
async def ensure_http_session(application: Application) -> httpx.AsyncClient:
    session: httpx.AsyncClient | None = application.bot_data.get("http")
    if session is None:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PTB-Bot/1.0"}
        session = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers=headers,
            http2=False,
            follow_redirects=True,
            verify=False,
        )
        application.bot_data["http"] = session
    return session

# Throttle BUY/SELL admin alerts per user (default: 10 minutes)
def can_notify_buy_sell(application: Application, user_id: int, window_seconds: int = 600) -> bool:
    store = application.bot_data.setdefault("buy_sell_notify_ts", {})
    now = datetime.now(timezone.utc).timestamp()
    last = store.get(user_id, 0)
    if (now - last) >= window_seconds:
        store[user_id] = now
        return True
    return False

async def _main():
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("usdt", usdt_command))
    app.add_handler(CommandHandler("usd", usd_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, poll_interval=0.5)
    try:
        # wait forever
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    # On Windows ensure selector policy
    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    print("Starting bot...")
    asyncio.run(_main())



