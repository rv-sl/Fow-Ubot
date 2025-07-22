from flask import Flask, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio
import threading
import os
import time

app = Flask(__name__)

api_id = int(os.getenv("apiid", 123456))
api_hash = os.getenv("apihash", "your_api_hash")
session_str = os.getenv("ss", "your_session_string")

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
def start_userbot():
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        app_client = Client("userbot", session_string=session_str, api_id=api_id, api_hash=api_hash)

        @app_client.on_message(filters.command("start") & filters.me)
        async def start_command(client: Client, message: Message):
            await message.reply("✅ UserBot is online! Use `/fo <chat> <msg_id>` to fetch content.")

        @app_client.on_message(filters.command("fo") & filters.me)
        async def forward_from_private(client: Client, message: Message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("❌ Usage: `/fo <chat> <message_id>`")
                return

            chat_id = parts[1]
            try:
                msg_id = int(parts[2])
            except:
                await message.reply("❌ Message ID must be a number.")
                return

            status = await message.reply("🔍 Fetching message...")

            try:
                target_msg = await client.get_messages(chat_id, msg_id)
            except Exception as e:
                await status.edit(f"❌ Fetch failed: `{e}`")
                return

            if target_msg.document or target_msg.video or target_msg.audio or target_msg.photo:
                media_type = "document"
                if target_msg.photo:
                    media_type = "photo"
                elif target_msg.video:
                    media_type = "video"
                elif target_msg.audio:
                    media_type = "audio"

                await status.edit(f"📥 Downloading {media_type}...")
                start = time.time()
                try:
                    file_path = await client.download_media(
                        target_msg,
                        progress=lambda c, t: progress_callback(c, t, status, start, "Downloading")
                    )
                except Exception as e:
                    await status.edit(f"❌ Download error: `{e}`")
                    return

                await status.edit("📤 Uploading to Saved Messages...")
                try:
                    await client.send_document(
                        "me",
                        file_path,
                        caption=target_msg.caption or f"📤 Re-uploaded from `{chat_id}` [ID: {msg_id}]",
                        progress=lambda c, t: progress_callback(c, t, status, start, "Uploading")
                    )
                    await status.edit("✅ File re-uploaded to Saved Messages.")
                except Exception as e:
                    await status.edit(f"❌ Upload failed: `{e}`")
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)

            elif target_msg.text:
                try:
                    await client.send_message("me", f"✉️ Fetched from `{chat_id}` [ID: {msg_id}]:\n\n{target_msg.text}")
                    await status.edit("✅ Text message copied to Saved Messages.")
                except Exception as e:
                    await status.edit(f"❌ Text send failed: `{e}`")
            else:
                await status.edit("⚠️ No downloadable content or text found.")

        app_client.run()

    threading.Thread(target=run, daemon=True).start()
    return "✅ UserBot started."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
