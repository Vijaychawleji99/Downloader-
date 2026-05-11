import telebot
import instaloader
import re
import os
import time
import sqlite3
import yt_dlp
import requests
import json
from datetime import datetime, date
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8634957040:AAEFe2GKNxA-RE3qalZL9Ogy9znlB6LFo5c"
CHANNEL_LINK = "https://t.me/viedietlooters"
CHANNEL_USERNAME = "@viedietlooters"
DAILY_LIMIT = 20

bot = telebot.TeleBot(BOT_TOKEN)

# Database setup
def setup_database():
    conn = sqlite3.connect('user_limits.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_downloads
                 (user_id INTEGER PRIMARY KEY,
                  download_date TEXT,
                  download_count INTEGER)''')
    conn.commit()
    conn.close()

setup_database()

def check_user_limit(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('user_limits.db')
    c = conn.cursor()
    c.execute("SELECT download_date, download_count FROM user_downloads WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result:
        last_date, count = result
        if last_date == today:
            if count >= DAILY_LIMIT:
                conn.close()
                return False, DAILY_LIMIT - count
            else:
                conn.close()
                return True, DAILY_LIMIT - count
        else:
            c.execute("UPDATE user_downloads SET download_date = ?, download_count = 0 WHERE user_id = ?", (today, user_id))
            conn.commit()
            conn.close()
            return True, DAILY_LIMIT
    else:
        c.execute("INSERT INTO user_downloads (user_id, download_date, download_count) VALUES (?, ?, 0)", (user_id, today))
        conn.commit()
        conn.close()
        return True, DAILY_LIMIT

def increment_user_downloads(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('user_limits.db')
    c = conn.cursor()
    c.execute("UPDATE user_downloads SET download_count = download_count + 1 WHERE user_id = ? AND download_date = ?", (user_id, today))
    conn.commit()
    conn.close()

def is_user_member(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def get_progress_bar(used, total, length=10):
    filled = int(length * used / total)
    empty = length - filled
    return "▓" * filled + "░" * empty

# Instagram downloader using instaloader with session fix
L = instaloader.Instaloader(
    save_metadata=False,
    download_comments=False,
    post_metadata_txt_pattern="",
    max_connection_attempts=3
)

# Optional: Login to Instagram for better access (uncomment if needed)
# try:
#     L.login("your_username", "your_password")
# except:
#     pass

def download_instagram(url):
    try:
        # Extract shortcode
        shortcode_match = re.search(r"instagram\.com/(?:reel|p)/([a-zA-Z0-9_-]+)", url)
        if not shortcode_match:
            return None
        shortcode = shortcode_match.group(1)
        
        print(f"Downloading Instagram post: {shortcode}")
        
        # Create temp directory
        temp_dir = f"insta_{shortcode}_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Download video
        L.download_post(post, target=temp_dir)
        
        # Find video file
        for file in os.listdir(temp_dir):
            if file.endswith(".mp4"):
                video_path = os.path.join(temp_dir, file)
                # Rename to simple name
                new_path = os.path.join(temp_dir, f"{shortcode}.mp4")
                os.rename(video_path, new_path)
                return new_path
        
        return None
        
    except Exception as e:
        print(f"Instagram Error: {e}")
        return None

# Alternative Instagram downloader using direct API (backup)
def download_instagram_api(url):
    try:
        shortcode_match = re.search(r"instagram\.com/(?:reel|p)/([a-zA-Z0-9_-]+)", url)
        if not shortcode_match:
            return None
        shortcode = shortcode_match.group(1)
        
        # Using publically available API
        api_url = f"https://instagram.com/p/{shortcode}/?__a=1&__d=1"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            video_url = None
            
            # Extract video URL from response
            if 'graphql' in data:
                shortcode_media = data['graphql']['shortcode_media']
                if shortcode_media.get('video_url'):
                    video_url = shortcode_media['video_url']
                elif shortcode_media.get('edge_sidecar_to_children'):
                    edges = shortcode_media['edge_sidecar_to_children']['edges']
                    for edge in edges:
                        if edge['node'].get('video_url'):
                            video_url = edge['node']['video_url']
                            break
            
            if video_url:
                temp_file = f"insta_{shortcode}_{int(time.time())}.mp4"
                video_response = requests.get(video_url, headers=headers, stream=True)
                
                with open(temp_file, 'wb') as f:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return temp_file
        
        return None
    except Exception as e:
        print(f"Instagram API Error: {e}")
        return None

# YouTube downloader
def download_youtube(url):
    try:
        timestamp = int(time.time())
        output_template = f"youtube_video_{timestamp}.mp4"
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'merge_output_format': 'mp4',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if os.path.exists(output_template):
                return output_template
            for file in os.listdir('.'):
                if file.startswith("youtube_video") and file.endswith(".mp4"):
                    return file
        return None
    except Exception as e:
        print(f"YouTube Error: {e}")
        return None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "User"
    
    if not is_user_member(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("✅ CHECK MEMBERSHIP", callback_data="check_membership"))
        
        welcome_text = f"""
🌟 **HI {user_name.upper()}!** 🌟

━━━━━━━━━━━━━━━━━━━━
**📱 VIEDIET LOOTERS**
*Premium Video Downloader*
━━━━━━━━━━━━━━━━━━━━

🔒 **ACCESS REQUIRED**

You need to join our channel first to use this bot!

✨ **Benefits After Joining:**
• 🎬 Download Instagram Reels
• 📥 Download YouTube Shorts/Videos
• 🎬 High Quality Videos (HD Max)
• 🎫 {DAILY_LIMIT} Free Downloads/Day
• ⚡ Fast & Secure Service

━━━━━━━━━━━━━━━━━━━━
👇 **CLICK BELOW TO JOIN** 👇
"""
        bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=markup)
        return
    
    can_download, remaining = check_user_limit(user_id)
    used = DAILY_LIMIT - remaining
    progress_bar = get_progress_bar(used, DAILY_LIMIT)
    percentage = int((used / DAILY_LIMIT) * 100)
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📸 INSTAGRAM", url="https://instagram.com"),
        InlineKeyboardButton("▶️ YOUTUBE", url="https://youtube.com")
    )
    markup.row(
        InlineKeyboardButton("📢 OUR CHANNEL", url=CHANNEL_LINK),
        InlineKeyboardButton("👤 PROFILE", callback_data="profile")
    )
    
    welcome_text = f"""
🌟 **WELCOME BACK, {user_name.upper()}!** 🌟

━━━━━━━━━━━━━━━━━━━━
**🎬 VIEDIET LOOTERS**
*Premium Video Downloader*
━━━━━━━━━━━━━━━━━━━━

📊 **YOUR DAILY STATUS**

{progress_bar} **{percentage}%**

📥 **USED:** {used}/{DAILY_LIMIT}
🎫 **REMAINING:** {remaining}

━━━━━━━━━━━━━━━━━━━━
💫 **SUPPORTED PLATFORMS:**
• **Instagram** — Reels & Videos
• **YouTube** — Shorts & Videos

━━━━━━━━━━━━━━━━━━━━
💡 **JUST SEND ME A LINK!**

*Made with ❤️ by @viedietlooters*
*{CHANNEL_USERNAME}*
"""
    bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    user_id = message.from_user.id
    if not is_user_member(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("✅ CHECK MEMBERSHIP", callback_data="check_membership"))
        bot.reply_to(message, "❌ Please join our channel first: " + CHANNEL_LINK, parse_mode="Markdown", reply_markup=markup)
        return
    
    help_text = f"""
📖 **HOW TO USE VIEDIET LOOTERS**

━━━━━━━━━━━━━━━━━━━━
🎯 **STEPS:**
━━━━━━━━━━━━━━━━━━━━

1️⃣ **Copy** Video URL (Instagram or YouTube)
2️⃣ **Paste** the link here
3️⃣ **Wait** for processing
4️⃣ **Enjoy** your HD video!

━━━━━━━━━━━━━━━━━━━━
📝 **EXAMPLE LINKS:**

**Instagram Reel:**
`https://www.instagram.com/reel/DGxQm2HzMqN/`

**Instagram Post:**
`https://www.instagram.com/p/ABC123XYZ/`

**YouTube Shorts:**
`https://youtube.com/shorts/abc123xyz`

**YouTube Video:**
`https://youtu.be/rTkD7wp3woO`

━━━━━━━━━━━━━━━━━━━━
🎫 **DAILY LIMIT:** {DAILY_LIMIT} videos
⏰ **RESETS:** Every 24 hours (Midnight)

━━━━━━━━━━━━━━━━━━━━
🔗 **OUR CHANNEL:** {CHANNEL_USERNAME}
📢 **JOIN:** {CHANNEL_LINK}

*Made with ❤️ by @viedietlooters*
"""
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    user_id = msg.from_user.id
    
    if not is_user_member(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("✅ CHECK MEMBERSHIP", callback_data="check_membership"))
        bot.reply_to(msg, "❌ **Access Denied!** Please join our channel first.", parse_mode="Markdown", reply_markup=markup)
        return
    
    can_download, remaining = check_user_limit(user_id)
    if not can_download:
        limit_text = f"""
⚠️ **DAILY LIMIT REACHED!** ⚠️

━━━━━━━━━━━━━━━━━━━━
📊 **TODAY'S USAGE:** {DAILY_LIMIT}/{DAILY_LIMIT}
⏰ **RESETS AT:** Midnight

━━━━━━━━━━━━━━━━━━━━
🔗 {CHANNEL_USERNAME}
"""
        bot.reply_to(msg, limit_text, parse_mode="Markdown")
        return
    
    url = msg.text.strip()
    
    # Check if it's Instagram or YouTube
    is_instagram = "instagram.com" in url
    is_youtube = "youtube.com" in url or "youtu.be" in url
    
    if not (is_instagram or is_youtube):
        error_text = f"""
❌ **INVALID LINK!** ❌

━━━━━━━━━━━━━━━━━━━━
✅ **Please send a valid link from:**

📸 **Instagram:** Reel or Post URL
▶️ **YouTube:** Shorts or Video URL

━━━━━━━━━━━━━━━━━━━━
📝 **Examples:**

**Instagram:** `https://www.instagram.com/reel/DGxQm2HzMqN/`

**YouTube:** `https://youtube.com/shorts/abc123`

━━━━━━━━━━━━━━━━━━━━
🔗 {CHANNEL_USERNAME}
"""
        bot.reply_to(msg, error_text, parse_mode="Markdown")
        return
    
    used = DAILY_LIMIT - remaining
    new_used = used + 1
    new_remaining = remaining - 1
    progress_bar = get_progress_bar(new_used, DAILY_LIMIT)
    percentage = int((new_used / DAILY_LIMIT) * 100)
    
    platform = "📸 INSTAGRAM" if is_instagram else "▶️ YOUTUBE"
    
    processing_msg = bot.reply_to(msg, f"""
⏳ **PROCESSING YOUR REQUEST...** ⏳

━━━━━━━━━━━━━━━━━━━━
🔍 **PLATFORM:** {platform}
🎬 **FETCHING VIDEO**

📊 **STATUS UPDATE:**
{progress_bar} **{percentage}%**

🎫 **REMAINING TODAY:** {new_remaining}/{DAILY_LIMIT}

━━━━━━━━━━━━━━━━━━━━
*Please wait while I get your video...*
""", parse_mode="Markdown")
    
    time.sleep(1)
    
    bot.edit_message_text(f"""
📥 **DOWNLOADING VIDEO** 📥

━━━━━━━━━━━━━━━━━━━━
⬇️ **FETCHING HIGH QUALITY**

🎬 **Platform:** {platform}
🎬 **Quality:** HD Max
📦 **Status:** Processing...

━━━━━━━━━━━━━━━━━━━━
*Almost there!*
""", msg.chat.id, processing_msg.message_id, parse_mode="Markdown")
    
    # Download based on platform
    file_path = None
    if is_instagram:
        file_path = download_instagram(url)
        # If first method fails, try API method
        if not file_path:
            print("Trying API method for Instagram...")
            file_path = download_instagram_api(url)
    else:
        file_path = download_youtube(url)
    
    if file_path and os.path.exists(file_path):
        bot.edit_message_text(f"""
📤 **UPLOADING VIDEO** 📤

━━━━━━━━━━━━━━━━━━━━
⬆️ **PREPARING YOUR FILE**

📊 **DAILY USAGE:**
{progress_bar} **{percentage}%**

🎫 **REMAINING:** {new_remaining}/{DAILY_LIMIT}

━━━━━━━━━━━━━━━━━━━━
*Your video is on the way!*
""", msg.chat.id, processing_msg.message_id, parse_mode="Markdown")
        
        try:
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            
            with open(file_path, "rb") as vid:
                caption_text = f"""
✅ **DOWNLOAD COMPLETE!** ✅

━━━━━━━━━━━━━━━━━━━━
📹 **VIDEO DETAILS:**
• **Platform:** {platform}
• **Quality:** HD Max
• **Size:** {file_size:.1f} MB
• **Status:** Ready

━━━━━━━━━━━━━━━━━━━━
📊 **TODAY'S USAGE:**
{progress_bar} **{percentage}%**

✅ **Used:** {new_used}/{DAILY_LIMIT}
🎫 **Remaining:** {new_remaining}

━━━━━━━━━━━━━━━━━━━━
💫 *Thanks for using VIEDIET LOOTERS!*

*Made with ❤️ by*
*{CHANNEL_USERNAME}*
"""
                
                bot.send_video(msg.chat.id, vid, caption=caption_text, parse_mode="Markdown")
                increment_user_downloads(user_id)
                bot.delete_message(msg.chat.id, processing_msg.message_id)
                
        except Exception as e:
            bot.edit_message_text(f"""
❌ **UPLOAD FAILED!** ❌

━━━━━━━━━━━━━━━━━━━━
😕 Couldn't send the video.
Please try again!

🔗 {CHANNEL_USERNAME}
""", msg.chat.id, processing_msg.message_id, parse_mode="Markdown")
            print(f"Upload error: {e}")
        
        # Cleanup
        try:
            os.remove(file_path)
            # Clean up directory if exists
            dir_name = os.path.dirname(file_path)
            if dir_name and os.path.exists(dir_name) and dir_name != '.':
                import shutil
                shutil.rmtree(dir_name)
        except:
            pass
              
    else:
        error_text = f"""
❌ **DOWNLOAD FAILED!** ❌

━━━━━━━━━━━━━━━━━━━━
**POSSIBLE REASONS:**
• Invalid or private video
• Broken URL link
• Network issue
• Platform restrictions

━━━━━━━━━━━━━━━━━━━━
**💡 SOLUTIONS:**
• Check the link is correct
• Make sure video is public
• Try again in a few minutes
• For private Instagram, video must be public

━━━━━━━━━━━━━━━━━━━━
🔗 {CHANNEL_USERNAME}
"""
        bot.edit_message_text(error_text, msg.chat.id, processing_msg.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "check_membership":
        if is_user_member(call.from_user.id):
            bot.answer_callback_query(call.id, "✅ Access Granted! Send /start again")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            send_welcome(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Still not a member! Please join our channel first.", show_alert=True)
    
    elif call.data == "profile":
        user_id = call.from_user.id
        can_download, remaining = check_user_limit(user_id)
        used = DAILY_LIMIT - remaining
        progress_bar = get_progress_bar(used, DAILY_LIMIT)
        percentage = int((used / DAILY_LIMIT) * 100)
        
        profile_text = f"""
👤 **YOUR PROFILE**

━━━━━━━━━━━━━━━━━━━━
📊 **DAILY STATISTICS**

{progress_bar} **{percentage}%**

📥 **DOWNLOADS USED:** {used}/{DAILY_LIMIT}
🎫 **REMAINING:** {remaining}

━━━━━━━━━━━━━━━━━━━━
💎 **PLAN:** Free Premium
⏰ **RESETS:** Midnight

━━━━━━━━━━━━━━━━━━━━
🔗 {CHANNEL_USERNAME}
"""
        bot.answer_callback_query(call.id)
        bot.edit_message_text(profile_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")

print("╔════════════════════════════════════════╗")
print("║     🎬 VIEDIET LOOTERS BOT ONLINE       ║")
print("╠════════════════════════════════════════╣")
print("║  ✅ Bot is running successfully        ║")
print("║  📡 Waiting for messages...            ║")
print("║  🟢 Service Active                     ║")
print("║  💎 Premium Interface Loaded           ║")
print("║  🔗 Channel: @viedietlooters          ║")
print("║  🎫 Daily Limit: 20 videos/user        ║")
print("║  📸 Instagram + ▶️ YouTube Support     ║")
print("║  🔧 Instagram Downloader FIXED         ║")
print("╚════════════════════════════════════════╝")

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"⚠️ Connection error: {e}")
        print("🔄 Restarting bot in 5 seconds...")
        time.sleep(5)