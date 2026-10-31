import os
import re
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)
from supabase import create_client, Client

# ==================== الإعدادات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
COURSE_LINK = os.environ.get("COURSE_LINK", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ixcwpmpxjvyvqeijikdr.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

WELCOME = """أهلاً بك في بوت N9 
للاشتراك في دورة الفاينل انجليزي

المبلغ: 89 ريال للفاينل. لتفاصيل أكثر عن الدورة: https://t.me/EngN927/923

💳 **طريقة التسجيل:**
التحويل على الحساب التالي (urpay / الراجحي):
`SA7580205583481222121010`
*(ملاحظة: في حال طلب منك البنك اسم المستفيد، يمكنك كتابة أي اسم عادي وحول)*

📸 **يرجى إرسال صورة إيصال التحويل هنا في المحادثة** 👇

بعد التأكد من التحويل سيصلك رابط الدخول للدورة.
في حال مواجهة أي مشكلة في التحويل أو بخصوص الدورة يمكنك الإرسال هنا وسيتم الرد عليك.

شكراً لكم 🤍"""


def course_message_text():
    return f"✅ **تم التأكد من التحويل بنجاح!**\n\nتفضل رابط الدخول للدورة:\n{COURSE_LINK}\n\nمرحباً بك 🌟"


def md(text) -> str:
    # يمنع أخطاء Markdown لما الاسم أو الرسالة فيها _ أو * أو `
    return escape_markdown(str(text or ""), version=1)


def is_admin(update: Update) -> bool:
    # يشتغل سواء ADMIN_ID حسابك أو ID قروب الإدارة
    user_ok = update.effective_user is not None and update.effective_user.id == ADMIN_ID
    chat_ok = update.effective_chat is not None and update.effective_chat.id == ADMIN_ID
    return user_ok or chat_ok


# ==================== سيرفر 24/7 لـ Render ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write("N9 Course Bot is Online 24/7!".encode('utf-8'))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ==================== حفظ البيانات في Supabase ====================
def _archive_message_sync(user_id, full_name, username, msg_type, content):
    try:
        supabase.table("course_messages").insert({
            "user_id": user_id,
            "full_name": full_name,
            "username": username or "",
            "msg_type": msg_type,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error archiving message: {e}")

async def archive_to_db(user_id, full_name, username, msg_type, content):
    await asyncio.to_thread(_archive_message_sync, user_id, full_name, username, msg_type, content)


# ---------- الطلاب المقبولين (مسموح لهم يدخلون القروب) ----------
def _save_approved_sync(user_id):
    supabase.table("approved_users").upsert({"user_id": user_id}).execute()

async def save_approved(user_id) -> bool:
    try:
        await asyncio.to_thread(_save_approved_sync, user_id)
        return True
    except Exception as e:
        print(f"Error saving approved user: {e}")
        return False

def _is_approved_sync(user_id):
    res = supabase.table("approved_users").select("user_id").eq("user_id", user_id).execute()
    return bool(res.data)

async def is_approved(user_id) -> bool:
    try:
        return await asyncio.to_thread(_is_approved_sync, user_id)
    except Exception as e:
        # أي خطأ = ما نقبل تلقائي (أمان)
        print(f"Error checking approved user: {e}")
        return False

# ==================== المعالجات (Handlers) ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await archive_to_db(user.id, user.full_name, user.username, "command", "/start")
    await update.message.reply_text(WELCOME, disable_web_page_preview=True, parse_mode="Markdown")

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return

    name = user.full_name
    username = f"@{user.username}" if user.username else "بدون يوزر"
    uid = user.id

    # 1. حفظ الإيصال في Supabase
    await archive_to_db(uid, name, user.username, "receipt", "تم إرسال إيصال/مرفق")

    # 2. إشعار الطالب
    await update.message.reply_text("✅ **وصلني الإيصال!**\nجاري التأكد من التحويل وسيتم إرسال رابط الدخول قريباً.", parse_mode="Markdown")

    # 3. إرسال الإيصال للأدمن مع أزرار القبول/الرفض
    if ADMIN_ID != 0:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)

        keyboard = [
            [
                InlineKeyboardButton("✅ تأكيد وإرسال الرابط", callback_data=f"ok:{uid}"),
                InlineKeyboardButton("❌ رفض الإيصال", callback_data=f"no:{uid}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📄 **إيصال جديد تم رفعه!**\n👤 الاسم: {md(name)}\n🔗 اليوزر: {md(username)}\n🔑 ID: `{uid}`",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def student_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return

    name = user.full_name
    username = f"@{user.username}" if user.username else "بدون يوزر"
    text = update.message.text

    await archive_to_db(user.id, name, user.username, "text", text)

    await update.message.reply_text("📨 وصلت رسالتك، سيتم الرد عليك قريباً.")

    if ADMIN_ID != 0:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💬 **رسالة من الطالب:**\n👤 الاسم: {md(name)} ({md(username)})\n🔑 ID: `{user.id}`\n\nالرسالة:\n{md(text)}",
            parse_mode="Markdown"
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, uid_str = query.data.split(":")
    uid = int(uid_str)

    try:
        if action == "ok":
            await context.bot.send_message(
                chat_id=uid,
                text=course_message_text(),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            # التسجيل يصير بس بعد ما الرسالة توصل
            if await save_approved(uid):
                status = "✅ *تم قبول الطالب وإرسال الرابط*"
            else:
                status = "⚠️ *انرسل الرابط بس ما تسجّل الطالب، اقبل طلبه يدوي*"
            await archive_to_db(uid, "System", "", "status", "تم قبول الاشتراك")
        else:
            await context.bot.send_message(
                chat_id=uid,
                text="❌ **نعتذر، لم نتمكن من التأكد من الإيصال المرسل.**\nالرجاء التأكد من الإيصال وإعادة إرساله مرة ثانية بشكل واضح، أو مراسلتنا هنا إذا واجهتك مشكلة.",
                parse_mode="Markdown"
            )
            status = "❌ *تم الرفض وإبلاغ الطالب*"
            await archive_to_db(uid, "System", "", "status", "تم رفض الإيصال")

    except Exception:
        status = "⚠️ *حدث خطأ! (ربما قام الطالب بحظر البوت)*"

    original_text = md(query.message.text or "طلب اشتراك")
    await query.edit_message_text(text=f"{original_text}\n\n{status}", parse_mode="Markdown")

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    replied_msg = update.message.reply_to_message
    src = replied_msg.text or replied_msg.caption or ""

    found = re.search(r"ID: `?(\d+)`?", src)
    if not found:
        await update.message.reply_text("⚠️ اعمل (Reply) على الرسالة التي تحتوي على ID الطالب.")
        return

    uid = int(found.group(1))

    try:
        if update.message.text:
            await context.bot.send_message(chat_id=uid, text=f"📩 **رد من الإدارة:**\n\n{md(update.message.text)}", parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=uid, text="📩 **مرفق من الإدارة:**", parse_mode="Markdown")
            await context.bot.copy_message(chat_id=uid, from_chat_id=update.message.chat_id, message_id=update.message.message_id)

        await update.message.reply_text("✅ **تم إرسال ردك للطالب بنجاح.**", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ **فشل الإرسال.** ربما الطالب حظر البوت.")


# ==================== قبول يدوي بأمر /approve ====================
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("اكتب: /approve ID\nمثال: /approve 2012574372")
        return

    uid = int(context.args[0])

    # 1. إرسال رسالة الرابط للطالب
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=course_message_text(),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception:
        await update.message.reply_text("❌ ما قدرت أرسل له. ممكن ما ضغط Start في البوت أو حاظره.")
        return

    # 2. تسجيله في المقبولين
    if not await save_approved(uid):
        await update.message.reply_text("⚠️ انرسل الرابط بس ما تسجّل، اقبل طلبه يدوي.")
        return

    await archive_to_db(uid, "System", "", "status", "تم قبول الاشتراك (يدوي)")

    # 3. لو عنده طلب انضمام معلّق، نقبله على طول
    pending = context.bot_data.get("pending_requests", {})
    group_id = pending.pop(uid, None)
    if group_id:
        try:
            await context.bot.approve_chat_join_request(chat_id=group_id, user_id=uid)
            await update.message.reply_text(f"✅ انرسل الرابط وتسجّل {uid} ودخل القروب")
            return
        except Exception:
            pass

    await update.message.reply_text(f"✅ انرسل الرابط وتسجّل {uid}")


# ==================== طلبات الانضمام للقروب ====================
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user = req.from_user
    username = f"@{user.username}" if user.username else "بدون يوزر"

    if await is_approved(user.id):
        try:
            await req.approve()
            await archive_to_db(user.id, user.full_name, user.username, "status", "دخل القروب")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ دخل القروب: {user.full_name} ({username})\n🔑 ID: {user.id}"
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ ما قدرت أقبل {user.full_name} (ID: {user.id})\nالسبب: {e}"
            )
    else:
        # نحفظ الطلب عشان لو سويت /approve يدخل على طول
        context.bot_data.setdefault("pending_requests", {})[user.id] = req.chat.id
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"⚠️ طلب انضمام من شخص غير مسجّل:\n"
                f"👤 {user.full_name} ({username})\n"
                f"🔑 ID: {user.id}\n\n"
                f"لو دافع اكتب:\n/approve {user.id}"
            )
        )


# ==================== التشغيل ====================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    # الطلاب: بس في الخاص (عشان البوت ما يرد على أحد داخل قروب الدورة)
    private = filters.ChatType.PRIVATE
    admin_chat = private | filters.Chat(ADMIN_ID)
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & private & (~filters.User(ADMIN_ID)), handle_receipt))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & private & (~filters.User(ADMIN_ID)), student_text))
    app.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_ID) & admin_chat, admin_reply))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(ok|no):"))

    print("Course Bot with Full Supabase Archiving is Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
