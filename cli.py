print("Hello Welcome to Crunchyroll Downloader")

from crunchyroll import (
    Crunchyroll, CrunchyrollAuth, CrunchyrollLicense,
    parse_mpd_content, get_segment_link_list,
    download_segment, get_filter_complex,
    convert_vtt_to_srt_custom
)

import re
import os
import shlex
import subprocess
from config import *

# =========================
# Setup
# =========================
os.makedirs("Downloads", exist_ok=True)

if debug:
    import logging
    logging.basicConfig(level=level)

auth = CrunchyrollAuth()

if use_account:
    if not Email or not Password:
        print("Enter Email/Password in config.py")
        exit()
    vid_token = auth.get_user_token(Email, Password)
else:
    vid_token = auth.get_guest_token()

crunchyroll = Crunchyroll(vid_token)

video_url = input("Enter URL: ")

# =========================
# Helper Functions
# =========================
def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError:
        print("Command failed:", cmd)
        exit()

def get_keys(license_data):
    return [f"{i['kid_hex']}:{i['key_hex']}" for i in license_data]

# =========================
# SINGLE VIDEO MODE
# =========================
if "watch" in video_url:

    match = re.search(r'https?://www\.crunchyroll\.com/watch/([^/]+)', video_url)
    if not match:
        print("Invalid URL")
        exit()

    vid_id = match.group(1)

    video_info = crunchyroll.get_video_info(vid_id)
    if not video_info:
        print("Video not found")
        exit()

    single_info = crunchyroll.get_single_info(vid_id)

    pssh, mpd_content, token = crunchyroll.get_pssh(video_info)
    video_list, audio_list = parse_mpd_content(mpd_content)

    # =========================
    # Quality Select
    # =========================
    print("Select Quality:")
    for i, v in enumerate(video_list):
        print(f"{i+1}. {v['height']}p")

    video = video_list[int(input("Choice: ")) - 1]

    # =========================
    # Audio Select
    # =========================
    print("Select Audio:")
    for i, v in enumerate(video_info['versions']):
        print(f"{i+1}. {locale_map.get(v['audio_locale'], v['audio_locale'])}")

    choices = input("Enter (1,2,...): ")
    selected = [int(x.strip()) - 1 for x in choices.split(",")]

    selected_audios = []
    for i in selected:
        version = video_info['versions'][i]
        selected_audios.append({
            "audio_locale": locale_map.get(version['audio_locale'], version['audio_locale']),
            "guid": version['guid']
        })

    # =========================
    # KEYS
    # =========================
    license_keys = get_keys(
        CrunchyrollLicense().get_license(pssh, token, vid_id, vid_token)["key"]
    )

    # =========================
    # AUDIO SEGMENTS
    # =========================
    for audio in selected_audios:
        info = crunchyroll.get_video_info(audio['guid'])
        pssh, mpd, token = crunchyroll.get_pssh(info)

        keys = get_keys(
            CrunchyrollLicense().get_license(pssh, token, audio['guid'], vid_token)["key"]
        )
        audio['key'] = keys[0]

        vlist, alist = parse_mpd_content(mpd)
        best = max(alist, key=lambda x: x['bandwidth'])
        audio['segment'] = get_segment_link_list(mpd, best['name'], best['base_url'])

    # =========================
    # TITLE
    # =========================
    meta = single_info["data"][0]["episode_metadata"]

    Title = f"{meta['season_title']}.S{str(meta['season_number']).zfill(2)}E{str(meta['episode_number']).zfill(2)}-{single_info['data'][0]['title']}"
    Title = re.sub(r'[<>:"/\\|?*]', '', Title)

    # =========================
    # DOWNLOAD
    # =========================
    vidseg = get_segment_link_list(mpd_content, video['name'], video['base_url'])

    print("Downloading Video...")
    download_segment(vidseg["all"], "enc_" + Title, "mp4")

    print("Downloading Audio...")
    for audio in selected_audios:
        download_segment(audio['segment']["all"], f"enc_{Title}_{audio['audio_locale']}", "m4a")

    # =========================
    # DECRYPT
    # =========================
    print("Decrypting Video...")
    key_args = " ".join([f"--key {k}" for k in license_keys])

    run_cmd(f"./mp4decrypt Downloads/enc_{Title}.mp4 {Title}.mp4 {key_args}")

    for audio in selected_audios:
        loc = audio['audio_locale']
        run_cmd(f"./mp4decrypt Downloads/enc_{Title}_{loc}.m4a {Title}_{loc}.m4a --key {audio['key']}")

    # =========================
    # MERGE
    # =========================
    cmd = f"{ffmpeg_path} -y -i {shlex.quote(Title+'.mp4')}"

    for audio in selected_audios:
        cmd += f" -i {shlex.quote(Title+'_'+audio['audio_locale']+'.m4a')}"

    cmd += " -map 0:v"

    for i in range(len(selected_audios)):
        cmd += f" -map {i+1}:a"

    output = f"{Title}.{video['height']}p.mkv"
    cmd += f" -c:v copy -c:a copy {shlex.quote(output)}"

    print("Merging...")
    run_cmd(cmd)

    # =========================
    # CLEANUP
    # =========================
    os.remove(f"{Title}.mp4")

    for audio in selected_audios:
        os.remove(f"{Title}_{audio['audio_locale']}.m4a")

    print("Done ✅")

# =========================
# SERIES MODE (BASIC FIXED)
# =========================
elif "series" in video_url:

    print("Batch Mode")

    data, _ = crunchyroll.get_content_info(url=video_url)

    if not data:
        print("Series not found")
        exit()

    episodes = data['data']

    count = int(input("How many episodes: "))

    for i in range(count):
        print(f"Downloading Episode {i+1}")

        ep_id = episodes[i]['id']
        os.system(f"python main.py")  # simple reuse (optional improve later)

else:
    print("Invalid URL")
