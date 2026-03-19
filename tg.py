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

def run(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True)
    except:
        print("Command failed:", cmd)
        exit()

# =========================
# AUTH
# =========================
auth = CrunchyrollAuth()

if use_account:
    if Email == "" or Password == "":
        print("Enter Email & Password in config.py")
        exit()
    vid_token = auth.get_user_token(Email, Password)
    if not vid_token:
        print("Invalid login")
        exit()
else:
    vid_token = auth.get_guest_token()

crunchyroll = Crunchyroll(vid_token)

video_url = input("Enter Crunchyroll URL: ")

# =========================
# SINGLE MODE
# =========================
if "watch" in video_url:

    match = re.search(r'https://www\.crunchyroll\.com/watch/([^/]+)', video_url)
    if not match:
        print("Invalid URL")
        exit()

    vid_id = match.group(1)

    video_info = crunchyroll.get_video_info(vid_id)
    if not video_info:
        print("Video not found")
        exit()

    single = crunchyroll.get_single_info(vid_id)

    pssh, mpd, token = crunchyroll.get_pssh(video_info)
    vlist, alist = parse_mpd_content(mpd)

    # QUALITY
    print("Select Quality:")
    for i, v in enumerate(vlist):
        print(f"{i+1}. {v['height']}p")

    video = vlist[int(input("Choice: ")) - 1]

    # AUDIO
    print("Select Audio:")
    for i, v in enumerate(video_info['versions']):
        print(f"{i+1}. {locale_map.get(v['audio_locale'], v['audio_locale'])}")

    audio_input = input("Enter (1,2): ")
    audio_indexes = [int(x.strip()) - 1 for x in audio_input.split(",")]

    selected_audios = []
    for i in audio_indexes:
        v = video_info['versions'][i]
        selected_audios.append({
            "audio_locale": locale_map.get(v['audio_locale'], v['audio_locale']),
            "guid": v['guid']
        })

    # KEYS
    lic = CrunchyrollLicense().get_license(pssh, token, vid_id, vid_token)["key"]
    key = f"{lic[0]['kid_hex']}:{lic[0]['key_hex']}"

    # AUDIO SEGMENTS
    for audio in selected_audios:
        info = crunchyroll.get_video_info(audio['guid'])
        pssh, mpd2, token = crunchyroll.get_pssh(info)

        lic = CrunchyrollLicense().get_license(pssh, token, audio['guid'], vid_token)["key"]
        audio['key'] = f"{lic[0]['kid_hex']}:{lic[0]['key_hex']}"

        v2, a2 = parse_mpd_content(mpd2)
        best = max(a2, key=lambda x: x['bandwidth'])
        audio['segment'] = get_segment_link_list(mpd2, best['name'], best['base_url'])

    # SUBTITLES
    selected_subtitles = []
    tracks = []

    if 'subtitles' in video_info:
        for lang, data in video_info['subtitles'].items():
            if lang != "none":
                tracks.append({
                    "language": lang,
                    "url": data['url'],
                    "format": data['format']
                })

    if tracks:
        print("Subtitles:")
        for i, t in enumerate(tracks):
            print(f"{i+1}. {t['language']}")

        sub_input = input("Select: ")
        idxs = [int(x.strip()) - 1 for x in sub_input.split(",")]

        for i in idxs:
            t = tracks[i]
            selected_subtitles.append({
                "language": locale_map.get(t['language'], t['language']),
                "url": t['url'],
                "format": t['format']
            })

    # TITLE
    meta = single["data"][0]["episode_metadata"]

    Title = f"{meta['season_title']}.S{str(meta['season_number']).zfill(2)}E{str(meta['episode_number']).zfill(2)}-{single['data'][0]['title']}"
    Title = re.sub(r'[<>:"/\\|?*]', '', Title)

    # DOWNLOAD
    vidseg = get_segment_link_list(mpd, video['name'], video['base_url'])

    print("Downloading video...")
    download_segment(vidseg["all"], "enc_" + Title, "mp4")

    print("Downloading audio...")
    for audio in selected_audios:
        download_segment(audio['segment']["all"], f"enc_{Title}_{audio['audio_locale']}", "m4a")

    # SUB DOWNLOAD
    for sub in selected_subtitles:
        filename = f"{Title}_{sub['language']}.{sub['format']}"
        run(f"curl {shlex.quote(sub['url'])} -o {shlex.quote(filename)}")

        if sub['format'] == "vtt":
            convert_vtt_to_srt_custom(filename, filename.replace(".vtt", ".srt"))
            os.remove(filename)
            sub['format'] = "srt"

    # DECRYPT
    print("Decrypting video...")
    run(f"./mp4decrypt Downloads/enc_{Title}.mp4 {Title}.mp4 --key {key}")

    print("Decrypting audio...")
    for audio in selected_audios:
        loc = audio['audio_locale']
        run(f"./mp4decrypt Downloads/enc_{Title}_{loc}.m4a {Title}_{loc}.m4a --key {audio['key']}")

    # MERGE
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
    run(cmd)

    # CLEANUP
    os.remove(f"{Title}.mp4")

    for audio in selected_audios:
        os.remove(f"{Title}_{audio['audio_locale']}.m4a")

    for sub in selected_subtitles:
        os.remove(f"{Title}_{sub['language']}.{sub['format']}")

    print("DONE ✅")

else:
    print("Batch mode not fixed in this version ❌")
