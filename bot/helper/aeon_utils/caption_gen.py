import json
import os
import re
from contextlib import suppress
from hashlib import md5

from aiofiles.os import path as aiopath
from langcodes import Language

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)


class DefaultDict(dict):
    def __missing__(self, key):
        return "Unknown"

import re
import os

def clean_filename(filename):
    # Remove file extension
    name, _ = os.path.splitext(filename)

    # Match movie name and year (capture text before the year)
    match = re.search(r"(.+?)\s+(\d{4})\b", name)  # Extract movie name & year
    if match:
        movie_name = match.group(1).strip()
        movie_year = match.group(2)
        return f"{movie_name} ({movie_year})"  # Format as "Movie Name (Year)"
    
    # Fallback if no match
    return name

    
async def generate_caption(filename, directory, caption_template):
    file_path = os.path.join(directory, filename)

    try:
        result = await cmd_exec(["mediainfo", "--Output=JSON", file_path])
        if result[1]:
            LOGGER.info(f"MediaInfo command output: {result[1]}")

        mediainfo_data = json.loads(result[0])  # Parse JSON output
    except Exception as error:
        LOGGER.error(f"Failed to retrieve media info: {error}. File may not exist!")
        return filename

    media_data = mediainfo_data.get("media", {})
    track_data = media_data.get("track", [])
    video_metadata = next(
        (track for track in track_data if track["@type"] == "Video"),
        {},
    )
    audio_metadata = [track for track in track_data if track["@type"] == "Audio"]
    subtitle_metadata = [track for track in track_data if track["@type"] == "Text"]

    video_duration = round(float(video_metadata.get("Duration", 0)))
    video_quality = get_video_quality(video_metadata.get("Height"))

    audio_languages = ", ".join(
        parse_audio_language("", audio)
        for audio in audio_metadata
        if audio.get("Language")
    )
    subtitle_languages = ", ".join(
        parse_subtitle_language("", subtitle)
        for subtitle in subtitle_metadata
        if subtitle.get("Language")
    )

    audio_languages = audio_languages if audio_languages else "Unknown"
    subtitle_languages = subtitle_languages if subtitle_languages else "-"
    video_quality = video_quality if video_quality else "Unknown"
    file_md5_hash = calculate_md5(file_path)

    caption_data = DefaultDict(
        filename=clean_filename(filename),  # Processed filename
        size=get_readable_file_size(await aiopath.getsize(file_path)),
        duration=get_readable_time(video_duration, True),
        quality=video_quality,
        audios=audio_languages,
        subtitles=subtitle_languages,
        md5_hash=file_md5_hash,
    )

    return caption_template.format_map(caption_data)


def get_video_quality(height):
    quality_map = {
        272: "LQ/360p",
        360: "SD/480p",
        540: "HD/720p",
        799: "HD/720p",  # Anything below 800px is still 720p
        1080: "FHD/1080p",  # Includes 800px cropped 1080p videos
        2160: "QHD/2160p",
        4320: "UHD/4320p",
        8640: "FUHD/8640p",
    }

    for threshold, quality in sorted(quality_map.items()):
        if height and int(height) <= threshold:
            return quality

    return "Unknown"



def parse_audio_language(existing_languages, audio_stream):
    language_code = audio_stream.get("Language")
    if language_code:
        with suppress(Exception):
            language_name = Language.get(language_code).display_name()
            if language_name not in existing_languages:
                LOGGER.debug(f"Parsed audio language: {language_name}")
                existing_languages += f"{language_name}, "
    return existing_languages.strip(", ")


def parse_subtitle_language(existing_subtitles, subtitle_stream):
    subtitle_code = subtitle_stream.get("Language")
    if subtitle_code:
        with suppress(Exception):
            subtitle_name = Language.get(subtitle_code).display_name()
            if subtitle_name not in existing_subtitles:
                LOGGER.debug(f"Parsed subtitle language: {subtitle_name}")
                existing_subtitles += f"{subtitle_name}, "
    return existing_subtitles.strip(", ")


def calculate_md5(file_path):
    md5_hash = md5()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()
