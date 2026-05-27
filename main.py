from fastapi import FastAPI
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import textwrap

app = FastAPI(title="TikTok Auto Video API (Subtitles Support)")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


class VideoPayload(BaseModel):
    text_content: str = ""
    background_video: str = "background.mp4"
    audio_track: str = "music.m4a"
    subtitle_file: str = ""


@app.get("/")
def home():
    return {"status": "API is running with Subtitle capabilities!"}


def get_audio_duration(audio_path):
    try:
        command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting audio duration: {e}")
        return 10.0


def create_text_image(text, font_path, image_width=1080, image_height=1920):
    try:
        img = Image.new('RGBA', (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, 60)
        lines = textwrap.wrap(text, width=25)
        y_text = (image_height / 2) - 150

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            x_text = (image_width - line_width) / 2

            stroke_width = 3
            draw.text((x_text, y_text), line, font=font, fill="black", stroke_width=stroke_width, stroke_fill="black")
            draw.text((x_text, y_text), line, font=font, fill="white")

            y_text += line_height + 20

        output_path = "temp_text.png"
        img.save(os.path.join(PROJECT_DIR, output_path))
        return output_path
    except Exception as e:
        print(f"Error creating text image: {e}")
        return None


@app.post("/generate-video")
def generate_video(payload: VideoPayload):
    abs_bg = os.path.join(PROJECT_DIR, payload.background_video)
    abs_audio = os.path.join(PROJECT_DIR, payload.audio_track)
    abs_font = os.path.join(PROJECT_DIR, "Pyidaungsu.ttf")

    if not os.path.exists(abs_bg):
        return {"status": "error", "message": f"Background video not found: {abs_bg}"}
    if not os.path.exists(abs_audio):
        return {"status": "error", "message": f"Audio track not found: {abs_audio}"}

    has_sub = bool(payload.subtitle_file.strip())
    if has_sub:
        abs_sub = os.path.join(PROJECT_DIR, payload.subtitle_file)
        if not os.path.exists(abs_sub):
            return {"status": "error", "message": f"Subtitle file not found: {abs_sub}"}

    duration = get_audio_duration(abs_audio)
    has_text = bool(payload.text_content.strip())


    command = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", payload.background_video]

    if has_text:
        create_text_image(payload.text_content, abs_font)
        command.extend(["-i", "temp_text.png"])

    command.extend(["-i", payload.audio_track, "-t", str(duration)])

    sub_style = "Fontname=Zawgyi-One,Fontsize=22,Outline=1,Alignment=2"
    filter_complex = ""

    if has_text and has_sub:
        filter_complex = f"[0:v][1:v]overlay=0:0:eof_action=repeat[vbg];[vbg]subtitles={payload.subtitle_file}:force_style='{sub_style}'[v]"
    elif has_text:
        filter_complex = "[0:v][1:v]overlay=0:0:eof_action=repeat[v]"
    elif has_sub:
        filter_complex = f"[0:v]subtitles={payload.subtitle_file}:force_style='{sub_style}'[v]"

    if filter_complex:
        command.extend(["-filter_complex", filter_complex, "-map", "[v]"])
    else:
        command.extend(["-map", "0:v:0"])

    audio_idx = "2:a:0" if has_text else "1:a:0"
    command.extend(["-map", audio_idx, "-c:v", "libx264", "-c:a", "aac", "output.mp4"])

    try:
        print(f"Generating video... Text: {has_text}, Subtitles: {has_sub}")

        result = subprocess.run(command, capture_output=True, text=True, cwd=PROJECT_DIR)

        if result.returncode != 0:
            return {"status": "error", "message": "FFmpeg Failed", "details": result.stderr}

        # ရှင်းလင်းရေး
        temp_img = os.path.join(PROJECT_DIR, "temp_text.png")
        if os.path.exists(temp_img):
            os.remove(temp_img)

        return {
            "status": "success",
            "message": f"Video generated successfully! (Duration: {duration}s)",
            "video_url": os.path.join(PROJECT_DIR, "output.mp4")
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}