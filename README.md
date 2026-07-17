# 📚 StudyIQ Daily Newsletter Agent

An automated pipeline that monitors the **StudyIQ Education YouTube channel** daily, extracts short-form videos (9–24 minutes), fetches their transcripts, summarises them in English using an LLM, and delivers a beautifully formatted HTML email digest — every night at **11 PM IST**, hands-free.

---

## Table of Contents

- [Overview](#overview)
- [Workflow Diagram](#workflow-diagram)
- [Step-by-Step Breakdown](#step-by-step-breakdown)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Setup Guide](#setup-guide)
- [Environment Variables](#environment-variables)
- [GitHub Actions](#github-actions)
- [Cost Breakdown](#cost-breakdown)
- [Troubleshooting](#troubleshooting)

---

## Overview

StudyIQ publishes multiple videos daily covering topics relevant to UPSC and other competitive exam preparation — Economy, Polity, Science & Tech, History, and more. This agent automatically:

1. Checks what StudyIQ uploaded **today**
2. Filters videos between **9 and 24 minutes** (long enough to have substance, short enough to summarise efficiently)
3. Fetches transcripts — even for Hindi-language videos with no captions
4. Summarises each video in **English** using Groq's LLaMA 3.3 70B
5. Sends a **formatted HTML newsletter** to one or more recipients

No manual intervention required after setup. Runs entirely for free on GitHub Actions.

---

## Workflow Diagram

<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/fb5694c5-a0d6-4de4-b81e-d83d5ad1f710" />

## Step-by-Step Breakdown

### Step 1 — Fetch Today's Videos

**File:** `agent.py` → `get_todays_videos()`  
**API used:** YouTube Data API v3 (free, ~50 quota units per run)

The function calls `youtube.search().list()` with `publishedAfter` set to midnight UTC of the current day and `channelId` set to StudyIQ's channel. This returns up to 50 video IDs.

It then calls `youtube.videos().list()` with those IDs to fetch `contentDetails` (for ISO 8601 duration) and `snippet` (for title and thumbnail). The `isodate` library parses the ISO 8601 duration into seconds.

**Filter logic:**
```
9 * 60 ≤ duration_in_seconds < 24 * 60
```

Videos outside this range are discarded. The 9-minute floor removes shorts and very brief updates. The 24-minute ceiling keeps videos that are summarisable within a single LLM call.

---

### Step 2 — Get Transcript

**File:** `agent.py` → `get_transcript()`  
**APIs used:** `youtube-transcript-api` (free) → Supadata API (fallback)

**Layer 1 — youtube-transcript-api:**  
Attempts to retrieve official captions in this order: `hi` (Hindi), `en` (English), `en-IN` (Indian English), then any available auto-generated language. Returns a dict with `text`, `lang`, and `method: "captions"`.

**Layer 2 — Supadata API:**  
If no captions are found (common for newer uploads or videos with disabled captions), the agent calls Supadata's hosted transcript endpoint. Supadata first checks for native captions and, if absent, runs its own AI transcription pipeline. Crucially, Supadata's infrastructure bypasses YouTube's bot-detection mechanisms that block requests from cloud server IP ranges like GitHub Actions.

Returns a dict with `text`, `lang`, and `method: "supadata"`.

If both layers fail, returns `{"text": "", "lang": "unknown", "method": "failed"}` and the video is noted in the newsletter as unavailable.

---

### Step 3 — Summarise

**File:** `agent.py` → `summarise()`  
**API used:** Groq API — `llama-3.3-70b-versatile` (fast inference, generous free tier)

The function builds a structured prompt. If the transcript language is Hindi, the prompt explicitly instructs the model to read and understand the Hindi content and respond in English.

The prompt requests output in a specific plain-text format with clearly labelled sections (`OVERVIEW:`, `KEY POINTS:`, `TOPIC TAGS:`) which are then parsed with Python string splitting — robust even if the model adds minor whitespace variations.

Temperature is set to `0.3` for consistent, factual output.

---

### Step 4 — Build HTML

**File:** `agent.py` → `build_html()`  
**Dependencies:** None (pure Python f-strings)

Generates a single HTML document with inline CSS (for maximum email client compatibility). Each video becomes a card with:

- A full-width thumbnail from YouTube's CDN (`thumbnails.high.url`)
- Title, duration formatted as `MM:SS`
- Topic tag pills in blue
- Overview paragraph and key points list
- A red YouTube-styled CTA button linking directly to the video

If no videos were found, a friendly "check back tomorrow" card is shown instead of an empty email.

---

### Step 5 — Send Email

**File:** `agent.py` → `send_email()`  
**Method:** Python `smtplib` with Gmail SMTP

Uses `STARTTLS` on port 587 (not SSL on 465) for maximum compatibility. Authenticates with a **Gmail App Password** — a 16-character code generated in Google Account → Security → 2-Step Verification → App passwords. Your actual Gmail login password is never used.

`EMAIL_TO` accepts a comma-separated list, so the same newsletter can be sent to multiple subscribers in one send.

---

## Project Structure

```
studyiq-newsletter/
│
├── agent.py                  # Main pipeline script
├── requirements.txt          # Python dependencies
├── .env                      # Local secrets (never commit this)
├── .gitignore                # Should include .env
│
└── .github/
    └── workflows/
        └── newsletter.yml    # GitHub Actions schedule + job definition
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Video discovery | YouTube Data API v3 | Official, reliable, free quota |
| Transcript fetch (primary) | youtube-transcript-api | Free, no API key, instant |
| Transcript fetch (fallback) | Supadata API | Works from cloud servers, AI fallback |
| Summarisation | Groq — LLaMA 3.3 70B | Fast inference, generous free tier |
| Email delivery | Python smtplib + Gmail SMTP | Zero cost, no third-party dependency |
| Automation | GitHub Actions | Free, no server, cron scheduling |
| Language | Python 3.11 | |

---

## Setup Guide

### Prerequisites

- Python 3.10 or higher
- A Google account (for YouTube API + Gmail)
- A GitHub account
- A Groq account (free at console.groq.com)
- A Supadata account (free at supadata.ai)

---

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/studyiq-newsletter.git
cd studyiq-newsletter
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get your API keys

**YouTube Data API v3**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project → Enable "YouTube Data API v3"
3. Credentials → Create credentials → API key
4. Copy the key

**Groq API**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up → API Keys → Create key
3. Copy the key (free tier is generous)

**Supadata API**
1. Go to [supadata.ai](https://supadata.ai)
2. Sign up → Dashboard → API Keys
3. Copy the key (100 free credits/month, no card required)

**Gmail App Password**
1. Google Account → Security → 2-Step Verification (enable if not on)
2. Scroll to "App passwords" → Generate for "Mail"
3. Copy the 16-character code

### 4. Create your `.env` file

```env
YOUTUBE_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
SUPADATA_API_KEY=supa_...
EMAIL_FROM=you@gmail.com
EMAIL_TO=recipient@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_PASS=xxxx xxxx xxxx xxxx
```

### 5. Test locally

```bash
python agent.py
```

You should see logs like:
```
Fetching today's StudyIQ videos...
Found 3 video(s) under 24 min.
  Summarising: India GDP Growth Explained
  Summarising: Article 370 Verdict Simplified
  Summarising: Science & Tech Current Affairs
Newsletter sent to recipient@example.com
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `YOUTUBE_API_KEY` | ✅ | YouTube Data API v3 key from Google Cloud Console |
| `GROQ_API_KEY` | ✅ | Groq API key for LLaMA 3.3 70B summarisation |
| `SUPADATA_API_KEY` | ✅ | Supadata key for fallback transcript fetching |
| `EMAIL_FROM` | ✅ | Gmail address used as sender |
| `EMAIL_TO` | ✅ | Recipient address(es), comma-separated |
| `SMTP_PASS` | ✅ | Gmail App Password (16-char, not your login password) |
| `SMTP_HOST` | ❌ | Default: `smtp.gmail.com` |
| `SMTP_PORT` | ❌ | Default: `587` |

---

## GitHub Actions

The workflow lives at `.github/workflows/newsletter.yml` and runs automatically every day at **11 PM IST** (5:30 PM UTC).

```yaml
name: StudyIQ Daily Newsletter

on:
  schedule:
    - cron: '30 17 * * *'   # 11:00 PM IST (UTC+5:30)
  workflow_dispatch:          # Manual trigger via GitHub UI

jobs:
  send-newsletter:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install --no-cache-dir -r requirements.txt

      - name: Run agent
        env:
          YOUTUBE_API_KEY:   ${{ secrets.YOUTUBE_API_KEY }}
          GROQ_API_KEY:      ${{ secrets.GROQ_API_KEY }}
          SUPADATA_API_KEY:  ${{ secrets.SUPADATA_API_KEY }}
          EMAIL_FROM:        ${{ secrets.EMAIL_FROM }}
          EMAIL_TO:          ${{ secrets.EMAIL_TO }}
          SMTP_PASS:         ${{ secrets.SMTP_PASS }}
        run: python agent.py
```

### Adding secrets to GitHub

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add each variable from the table above as a separate secret. The workflow reads them at runtime — they are never exposed in logs.

### Manual trigger

To run the workflow immediately without waiting for the schedule:

Repo → **Actions** tab → **StudyIQ Daily Newsletter** → **Run workflow** button (top right)

---

## Cost Breakdown

For a typical day with 3–5 videos:

| Service | Usage | Cost |
|---|---|---|
| YouTube Data API v3 | ~60 quota units/day (free limit: 10,000) | **$0** |
| youtube-transcript-api | Unlimited | **$0** |
| Supadata API | 0–5 credits/day (free: 100/month) | **$0** (free tier) |
| Groq — LLaMA 3.3 70B | ~5,000 tokens/video × 5 videos | **$0** (free tier) |
| Gmail SMTP | 1 email/day | **$0** |
| GitHub Actions | ~2 min/day (free limit: 2,000 min/month) | **$0** |
| **Total** | | **$0/month** |

If you scale beyond the free tiers (e.g. more subscribers, more channels), Supadata paid plans start at $17/month and Groq pay-as-you-go is a fraction of a cent per video.

---

## Troubleshooting

**"No videos found today"**  
StudyIQ may not have uploaded any videos in the 9–24 min range today. The newsletter still sends with a "check back tomorrow" message. You can widen the duration filter in `agent.py` by adjusting `MIN_DURATION` and `MAX_DURATION`.

**"Transcript not available" in newsletter**  
Both youtube-transcript-api and Supadata failed for a video. This is rare. Check that your `SUPADATA_API_KEY` is valid and you haven't exhausted your monthly credits.

**GitHub Actions workflow not triggering**  
GitHub occasionally delays cron schedules by up to 30 minutes under heavy load. You can always trigger it manually via the Actions tab. Also confirm the workflow file is on the `main` branch.

**Gmail authentication error**  
Make sure you're using an **App Password**, not your Google login password. App passwords are generated at Google Account → Security → 2-Step Verification → App passwords. 2-Step Verification must be enabled first.

**Groq rate limit error**  
The free tier has generous limits but can throttle under burst load. If you're processing many videos in quick succession, add a small `time.sleep(1)` between `summarise()` calls in the `main()` loop.

**YouTube quota exceeded**  
The free YouTube Data API quota is 10,000 units/day. A single run uses ~60 units, so you'd need to run the script ~166 times in a day to hit the limit. This should never happen under normal use.

---

## Requirements

```
google-api-python-client
youtube-transcript-api
groq
supadata
isodate
python-dotenv
requests
```

---

*Built for UPSC & competitive exam aspirants. Runs entirely on free tiers.*
