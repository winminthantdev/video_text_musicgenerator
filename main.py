from fastapi import FastAPI
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import textwrap

app = FastAPI(title="TikTok Auto Video API (Optional Text & Dynamic Audio)")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# Made text_content default to an empty string so it's optional
class VideoPayload(BaseModel):
    text_content: str = ""
    background_video: str = "background.mp4"
    audio_track: str = "music.m4a"  # Defaulting to your m4a preference


@app.get("/")
def home():
    return {"status": "API is running!"}


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
        y_text = (image_height / 2) - 100

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
        print(f"Error creating text image: {e}")
        return None


@app.post("/generate-video")
def generate_video(payload: VideoPayload):
    bg_path = os.path.join(PROJECT_DIR, payload.background_video)
    audio_path = os.path.join(PROJECT_DIR, payload.audio_track)
    font_path = os.path.join(PROJECT_DIR, "Pyidaungsu.ttf")
    output_filename = os.path.join(PROJECT_DIR, "output.mp4")

    if not os.path.exists(bg_path):
        return {"status": "error", "message": f"Background video not found: {bg_path}"}
    if not os.path.exists(audio_path):
        return {"status": "error", "message": f"Audio track not found: {audio_path}"}

    duration = get_audio_duration(audio_path)

    # Check if user provided any text (ignores just spaces/newlines)
    has_text = bool(payload.text_content.strip())
    text_image_path = None

    if has_text:
        # IF TEXT EXISTS: Create image and overlay it
        if not os.path.exists(font_path):
            return {"status": "error", "message": f"Font file not found: {font_path}"}

        text_image_path = create_text_image(payload.text_content, font_path)
        if not text_image_path:
            return {"status": "error", "message": "Failed to create text overlay image."}

        command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", bg_path,  # Input 0: Video
            "-i", text_image_path,  # Input 1: Image
            "-i", audio_path,  # Input 2: Audio
            "-t", str(duration),
            "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=repeat[v]",
            "-map", "[v]",
            "-map", "2:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            output_filename
        ]
    else:
        # IF NO TEXT: Just combine looping video and audio
        command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", bg_path,  # Input 0: Video
            "-i", audio_path,  # Input 1: Audio
            "-t", str(duration),
            "-map", "0:v:0",  # Take video from Input 0
            "-map", "1:a:0",  # Take audio from Input 1
            "-c:v", "libx264",
            "-c:a", "aac",
            output_filename
        ]

    try:
        mode = "with text overlay" if has_text else "without text overlay"
        print(f"Starting Video Generation ({mode}) for duration: {duration} seconds")

        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            return {"status": "error", "message": "FFmpeg Failed", "details": result.stderr}

        # Clean up temp image if it was created
        if text_image_path and os.path.exists(text_image_path):
            os.remove(text_image_path)

        return {
            "status": "success",
            "message": f"Video generated successfully {mode}!",
            "video_url": output_filename
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}