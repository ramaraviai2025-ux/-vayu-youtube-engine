import asyncio
import edge_tts
import requests
import json
import os
import sys
import random
import re
from moviepy.editor import (
    VideoFileClip, AudioFileClip, TextClip,
    CompositeVideoClip, concatenate_videoclips,
    ColorClip, ImageClip
)

# ============================================
# SETTINGS
# ============================================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
VOICE = "hi-IN-MadhurNeural"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# ============================================
# STEP 1: GENERATE VOICE (FREE - Edge TTS)
# ============================================
async def generate_voice(text):
    print("🎙️ Generating voiceover...")
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate="+5%"
    )
    await communicate.save("voiceover.mp3")
    print("✅ Voiceover saved!")
    return "voiceover.mp3"

# ============================================
# STEP 2: DOWNLOAD VIDEOS FROM PEXELS (FREE)
# ============================================
def download_pexels_videos(query, count=4):
    print(f"📥 Searching Pexels for: {query}")
    headers = {"Authorization": PEXELS_API_KEY}
    
    # Clean up query - keep it simple
    clean_query = re.sub(r'[^a-zA-Z\s]', '', query)
    words = clean_query.split()[:3]
    search_term = " ".join(words)
    
    url = f"https://api.pexels.com/videos/search?query={search_term}&per_page={count}&orientation=portrait"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"⚠️ Pexels error: {response.status_code}")
        # Try a generic fallback search
        url = f"https://api.pexels.com/videos/search?query=technology&per_page={count}&orientation=portrait"
        response = requests.get(url, headers=headers)
    
    data = response.json()
    videos = data.get("videos", [])
    
    if not videos:
        print("⚠️ No videos found, using fallback")
        url = f"https://api.pexels.com/videos/search?query=computer coding&per_page={count}&orientation=portrait"
        response = requests.get(url, headers=headers)
        data = response.json()
        videos = data.get("videos", [])
    
    paths = []
    for i, video in enumerate(videos):
        video_files = video.get("video_files", [])
        # Pick a good quality file
        chosen = None
        for vf in video_files:
            h = vf.get("height", 0)
            w = vf.get("width", 0)
            if h >= 720 and h <= 1920:
                chosen = vf
                break
        if not chosen and video_files:
            chosen = video_files[0]
        
        if chosen:
            video_url = chosen["link"]
            path = f"stock_{i}.mp4"
            print(f"  ⬇️ Downloading video {i+1}...")
            r = requests.get(video_url, stream=True)
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            paths.append(path)
    
    print(f"✅ Downloaded {len(paths)} videos")
    return paths

