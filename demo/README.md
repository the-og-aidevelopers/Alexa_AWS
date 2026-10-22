# Demo video

Two ways to make it. Neither output is tracked by git (`demo/out/`).

**Quick version (`make_video.py`)** records the app with captions and a computer voice in one pass.
No extra tools beyond Playwright, Kokoro and ffmpeg. About 2 minutes.

**Polished version** uses [claude-code-video-toolkit](https://github.com/digitalsamba/claude-code-video-toolkit)
(Remotion): motion graphics, burned word-by-word captions, an Echo concept scene, and the AWS plan.
The Remotion project is a copy of the toolkit's `product-demo` template kept outside this repo
(default `~/Documents/projects/video-toolkit-src/projects/family-dose-check`, override with `VIDEO_PROJECT`).

```bash
python demo/make_narration.py    # voice + word-timed captions for each scene
python demo/make_footage.py      # records the real app at 1440x810 (own server, temporary data)
python demo/make_timeline.py     # scene lengths, chapter times, spoken-word cues -> timeline.ts
cd <video project> && npx remotion render FamilyDoseCheck out/family-dose-check.mp4 --crf=16
```

`video_script.py` holds the narration text. The AWS slide labels what is in the code today (Bedrock,
Cognito, both opt-in) separately from the deployment plan (EC2/Fargate, DynamoDB, EventBridge
Scheduler, SNS with Alexa+, Transcribe, Textract with S3). Keep that split honest if the code changes.
