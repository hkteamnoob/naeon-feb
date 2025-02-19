import json
from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE

from bot import LOGGER, cpu_no


async def get_file_info(file):
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_format",  # Get filename and general metadata
        file,
    ]
    process = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"Error getting file info: {stderr.decode().strip()}")
        return None, None

    try:
        data = json.loads(stdout)
        format_info = data.get("format", {})

        # Extract and print the filename
        file_name = os.path.basename(format_info.get("filename", file))
        print(f"Extracted filename: {file_name}")  # Print statement for inspection

        return file_name
    except json.JSONDecodeError:
        print(f"Invalid JSON output from ffprobe: {stdout.decode().strip()}")
        return None


async def get_streams(file):
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        file,
    ]
    process = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        LOGGER.error(f"Error getting stream info: {stderr.decode().strip()}")
        return None

    try:
        return json.loads(stdout)["streams"]
    except KeyError:
        LOGGER.error(
            f"No streams found in the ffprobe output: {stdout.decode().strip()}",
        )
        return None


# TODO Lots of work need
async def get_watermark_cmd(file, key):
    temp_file = f"{file}.temp.mkv"
    font_path = "default.otf"

    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-vf",
        f"drawtext=text='{key}':fontfile={font_path}:fontsize=20:fontcolor=white:x=10:y=10",
        # "-preset",
        # "ultrafast",
        "-threads",
        f"{max(1, cpu_no // 2)}",
        temp_file,
    ]

    return cmd, temp_file


LANGUAGE_MAP = {
    "eng": "English",
    "tam": "Tamil",
    "tel": "Telugu",
    "hin": "Hindi",
    "mal": "Malayalam",
    "kan": "Kannada",
    "urd": "Urdu",
    "ben": "Bengali",
    "mar": "Marathi",
}


async def get_metadata_cmd(file_path, key):
    """Processes a single file to update metadata."""
    temp_file = f"{file_path}.temp.mkv"
    streams = await get_streams(file_path)
    await get_file_info(file_path)
    if not streams:
        return None, None

    languages = {
        stream["index"]: stream["tags"]["language"]
        for stream in streams
        if "tags" in stream and "language" in stream["tags"]
    }

    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file_path,
        "-map_metadata",
        "-1",
        "-c",
        "copy",
        "-metadata:s:v:0",
        f"title={key}",
        "-metadata",
        f"title={key}",
    ]

    audio_index = 0
    subtitle_index = 0
    first_video = False

    for stream in streams:
        stream_index = stream["index"]
        stream_type = stream["codec_type"]

        if stream_type == "video":
            if not first_video:
                cmd.extend(["-map", f"0:{stream_index}"])
                first_video = True
            cmd.extend([f"-metadata:s:v:{stream_index}", f"title={key}"])
            if stream_index in languages:
                cmd.extend(
                    [
                        f"-metadata:s:v:{stream_index}",
                        f"language={languages[stream_index]}",
                    ],
                )
        elif stream_type == "audio":
            # Convert language code to full name
            lang_code = languages.get(stream_index, "")
            lang_name = LANGUAGE_MAP.get(
                lang_code,
                lang_code,
            ).capitalize()  # Default to code if not in map
            title_value = (
                f"{lang_name}-{key}" if lang_name else key
            )  # Ensure formatting is correct

            cmd.extend(
                [
                    "-map",
                    f"0:{stream_index}",
                    f"-metadata:s:a:{audio_index}",
                    f"title={title_value}",
                ],
            )
            if lang_code:
                cmd.extend([f"-metadata:s:a:{audio_index}", f"language={lang_code}"])
            audio_index += 1

        elif stream_type == "subtitle":
            codec_name = stream.get("codec_name", "unknown")
            if codec_name in ["webvtt", "unknown"]:
                LOGGER.warning(
                    f"Skipping unsupported subtitle metadata modification: {codec_name} for stream {stream_index}",
                )
            else:
                cmd.extend(
                    [
                        "-map",
                        f"0:{stream_index}",
                        f"-metadata:s:s:{subtitle_index}",
                        f"title={key}",
                    ],
                )
                if stream_index in languages:
                    cmd.extend(
                        [
                            f"-metadata:s:s:{subtitle_index}",
                            f"language={languages[stream_index]}",
                        ],
                    )
                subtitle_index += 1
        else:
            cmd.extend(["-map", f"0:{stream_index}"])

    cmd.extend(["-threads", f"{max(1, cpu_no // 2)}", temp_file])
    return cmd, temp_file


# TODO later
async def get_embed_thumb_cmd(file, attachment_path):
    temp_file = f"{file}.temp.mkv"
    attachment_ext = attachment_path.split(".")[-1].lower()
    mime_type = "application/octet-stream"
    if attachment_ext in ["jpg", "jpeg"]:
        mime_type = "image/jpeg"
    elif attachment_ext == "png":
        mime_type = "image/png"

    cmd = [
        "xtra",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        file,
        "-attach",
        attachment_path,
        "-metadata:s:t",
        f"mimetype={mime_type}",
        "-c",
        "copy",
        "-map",
        "0",
        "-threads",
        f"{max(1, cpu_no // 2)}",
        temp_file,
    ]

    return cmd, temp_file
