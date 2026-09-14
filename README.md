# DONIAWIK V2 — Video Quality Engine

A polished local-first video optimizer UI inspired by modern creator tools, with an original DONIAWIK design.

## What V2 does
- Drag/drop video upload
- STABLE and MAXIMUM processing modes
- Automatic source analysis
- NVIDIA NVENC detection with CPU fallback
- H.264 video + AAC 48 kHz audio
- Fast-start MP4 output
- Live progress and engine status
- Before/after file information
- Animated particle background
- No cloud upload: processing runs on the computer hosting Flask/FFmpeg

## Run on Windows
1. Install Python 3.10+.
2. Install FFmpeg and confirm `ffmpeg -version` works in Command Prompt.
3. Open Command Prompt in this folder.
4. Run `python -m pip install -r requirements.txt`.
5. Run `python app.py`.
6. Open `http://127.0.0.1:5000`.

## Important
This is V2 of the local engine, not a production public SaaS deployment. For a public launch, replace Flask's development server with a production WSGI server and add authentication/quotas, rate limits, durable job storage, isolated workers, cleanup policies, HTTPS, monitoring and stronger upload validation.

DONIAWIK does not bypass or interfere with TikTok's security, anti-abuse systems, upload restrictions, or server-side transcoding.