# ============================================
# STEP 3: BUILD THE YOUTUBE SHORT VIDEO
# ============================================
def make_video(audio_path, video_paths, title, sentences):
    print("🎬 Building video...")
    
    audio = AudioFileClip(audio_path)
    total_duration = audio.duration
    print(f"  Audio duration: {total_duration:.1f} seconds")
    
    if not video_paths:
        print("  Using color background (no stock videos)")
        bg = ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(10, 10, 30),
            duration=total_duration
        )
        video_clips = [bg]
    else:
        clip_duration = total_duration / len(video_paths)
        video_clips = []
        
        for i, vpath in enumerate(video_paths):
            try:
                clip = VideoFileClip(vpath)
                
                # Resize to fill the frame
                aspect = clip.w / clip.h
                target_aspect = VIDEO_WIDTH / VIDEO_HEIGHT
                
                if aspect > target_aspect:
                    # Video is wider - resize by height
                    clip = clip.resize(height=VIDEO_HEIGHT)
                else:
                    # Video is taller - resize by width
                    clip = clip.resize(width=VIDEO_WIDTH)
                
                # Crop to exact size
                x1 = max(0, (clip.w - VIDEO_WIDTH) // 2)
                y1 = max(0, (clip.h - VIDEO_HEIGHT) // 2)
                clip = clip.crop(
                    x1=x1, y1=y1,
                    width=min(VIDEO_WIDTH, clip.w),
                    height=min(VIDEO_HEIGHT, clip.h)
                )
                
                # Handle duration
                if clip.duration >= clip_duration:
                    start = random.uniform(0, max(0, clip.duration - clip_duration))
                    clip = clip.subclip(start, start + clip_duration)
                else:
                    # Loop if too short
                    loops = int(clip_duration / clip.duration) + 1
                    clip = concatenate_videoclips([clip] * loops)
                    clip = clip.subclip(0, clip_duration)
                
                clip = clip.without_audio()
                video_clips.append(clip)
                
            except Exception as e:
                print(f"  ⚠️ Error with {vpath}: {e}")
                fallback = ColorClip(
                    size=(VIDEO_WIDTH, VIDEO_HEIGHT),
                    color=(10, 10, 30),
                    duration=clip_duration
                )
                video_clips.append(fallback)
    
    # Join all clips
    main_video = concatenate_videoclips(video_clips, method="compose")
    main_video = main_video.subclip(0, total_duration)
    
    # Create subtitle text clips
    text_clips = []
    
    # Title at the top (first 4 seconds)
    try:
        title_clip = (TextClip(
            title[:45],
            fontsize=44,
            color='white',
            font='DejaVu-Sans-Bold',
            size=(VIDEO_WIDTH - 100, None),
            method='caption',
            stroke_color='black',
            stroke_width=2
        )
        .set_position(('center', 180))
        .set_start(0)
        .set_duration(min(4, total_duration)))
        text_clips.append(title_clip)
    except Exception as e:
        print(f"  ⚠️ Title text error: {e}")
    
    # Subtitles at bottom
    if sentences:
        sent_duration = total_duration / len(sentences)
        for i, sent in enumerate(sentences):
            if not sent.strip():
                continue
            try:
                sub = (TextClip(
                    sent.strip()[:80],
                    fontsize=38,
                    color='yellow',
                    font='DejaVu-Sans-Bold',
                    size=(VIDEO_WIDTH - 140, None),
                    method='caption',
                    stroke_color='black',
                    stroke_width=2
                )
                .set_position(('center', VIDEO_HEIGHT - 400))
                .set_start(i * sent_duration)
                .set_duration(sent_duration))
                text_clips.append(sub)
            except:
                pass
    
    # Combine everything
    final = CompositeVideoClip(
        [main_video] + text_clips,
        size=(VIDEO_WIDTH, VIDEO_HEIGHT)
    )
    final = final.set_audio(audio)
    final = final.set_duration(total_duration)
    
    # Save
    output_path = "final_short.mp4"
    final.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        audio_codec='aac',
        bitrate='4000k',
        preset='ultrafast',
        threads=2
    )
    
    print(f"✅ Video created: {output_path}")
    
    # Cleanup
    audio.close()
    final.close()
    
    return output_path

# ============================================
# STEP 4: UPLOAD TO YOUTUBE
# ============================================
def upload_youtube(video_path, title, description):
    print("📤 Uploading to YouTube...")
    
    creds_json = os.environ.get("YOUTUBE_CREDENTIALS", "")
    if not creds_json:
        print("❌ No YouTube credentials! Skipping upload.")
        print("✅ Video saved as final_short.mp4")
        return None
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        creds_data = json.loads(creds_json)
        credentials = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret")
        )
        
        youtube = build("youtube", "v3", credentials=credentials)
        
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": ["AI", "Tech", "News", "Hinglish", 
                         "Artificial Intelligence"],
                "categoryId": "28"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }
        
        media = MediaFileUpload(video_path, mimetype="video/mp4",
                                resumable=True)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = request.execute()
        vid_id = response["id"]
        print(f"🎉 UPLOADED! https://youtube.com/shorts/{vid_id}")
        return vid_id
        
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return None

# ============================================
# MAIN - RUNS EVERYTHING
# ============================================
async def main():
    # Get data from environment variables
    script = os.environ.get("SCRIPT_TEXT", "")
    title = os.environ.get("VIDEO_TITLE", "AI News Today")
    search_query = os.environ.get("SEARCH_QUERY", "artificial intelligence")
    
    if not script:
        print("❌ No script text found!")
        sys.exit(1)
    
    print("=" * 50)
    print("🚀 VAYU YOUTUBE ENGINE")
    print("=" * 50)
    print(f"📝 Title: {title}")
    print(f"📝 Script preview: {script[:80]}...")
    print()
    
    # Split script into sentences
    sentences = [s.strip() for s in script.replace("।", ".")
                 .replace("!", ".").replace("?", ".").split(".") 
                 if s.strip() and len(s.strip()) > 5]
    
    # 1. Voice
    audio_path = await generate_voice(script)
    
    # 2. Stock videos
    video_paths = download_pexels_videos(search_query, count=4)
    
    # 3. Make video
    video_file = make_video(audio_path, video_paths, title, sentences)
    
    # 4. Upload
    description = f"{title}\n\n#AI #Tech #News #Hinglish #Shorts"
    upload_youtube(video_file, title, description)
    
    print("\n✅ ALL DONE!")

if __name__ == "__main__":
    asyncio.run(main())
