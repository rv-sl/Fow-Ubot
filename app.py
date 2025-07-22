from flask import Flask, request, jsonify, render_template
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.types import Message
import threading
import asyncio
import time
import os

app = Flask(__name__)

api_id = int(os.getenv("apiid"))       # Make sure these are set in your env
api_hash = os.getenv("apihash")

client = None
phone_number_global = None
session_str = None
login_error = None


# Progress callback for file uploads/downloads
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
            msg.edit(text)
            progress_callback.last_edit = now
        except:
            pass

progress_callback.last_edit = 0


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/send_code', methods=['POST'])
def send_code():
    global client, phone_number_global, login_error
    phone_number_global = request.json.get('phone')
    login_error = None
    try:
        client = Client(":memory:", api_id, api_hash)
        with client:
            sent_code = client.send_code(phone_number_global)
        return jsonify({"status": "code_sent", "phone_code_hash": sent_code.phone_code_hash})
    except Exception as e:
        login_error = str(e)
        return jsonify({"status": "error", "message": login_error}), 400


@app.route('/verify_code', methods=['POST'])
def verify_code():
    global client, phone_number_global, session_str, login_error
    code = request.json.get('code')
    phone_code_hash = request.json.get('phone_code_hash')
    password = request.json.get('password')  # Optional 2FA password

    try:
        client = Client(":memory:", api_id, api_hash)
        with client:
            try:
                client.sign_in(phone_number_global, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeeded:
                if not password:
                    return jsonify({"status": "password_needed"})
                client.check_password(password)

            session_str = client.export_session_string()
        return jsonify({"status": "success", "session_string": session_str})
    except Exception as e:
        login_error = str(e)
        return jsonify({"status": "error", "message": login_error}), 400


@app.route('/start_bot', methods=['POST'])
def start_bot():
    global session_str
    if not session_str:
        return jsonify({"status": "error", "message": "Not logged in"}), 400

    def run_userbot():
        # Each thread needs its own event loop
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = asyncio.get_event_loop()

        app_client = Client(session_str, api_id=api_id, api_hash=api_hash)

        @app_client.on_message(filters.command("start") & filters.me)
        async def start_command(client: Client, message: Message):
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
                await status.edit(f"❌ Failed to fetch: `{e}`")
                return

            if not target_msg or not target_msg.document:
                await status.edit("⚠️ No document found in that message.")
                return

            # Download
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

            # Upload
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

        print("Userbot is running...")
        app_client.run()

    threading.Thread(target=run_userbot, daemon=True).start()
    return jsonify({"status": "bot_started"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
