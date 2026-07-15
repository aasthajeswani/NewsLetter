import os, isodate, smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
import os, tempfile, isodate,smtplib
from groq import Groq
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
import requests
# from youtube_transcript_api import YouTubeTranscriptApi
# from youtube_transcript_api.proxies import WebshareProxyConfig
# from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
# import requests

load_dotenv()

YT_API_KEY   = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID   = "UCrC8mOqJQpoB7NuIMKIS6rQ"  # StudyIQ Education
#ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GROQ_KEY = os.environ["GROQ_API_KEY"]
EMAIL_FROM   = os.environ["EMAIL_FROM"]
EMAIL_TO     = os.environ["EMAIL_TO"]         # comma-separated for many recipients
SMTP_HOST    = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", 587))
SUPADATA_KEY = os.environ["SUPADATA_API_KEY"]
SMTP_PASS    = os.environ["SMTP_PASS"]
# WEBSHARE_USER = os.environ["WEBSHARE_USER"]
# WEBSHARE_PASS = os.environ["WEBSHARE_PASS"]
MIN_DURATION = 9 * 60      # 9 minute in seconds
MAX_DURATION = 24 * 60  # 24 minutes in seconds

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
youtube = build("youtube", "v3", developerKey=YT_API_KEY)
#claude  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def get_todays_videos():
    """Return list of video dicts published today, duration < 24 min."""
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    published_after = today.isoformat().replace("+00:00", "Z")

    # Step 1: search for today's uploads on the channel
    search_resp = youtube.search().list(
        part="id",
        channelId=CHANNEL_ID,
        publishedAfter=published_after,
        type="video",
        maxResults=50,
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not video_ids:
        return []

    # Step 2: get durations via videos.list
    details = youtube.videos().list(
        part="contentDetails,snippet",
        id=",".join(video_ids),
    ).execute()

    results = []
    # for item in details.get("items", []):
    #     dur_iso  = item["contentDetails"]["duration"]
    #     dur_secs = isodate.parse_duration(dur_iso).total_seconds()
    for item in details.get("items", []):
        content = item.get("contentDetails", {})
        dur_iso = content.get("duration")
    
        if not dur_iso:
            print(f"Skipping video {item.get('id')} because duration is missing.")
            print(item)
            continue
    
        dur_secs = isodate.parse_duration(dur_iso).total_seconds()
    
        if MIN_DURATION <= dur_secs < MAX_DURATION:
            results.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "url": f"https://youtu.be/{item['id']}",
                "duration": int(dur_secs),
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
            })
        # if dur_secs < MAX_DURATION and dur_secs >= MIN_DURATION:
        #     results.append({
        #         "id":        item["id"],
        #         "title":     item["snippet"]["title"],
        #         "url":       f"https://youtu.be/{item['id']}",
        #         "duration":  int(dur_secs),
        #         "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
        #     })
    return results

