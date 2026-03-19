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

hard_subtitle = None

# =========================
# Setup
# =========================
os.makedirs("Downloads", exist_ok=True)

if debug:
    import logging
    logging.basicConfig(level=level)

def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        print("Command failed:", cmd)
        print(e)
        exit()

auth = CrunchyrollAuth()

if use_account:
    if Email == "" or Password == "":
        print("Please enter your email and password in config.py file")
        exit()
    vid_token = auth.get_user_token(Email, Password)
    if not vid_token:
        print("Login failed")
        exit()
else:
    vid_token = auth.get_guest_token()

crunchyroll = Crunchyroll(vid_token)

video_url = input("Enter the Crunchyroll video URL: ")

# =========================
# SINGLE MODE
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
    # Quality
    # =========================
    print("Select the video quality:")
    for i, video in enumerate(video_list):
        print(f"{i+1}. {video['height']}p")

    try:
        video = video_list[int(input("Enter choice: ")) - 1]
    except:
        print("Invalid selection")
        exit()

    # =========================
    # Audio
    # =========================
    print("Select audio:")
    for i, v in enumerate(video_info['versions']):
        print(f"{i+1}) {locale_map.get(v['audio_locale'], v['audio_locale'])}")

    audio_input = input("Enter (1,2,...): ")

    try:
        audio_indexes = [int(x.strip()) - 1 for x in audio_input.split(",")]
    except:
        print("Invalid audio input")
        exit()

    selected_audios = []
    for i in audio_indexes:
        if i < 0 or i >= len(video_info['versions']):
            print("Invalid audio index")
            exit()

        v = video_info['versions'][i]
        selected_audios.append({
            "audio_locale": locale_map.get(v['audio_locale'], v['audio_locale']),
            "guid": v['guid']
        })

    # =========================
    # KEYS
    # =========================
    license_data = CrunchyrollLicense().get_license(pssh, token, vid_id, vid_token)["key"]
    keys = [f"{i['kid_hex']}:{i['key_hex']}" for i in license_data]

    # =========================
    # AUDIO SEGMENTS
    # =========================
    for audio in selected_audios:
        info = crunchyroll.get_video_info(audio['guid'])
        pssh, mpd, token = crunchyroll.get_pssh(info)

        lic = CrunchyrollLicense().get_license(pssh, token, audio['guid'], vid_token)["key"]
        audio['key'] = f"{lic[0]['kid_hex']}:{lic[0]['key_hex']}"

        _, alist = parse_mpd_content(mpd)

        if not alist:
            print("No audio stream found")
            exit()

        best = max(alist, key=lambda x: x['bandwidth'])
        audio['segment'] = get_segment_link_list(mpd, best['name'], best['base_url'])

    # =========================
    # SUBTITLES
    # =========================
    selected_subtitles = []

    tracks = []

    if 'captions' in video_info:
        for lang, data in video_info['captions'].items():
            tracks.append({
                "type": "caption",
                "language": lang,
                "url": data['url'],
                "format": data['format']
            })

    if 'subtitles' in video_info:
        for lang, data in video_info['subtitles'].items():
            if lang != "none" and 'url' in data:
                tracks.append({
                    "type": "subtitle",
                    "language": lang,
                    "url": data['url'],
                    "format": data['format']
                })

    if tracks:
        print("Available subtitles:")
        for i, t in enumerate(tracks):
            print(f"{i+1}. {t['language']} ({t['type']})")

        sub_input = input("Select subtitles (or press Enter to skip): ").strip()

        if sub_input:
            try:
                indexes = [int(x.strip()) - 1 for x in sub_input.split(",")]
                for i in indexes:
                    t = tracks[i]
                    selected_subtitles.append({
                        "language": locale_map.get(t['language'], t['language']),
                        "url": t['url'],
                        "format": t['format'],
                        "type": t['type']
                    })
            except:
                print("Invalid subtitle input")
                exit()

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

    print("Downloading video...")
    download_segment(vidseg["all"], "enc_" + Title, "mp4")

    print("Downloading audio...")
    for audio in selected_audios:
        download_segment(audio['segment']["all"], f"enc_{Title}_{audio['audio_locale']}", "m4a")

    # =========================
    # SUB DOWNLOAD
    # =========================
    for sub in selected_subtitles:
        filename = f"{Title}_{sub['language']}.{sub['format']}"
        run_cmd(f"curl {shlex.quote(sub['url'])} -o {shlex.quote(filename)}")

        if sub['format'] == "vtt":
            new_file = filename.replace(".vtt", ".srt")
            convert_vtt_to_srt_custom(filename, new_file)
            os.remove(filename)
            sub['format'] = "srt"

    # =========================
    # DECRYPT
    # =========================
    print("Decrypting video...")
    key_args = " ".join([f"--key {k}" for k in keys])
    run_cmd(f"./mp4decrypt Downloads/enc_{Title}.mp4 {Title}.mp4 {key_args}")

    print("Decrypting audio...")
    for audio in selected_audios:
        loc = audio['audio_locale']
        run_cmd(f"./mp4decrypt Downloads/enc_{Title}_{loc}.m4a {Title}_{loc}.m4a --key {audio['key']}")

    # =========================
    # MERGE
    # =========================
    cmd = f"{ffmpeg_path} -y -i {shlex.quote(Title+'.mp4')}"

    for audio in selected_audios:
        cmd += f" -i {shlex.quote(Title+'_'+audio['audio_locale']+'.m4a')}"

    for sub in selected_subtitles:
        cmd += f" -i {shlex.quote(Title+'_'+sub['language']+'.'+sub['format'])}"

    cmd += " -map 0:v"

    for i in range(len(selected_audios)):
        cmd += f" -map {i+1}:a"

    for i in range(len(selected_subtitles)):
        cmd += f" -map {len(selected_audios)+i+1}:s"

    output = f"{Title}.{video['height']}p.mkv"

    cmd += f" -c:v {encoding_code} -c:a {audio_codec} -c:s copy {shlex.quote(output)}"

    print("Merging...")
    run_cmd(cmd)

    # =========================
    # CLEANUP
    # =========================
    os.remove(f"{Title}.mp4")

    for audio in selected_audios:
        os.remove(f"{Title}_{audio['audio_locale']}.m4a")

    for sub in selected_subtitles:
        os.remove(f"{Title}_{sub['language']}.{sub['format']}")

    print("Done ✅")
