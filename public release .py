#!/usr/bin/env python3
""" Telegram qBittorrent Bot - Full Debugged Version """

import logging
import os
import re
import asyncio
from mega import Mega
from qbittorrentapi import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
BOT_TOKEN = "Bot  Token Here" 
QB_HOST = 'Local host'
QB_PORT = 8080
QB_USERNAME = 'admin'
QB_PASSWORD = 'password'

MEGA_EMAIL = "Email"
MEGA_PASSWORD = "password"

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CLIENT INITIALIZATION ---
try:
    QB = Client(host=QB_HOST, port=QB_PORT, username=QB_USERNAME, password=QB_PASSWORD)
    QB.auth_log_in()
    logger.info("Connected to qBittorrent")
except Exception as e:
    logger.error(f"Could not connect to qBittorrent: {e}")

mega = Mega()
MEGA_CLIENT = mega.login(MEGA_EMAIL, MEGA_PASSWORD)

# --- UTILS ---
def is_magnet_link(text: str) -> bool:
    return bool(re.match(r'magnet:\?xt=urn:btih:', text, re.IGNORECASE))

def sync_upload_to_mega(torrent_hash):
    """Synchronous function to handle the actual upload."""
    try:
        torrent = QB.torrents_info(torrent_hashes=torrent_hash)[0]
        content_path = os.path.join(torrent.save_path, torrent.name)
        
        if not os.path.exists(content_path):
            return f"❌ Path not found: {content_path}"
        
        # This part can take a long time
        node = MEGA_CLIENT.upload(content_path)
        link = MEGA_CLIENT.get_upload_link(node)
        return f"✅ MEGA Link: {link}"
    except Exception as e:
        return f"❌ MEGA Error: {str(e)}"

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **qBittorrent Telegram Bot**\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/list - List top 10 torrents\n"
        "Send a magnet link to start downloading."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def list_torrents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        torrents = QB.torrents_info()
        if not torrents:
            await update.message.reply_text("No torrents found.")
            return

        message = "📋 **Active Torrents:**\n\n"
        for t in torrents[:10]:
            # Simple state mapping
            state = t.state.lower()
            emoji = '⬇️' if 'download' in state else '⏸️' if 'paused' in state else '✅'
            
            message += (
                f"{emoji} `{t.name[:40]}`\n"
                f"Progress: **{t.progress * 100:.1f}%** | Hash: `{t.hash[:6]}`\n\n"
            )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if is_magnet_link(text):
        try:
            QB.torrents_add(urls=text)
            await asyncio.sleep(1.5)  # Wait for QB to register
            
            torrents = QB.torrents_info(sort='added_on', reverse=True)
            t = torrents[0]
            
            keyboard = [
                [InlineKeyboardButton("⏸️ Pause", callback_data=f"pause_{t.hash}")],
                [InlineKeyboardButton("☁️ Upload to MEGA", callback_data=f"mega_{t.hash}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ **Added Torrent**\nName: `{t.name}`", 
                reply_markup=reply_markup, 
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding: {e}")
    else:
        await update.message.reply_text("❌ Please send a valid magnet link.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, thash = query.data.split('_', 1)
    
    try:
        if action == 'pause':
            QB.torrents_pause(torrent_hashes=thash)
            await query.edit_message_text(f"⏸️ Torrent `{thash[:6]}` paused.", parse_mode='Markdown')
        
        elif action == 'mega':
            # Check if download is actually finished
            torrent = QB.torrents_info(torrent_hashes=thash)[0]
            if torrent.progress < 1.0:
                await query.message.reply_text("⚠️ Download is not 100% complete yet!")
                return

            await query.edit_message_text("☁️ *Uploading to MEGA...* (This may take a while)", parse_mode='Markdown')
            
            # Use run_in_executor to keep the bot from freezing
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, sync_upload_to_mega, thash)
            
            await query.message.reply_text(result)

    except Exception as e:
        await query.message.reply_text(f"❌ Callback Error: {e}")

# --- MAIN ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_torrents))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot started. Polling...")
    application.run_polling()

if __name__ == '__main__':
    main()