def get_transcript(video_id: str) -> dict:
    """
    Fetches transcript via Supadata API.
    - Tries native captions (Hindi/English) first — 1 credit
    - Falls back to AI-generated transcription if no captions — still 1 credit
    - Works from any server including GitHub Actions
    """
    url = "https://api.supadata.ai/v1/youtube/transcript"
    headers = {"x-api-key": SUPADATA_KEY}
    params = {
        "videoId": video_id,
        "text": "true",   # returns plain string, not timestamped chunks
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # data["content"] is plain text when text=true
        text = data.get("content", "")
        lang = data.get("lang", "unknown")

        if not text:
            return {"text": "", "lang": "unknown", "method": "failed"}

        return {"text": text, "lang": lang, "method": "supadata"}

    except Exception as e:
        print(f"  Supadata transcript failed for {video_id}: {e}")
        return {"text": "", "lang": "unknown", "method": "failed"}


# def get_transcript(video_id: str) -> dict:

#     # --- Layer 1: youtube-transcript-api via Webshare residential proxy ---
#     try:
#         ytt = YouTubeTranscriptApi(
#             proxy_config=WebshareProxyConfig(
#                 proxy_username=WEBSHARE_USER,
#                 proxy_password=WEBSHARE_PASS,
#             )
#         )
#         transcript_list = ytt.list_transcripts(video_id)
#         for lang in ["hi", "en", "en-IN"]:
#             try:
#                 t = transcript_list.find_transcript([lang])
#                 chunks = t.fetch()
#                 text = " ".join(c["text"] for c in chunks)
#                 if text.strip():
#                     return {"text": text, "lang": lang, "method": "proxy-captions"}
#             except Exception:
#                 continue
#         # try any available language
#         for t in transcript_list:
#             chunks = t.fetch()
#             text = " ".join(c["text"] for c in chunks)
#             if text.strip():
#                 return {"text": text, "lang": t.language_code, "method": "proxy-captions"}
#     except Exception as e:
#         print(f"  Layer 1 failed for {video_id}: {e}")

#     # --- Layer 2: youtube-transcript.ai (free, no key, no credit limit) ---
#     try:
#         resp = requests.get(
#             f"https://youtube-transcript.ai/api/transcript/{video_id}",
#             timeout=20
#         )
#         if resp.status_code == 200:
#             data = resp.json()
#             text = " ".join(seg.get("text", "") for seg in data.get("transcript", []))
#             if text.strip():
#                 return {"text": text, "lang": data.get("lang", "unknown"), "method": "yt-transcript-ai"}
#     except Exception as e:
#         print(f"  Layer 2 failed for {video_id}: {e}")

#     # --- Layer 3: Supadata (last resort only) ---
#     try:
#         resp = requests.get(
#             "https://api.supadata.ai/v1/youtube/transcript",
#             headers={"x-api-key": SUPADATA_KEY},
#             params={"videoId": video_id, "text": "true"},
#             timeout=30
#         )
#         resp.raise_for_status()
#         data = resp.json()
#         text = data.get("content", "")
#         if text.strip():
#             return {"text": text, "lang": data.get("lang", "unknown"), "method": "supadata"}
#     except Exception as e:
#         print(f"  Layer 3 (Supadata) failed for {video_id}: {e}")

#     return {"text": "", "lang": "unknown", "method": "failed"}

# def summarise(title: str, transcript: str) -> dict:
#     """Ask Claude to return a structured summary."""
#     if not transcript:
#         return {"overview": "Transcript unavailable.", "key_points": []}

#     prompt = f"""You are an expert educational content summariser.

# Video title: {title}

# Transcript:
# {transcript[:12000]}

# Respond in JSON with exactly these keys:
# - "overview": 2-3 sentence plain-English summary of what the video covers.
# - "key_points": list of 4-6 bullet strings (each ≤ 20 words), the most important facts/concepts.
# - "topic_tags": list of 2-4 short topic labels (e.g. "Economy", "Polity", "Science & Tech").

# Return only valid JSON, no markdown fences."""

#     msg = claude.messages.create(
#         model="claude-sonnet-4-6",
#         max_tokens=1000,
#         messages=[{"role": "user", "content": prompt}],
#     )
#     import json
#     try:
#         return json.loads(msg.content[0].text)
#     except Exception:
#         return {"overview": msg.content[0].text, "key_points": [], "topic_tags": []}


def fmt_duration(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"

# def get_transcript(video_id: str) -> dict:
#     """
#     Returns {"text": "...", "lang": "hi"/"en", "method": "captions"/"whisper"}
#     Layer 1: YouTube captions (Hindi or English)
#     Layer 2: yt-dlp audio download + Groq Whisper transcription
#     """
#     # --- Layer 1: captions ---
#     try:
#         transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
#         # Try Hindi first (StudyIQ's primary language), then English
#         for lang in ["hi", "en", "en-IN"]:
#             try:
#                 t = transcript_list.find_transcript([lang])
#                 chunks = t.fetch()
#                 text = " ".join(c["text"] for c in chunks)
#                 return {"text": text, "lang": lang, "method": "captions"}
#             except Exception:
#                 continue
#         # Try any auto-generated caption
#         for t in transcript_list:
#             chunks = t.fetch()
#             text = " ".join(c["text"] for c in chunks)
#             return {"text": text, "lang": t.language_code, "method": "captions"}
#     except (TranscriptsDisabled, NoTranscriptFound):
#         pass
#     except Exception:
#         pass

#     # --- Layer 2: yt-dlp + Groq Whisper ---
#     try:
#         with tempfile.TemporaryDirectory() as tmpdir:
#             audio_path = os.path.join(tmpdir, f"{video_id}.mp3")
#             ydl_opts = {
#                 "format": "bestaudio/best",
#                 "outtmpl": os.path.join(tmpdir, f"{video_id}"),
#                 "postprocessors": [{
#                     "key": "FFmpegExtractAudio",
#                     "preferredcodec": "mp3",
#                     "preferredquality": "64",   # low bitrate = smaller file = faster upload
#                 }],
#                 "quiet": True,
#             }
#             with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#                 ydl.download([f"https://youtu.be/{video_id}"])

#             with open(audio_path, "rb") as f:
#                 result = groq_client.audio.transcriptions.create(
#                     file=(f"{video_id}.mp3", f.read()),
#                     model="whisper-large-v3-turbo",
#                     response_format="text",
#                     language="hi",   # hint: StudyIQ is primarily Hindi
#                 )
#             return {"text": str(result), "lang": "hi", "method": "whisper"}
#     except Exception as e:
#         print(f"  Whisper fallback failed for {video_id}: {e}")
#         return {"text": "", "lang": "unknown", "method": "failed"}


def summarise(title: str, transcript_data: dict) -> dict:
    text = transcript_data.get("text", "")
    lang = transcript_data.get("lang", "en")

    if not text:
        return {
            "overview": "Transcript not available.",
            "key_points": [],
            "topic_tags": []
        }

    lang_instruction = (
        "The transcript is in Hindi. Understand it and respond in English."
        if lang == "hi" else
        "Summarise the transcript in English."
    )

    prompt = f"""
You are an expert UPSC content analyst.

{lang_instruction}

Video Title:
{title}

Transcript:
{text[:5000]}

Return output in EXACT format:

OVERVIEW:
(write 2–3 clear sentences)

KEY POINTS:
- point 1
- point 2
- point 3
- point 4
- point 5
- point 6

TOPIC TAGS:
tag1, tag2, tag3
"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    content = resp.choices[0].message.content

    # --- PARSE STRUCTURED TEXT ---
    try:
        overview = content.split("OVERVIEW:")[1].split("KEY POINTS:")[0].strip()
        key_points_block = content.split("KEY POINTS:")[1].split("TOPIC TAGS:")[0]
        tags_block = content.split("TOPIC TAGS:")[1].strip()

        key_points = [
            p.strip("- ").strip()
            for p in key_points_block.strip().split("\n")
            if p.strip()
        ]

        topic_tags = [t.strip() for t in tags_block.split(",")]

        return {
            "overview": overview,
            "key_points": key_points,
            "topic_tags": topic_tags
        }

    except Exception:
        return {
            "overview": content,
            "key_points": [],
            "topic_tags": []
        }

def build_html(videos_with_summaries: list) -> str:
    date_str = datetime.now().strftime("%A, %d %B %Y")
    count = len(videos_with_summaries)

    cards = ""

    for v in videos_with_summaries:
        s = v["summary"]

        tags = "".join(
            f"""
            <span style="
                display:inline-block;
                background:#eef3ff;
                color:#2457d6;
                padding:4px 10px;
                margin:2px;
                border-radius:12px;
                font-size:12px;
                font-weight:bold;">
                {t}
            </span>
            """
            for t in s.get("topic_tags", [])
        )

        points = "".join(
            f"<li style='margin-bottom:6px;'>{p}</li>"
            for p in s.get("key_points", [])
        )

        cards += f"""
        <div style="
            background:#ffffff;
            border:1px solid #dddddd;
            border-radius:12px;
            padding:20px;
            margin-bottom:30px;">

            <img src="{v['thumbnail']}"
                 alt="Thumbnail"
                 style="width:100%;max-width:640px;border-radius:10px;">

            <h2 style="
                color:#222;
                margin-top:18px;
                margin-bottom:10px;">
                {v['title']}
            </h2>

            <p style="color:#777;font-size:14px;">
                ⏱ {fmt_duration(v['duration'])}
            </p>

            <div style="margin:12px 0;">
                {tags}
            </div>

            <p style="
                line-height:1.7;
                color:#444;
                font-size:15px;">
                {s.get("overview", "")}
            </p>

            <h4 style="margin-top:20px;">Key Points</h4>

            <ul style="
                color:#333;
                line-height:1.7;
                padding-left:22px;">
                {points}
            </ul>

            <a href="{v['url']}"
               style="
               display:inline-block;
               margin-top:15px;
               background:#ff0000;
               color:white;
               text-decoration:none;
               padding:10px 18px;
               border-radius:6px;
               font-weight:bold;">
               ▶ Watch on YouTube
            </a>

        </div>
        """

    if not cards:
        cards = """
        <div style="
            background:white;
            border-radius:10px;
            padding:30px;
            text-align:center;">
            <h2>No short videos found today.</h2>
            <p>Check back tomorrow for a new StudyIQ digest.</p>
        </div>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>StudyIQ Daily Digest</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#f4f6f8;
    font-family:Arial, Helvetica, sans-serif;">

<div style="
    max-width:800px;
    margin:30px auto;
    background:#ffffff;
    border-radius:12px;
    overflow:hidden;
    box-shadow:0 4px 12px rgba(0,0,0,0.08);">

    <div style="
        background:#0b57d0;
        color:white;
        padding:35px;
        text-align:center;">

        <h1 style="margin:0;">
            📚 StudyIQ Daily Digest
        </h1>

        <p style="margin-top:10px;font-size:16px;">
            {date_str}
        </p>

        <p style="font-size:18px;">
            {count} video{"s" if count != 1 else ""} under 24 minutes
        </p>

    </div>

    <div style="padding:30px;">
        {cards}
    </div>

    <div style="
        text-align:center;
        color:#777;
        padding:25px;
        font-size:13px;
        border-top:1px solid #eeeeee;">

        Generated automatically by the StudyIQ Newsletter Agent

    </div>

</div>

</body>
</html>
"""

def send_email(html: str, subject: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, SMTP_PASS)
        recipients = [r.strip() for r in EMAIL_TO.split(",")]
        server.sendmail(EMAIL_FROM, recipients, msg.as_string())


def main():
    print("Fetching today's StudyIQ videos...")
    videos = get_todays_videos()
    print(f"Found {len(videos)} video(s) under 24 min.")

    enriched = []
    for v in videos:
        print(f"  Summarising: {v['title']}")
        transcript = get_transcript(v["id"])
        v["summary"] = summarise(v["title"], transcript)
        enriched.append(v)

    date_str = datetime.now().strftime("%d %b %Y")
    subject  = f"StudyIQ Digest — {date_str} ({len(enriched)} videos)"
    html     = build_html(enriched)
    send_email(html, subject)
    print(f"Newsletter sent to {EMAIL_TO}")


if __name__ == "__main__":
    main()
