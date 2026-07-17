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

load_dotenv()

YT_API_KEY   = os.environ["YOUTUBE_API_KEY"]
CHANNEL_ID   = "UCrC8mOqJQpoB7NuIMKIS6rQ"  # StudyIQ Education
GROQ_KEY = os.environ["GROQ_API_KEY"]
EMAIL_FROM   = os.environ["EMAIL_FROM"]
EMAIL_TO     = os.environ["EMAIL_TO"]         # comma-separated for many recipients
SMTP_HOST    = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", 587))
# SUPADATA_KEY = os.environ["SUPADATA_API_KEY"]
SUPADATA_KEYS = [
    os.environ["SUPADATA_API_KEY_1"],
    os.environ["SUPADATA_API_KEY_2"],
]
SMTP_PASS    = os.environ["SMTP_PASS"]
MIN_DURATION = 9 * 60      # 9 minute in seconds
MAX_DURATION = 24 * 60  # 24 minutes in seconds
PROMO_KEYWORDS = [
    "batch",
    "course",
    "foundation",
    "admission",
    "enroll",
    "enrol",
    "registration",
    "launch",
    "offer",
    "discount",
    "scholarship",
    "webinar",
    "masterclass",
    "orientation",
    "demo",
    "free class",
    "strategy session",
    "test series",
    "mock test",
    "answer writing",
    "mentorship",
    "join now",
    "limited seats",
]

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
youtube = build("youtube", "v3", developerKey=YT_API_KEY)

def is_promotional(title: str) -> bool:
    title = title.lower()
    return any(keyword in title for keyword in PROMO_KEYWORDS)


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
    for item in details.get("items", []):
        content = item.get("contentDetails", {})
        title = item["snippet"]["title"]

        if is_promotional(title):
            print(f"Skipping promotional video: {title}")
            continue
        dur_iso = content.get("duration")
    
        if not dur_iso:
            print(f"Skipping video {item.get('id')} because duration is missing.")
            print(item)
            continue
    
        dur_secs = isodate.parse_duration(dur_iso).total_seconds()
    
        if MIN_DURATION <= dur_secs < MAX_DURATION:
            results.append({
                "id": item["id"],
                "title": title,
                "url": f"https://youtu.be/{item['id']}",
                "duration": int(dur_secs),
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
            })
    return results

def get_transcript(video_id: str) -> dict:
    """
    Fetches transcript via Supadata API.
    - Tries native captions (Hindi/English) first — 1 credit
    - Falls back to AI-generated transcription if no captions — still 1 credit
    - Works from any server including GitHub Actions
    """
    url = "https://api.supadata.ai/v1/youtube/transcript"
    for key in SUPADATA_KEYS:
        try:
            resp = requests.get(
                url,
                headers={"x-api-key": key},
                params={
                    "videoId": video_id,
                    "text": "true",
                },
                timeout=30,
            )

            # If quota is exhausted, try the next key
            if resp.status_code in (402, 429):
                print(f"Supadata quota exhausted for key: {key[:8]}...")
                continue

            resp.raise_for_status()

            data = resp.json()

            text = data.get("content", "")
            lang = data.get("lang", "unknown")

            if text.strip():
                return {
                    "text": text,
                    "lang": lang,
                    "method": "supadata",
                }

        except Exception as e:
            print(f"Supadata failed: {e}")

    return {
        "text": "",
        "lang": "unknown",
        "method": "failed",
    }
    

def fmt_duration(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"


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
