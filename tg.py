# =========================
# GLOBAL STATES
# =========================
user_states = {}
active_downloads = {}

# =========================
# DOWNLOAD COMMAND
# =========================
@app.on_message(filters.command(["download", "dl"]))
@check_active_download
def download_command(client, message: Message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        return message.reply_text(
            "❌ URL do bhai\nExample:\n/download https://crunchyroll.com/watch/..."
        )

    video_url = message.command[1].strip()
    status_msg = message.reply_text("⏳ Processing URL...")

    user_states[user_id] = {
        "step": "initial",
        "url": video_url,
        "data": {},
        "message": status_msg,
        "is_series": False
    }

    try:
        if "watch" not in video_url and "series" not in video_url:
            edit_message(status_msg, "❌ Invalid URL")
            user_states.pop(user_id, None)
            return

        edit_message(status_msg, "✅ URL OK\nProcessing...")

        # 👉 Aage tumhara main Crunchyroll logic continue hoga

    except Exception as e:
        edit_message(status_msg, f"❌ Error: {e}")
        user_states.pop(user_id, None)


# =========================
# SUBTITLE SELECTION (FIXED)
# =========================
def ask_subtitles(client, user_id):
    if user_id not in user_states:
        return

    state = user_states[user_id]
    status_msg = state["message"]
    video_info = state["data"].get("video_info", {})

    available_tracks = []
    track_info_list = []

    def add_track(lang, data, track_type):
        try:
            if not isinstance(data, dict):
                return

            if lang == "none":
                return

            url = data.get("url")
            if not url:
                return

            label_prefix = "[CC]" if track_type == 'caption' else "[SUB]"
            lang_display = locale_map.get(lang, lang)

            available_tracks.append(f"{label_prefix} {lang_display}")

            track_info_list.append({
                'type': track_type,
                'language': lang,
                'url': url,
                'format': data.get('format', 'vtt'),
                'display_name': lang_display
            })

        except Exception as e:
            print("Subtitle error:", e)

    # captions safe
    for lang, data in (video_info.get('captions') or {}).items():
        add_track(lang, data, 'caption')

    # subtitles safe
    for lang, data in (video_info.get('subtitles') or {}).items():
        add_track(lang, data, 'subtitle')

    if not track_info_list:
        edit_message(status_msg, "⚠️ No subtitles found, continuing...")
        state["data"]["selected_subtitles"] = []
        state["step"] = "confirm_download"
        confirm_download(client, user_id)
        return

    state["data"]["selected_subtitles"] = []
    state["data"]["available_subtitle_options"] = track_info_list

    buttons = []
    for i, track in enumerate(track_info_list):
        buttons.append([
            InlineKeyboardButton(
                available_tracks[i],
                callback_data=f"sub_{i}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("✅ Done", callback_data="sub_done"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ])

    state["step"] = "select_subtitles"

    edit_message(
        status_msg,
        "🎬 Select subtitles:",
        keyboard=InlineKeyboardMarkup(buttons)
    )


# =========================
# TEXT INPUT HANDLER (FIXED)
# =========================
@app.on_message(filters.text & filters.private)
def handle_text_reply(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_states:
        return

    state = user_states[user_id]

    # 👉 Episode count input
    if state.get("step") == "ask_episode_count":
        try:
            count = int(message.text.strip())

            total = state["data"].get("total_episodes", 0)

            if count <= 0 or count > total:
                return message.reply_text(f"❌ 1 se {total} ke beech number bhejo")

            state["data"]["episodes_to_download_count"] = count
            state["step"] = "next_step"

            message.reply_text(f"✅ {count} episodes select ho gaye")

            # 👉 Aage next step call karo
            ask_video_quality(client, user_id)

        except ValueError:
            message.reply_text("❌ Sirf number bhejo bhai")


# =========================
# SAFE MESSAGE EDIT
# =========================
def edit_message(message, text, keyboard=None):
    try:
        message.edit_text(text, reply_markup=keyboard)
    except:
        pass
