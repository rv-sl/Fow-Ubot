from flask import Flask, request, jsonify, render_template
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.types import Message
import asyncio
import threading
import os
import time

app = Flask(__name__)

api_id = int(os.getenv("apiid", 12345))       # replace with your actual default or set as env var
api_hash = os.getenv("apihash", "your_apihash_here")

phone_number_global = None
session_str = None


def progress_callback(current, total, msg, start_time, label="Progress"):
    now = time.time()
    if now - progress_callback.last_edit >= 10:
        percent = (current / total) * 100
        speed = current / (now - start_time + 1)
        eta = (total - current) / speed if speed else 0
        text = (
            f"📦 **{label}**\n"
            f"✅ {current / 1024 ** 2:.2f}MB / {total / 1024 ** 2:.2f}MB ({percent:.2f}%)\n"
            f"⚡️ Speed: {speed / 1024:.2f} KB/s\n"
            f"⏳ ETA: {int(eta)}s"
        )
        try:
            asyncio.run_coroutine_threadsafe(msg.edit(text), asyncio.get_event_loop())
            progress_callback.last_edit = now
        except:
            pass

progress_callback.last_edit = 0


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/send_code", methods=["POST"])
def send_code():
    global phone_number_global
    data = request.get_json()
    phone_number_global = data.get("phone")

    try:
        with Client("anon", api_id, api_hash, in_memory=True) as app_client:
            result = app_client.send_code(phone_number_global)
        return jsonify({"status": "code_sent", "phone_code_hash": result.phone_code_hash})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/verify_code", methods=["POST"])
def verify_code():
    global session_str
    data = request.get_json()
    code = data.get("code")
    phone_code_hash = data.get("phone_code_hash")
    password = data.get("password")

    try:
        with Client("login", api_id, api_hash, in_memory=True) as app_client:
            try:
                app_client.sign_in(phone_number_global, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeeded:
                if not password:
                    return jsonify({"status": "password_needed"})
                app_client.check_password(password)

            session_str = app_client.export_session_string()
        return jsonify({"status": "success", "session_string": session_str})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/start_bot", methods=["POST"])
def start_bot():
    global session_str
    if not session_str:
        return jsonify({"status": "error", "message": "No session found."}), 400

    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        app_client = Client("userbot", session_string=session_str, api_id=api_id, api_hash=api_hash)

        @app_client.on_message(filters.command("start") & filters.me)
        async def start_cmd(client: Client, message: Message):
            await message.reply("✅ UserClient is online. Use `/fo <chat> <message_id>` to fetch a file.")

        @app_client.on_message(filters.command("fo") & filters.me)
        async def fetch_file(client: Client, message: Message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("❌ Usage: `/fo <chat_username_or_id> <message_id>`", quote=True)
                return

            chat_id, msg_id = parts[1], parts[2]
            if not msg_id.isdigit():
                await message.reply("❌ Message ID must be a number.")
                return

            msg_id = int(msg_id)
            status = await message.reply(f"🔍 Fetching message {msg_id} from `{chat_id}`...")

            try:
                target_msg = await client.get_messages(chat_id, msg_id)
            except Exception as e:
                await status.edit(f"❌ Fetch failed: `{e}`")
                return

            if not target_msg or not target_msg.document:
                await status.edit("⚠️ No document found in that message.")
                return

            start = time.time()
            await status.edit("📥 Downloading...")
            try:
                file_path = await client.download_media(
                    target_msg,
                    progress=lambda c, t: progress_callback(c, t, status, start, "Downloading"),
                )
            except Exception as e:
                await status.edit(f"❌ Download error: `{e}`")
                return

            start = time.time()
            await status.edit("📤 Uploading to Saved Messages...")
            try:
                await client.send_document(
                    "me",
                    file_path,
                    caption=f"📤 Fetched from `{chat_id}` [ID: {msg_id}]",
                    progress=lambda c, t: progress_callback(c, t, status, start, "Uploading"),
                )
                await status.edit("✅ Done! Uploaded to Saved Messages.")
            except Exception as e:
                await status.edit(f"❌ Upload failed: `{e}`")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        app_client.run()

    threading.Thread(target=run_bot, daemon=True).start()
    return jsonify({"status": "bot_started"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
