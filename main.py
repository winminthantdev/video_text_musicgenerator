from fastapi import FastAPI, UploadFile, File, Form
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import textwrap
import shutil

app = FastAPI(title="TikTok Auto Video API (n8n File Upload Version)")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def home():
    return {"status": "API is ready to receive files from n8n!"}


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

        output_path = os.path.join(PROJECT_DIR, "temp_text.png")
        img.save(output_path)
        return output_path
    except Exception as e:
        return None


# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
@app.post("/generate-video")
async def generate_video(
        text_content: str = Form(""),
        background_video: UploadFile = File(...),
        audio_track: UploadFile = File(...),
        subtitle_file: UploadFile = File(None)  # Optional
):
    bg_path = os.path.join(PROJECT_DIR, f"temp_{background_video.filename}")
    with open(bg_path, "wb") as buffer:
        shutil.copyfileobj(background_video.file, buffer)

    audio_path = os.path.join(PROJECT_DIR, f"temp_{audio_track.filename}")
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio_track.file, buffer)

    sub_path = None
    has_sub = False
    if subtitle_file and subtitle_file.filename:
        has_sub = True
        sub_path = os.path.join(PROJECT_DIR, f"temp_{subtitle_file.filename}")
        with open(sub_path, "wb") as buffer:
            shutil.copyfileobj(subtitle_file.file, buffer)

    font_path = os.path.join(PROJECT_DIR, "Pyidaungsu.ttf")
    output_filename = os.path.join(PROJECT_DIR, "output.mp4")
    duration = get_audio_duration(audio_path)
    has_text = bool(text_content.strip())

    # FFmpeg Command
    command = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", bg_path]

    text_image_path = None
    if has_text:
        text_image_path = create_text_image(text_content, font_path)
        command.extend(["-i", text_image_path])

    command.extend(["-i", audio_path, "-t", str(duration)])

    sub_style = "Fontname=Pyidaungsu,Fontsize=22,Outline=1,Alignment=2"
    filter_complex = ""

    if has_text and has_sub:
        filter_complex = f"[0:v][1:v]overlay=0:0:eof_action=repeat[vbg];[vbg]subtitles={sub_path}:force_style='{sub_style}'[v]"
    elif has_text:
        filter_complex = "[0:v][1:v]overlay=0:0:eof_action=repeat[v]"
    elif has_sub:
        filter_complex = f"[0:v]subtitles={sub_path}:force_style='{sub_style}'[v]"

    if filter_complex:
        command.extend(["-filter_complex", filter_complex, "-map", "[v]"])
    else:
        command.extend(["-map", "0:v:0"])

    audio_idx = "2:a:0" if has_text else "1:a:0"
    command.extend(["-map", audio_idx, "-c:v", "libx264", "-c:a", "aac", output_filename])

    try:
        print(f"Generating video... Text: {has_text}, Subtitles: {has_sub}")
        result = subprocess.run(command, capture_output=True, text=True, cwd=PROJECT_DIR)

        if result.returncode != 0:
            return {"status": "error", "message": "FFmpeg Failed", "details": result.stderr}

        return {
            "status": "success",
            "message": "Video generated successfully!",
            "video_url": output_filename
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        if os.path.exists(bg_path): os.remove(bg_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        if sub_path and os.path.exists(sub_path): os.remove(sub_path)
        if text_image_path and os.path.exists(text_image_path): os.remove(text_image_path)