"""The words of the demo video and the project the video is built in (shared by the build scripts)."""
from __future__ import annotations

import os
from pathlib import Path

# The Remotion project (a copy of the toolkit's product-demo template) lives outside this repository.
PROJECT = Path(os.environ.get(
    "VIDEO_PROJECT",
    Path.home() / "Documents/projects/video-toolkit-src/projects/family-dose-check",
))
PUBLIC = PROJECT / "public"

SCENES = [
    # id, kind, narration
    ("title", "title", "About half of all prescriptions are taken incorrectly. Family Dose Check helps a family get it right."),
    ("solution", "solution", "It is a spoken household medicine log for Alexa Plus. A caregiver sets it up, anyone can talk to it, and the whole family shares one record."),
    ("setup", "app", "A caregiver creates a private household, adds the people they care for, and each person's medicines, with the times and days."),
    ("voice", "app", "Anyone can also just say it. The speech is transcribed, and the right action is chosen."),
    ("chat", "app", "Ask what is due. Say a dose was taken, and the record updates. Ask how the day went, or change and remove medicines, all in plain words."),
    ("family", "app", "One household connects the whole family. Anyone can log anyone's dose, and everyone sees the same record."),
    ("reminder", "app", "Ten minutes before a dose, the app announces it. Here Mom's metformin is added for ten minutes from now, and the reminder appears and is spoken."),
    ("echo", "echo", "With Alexa Plus connected, the same reminder is spoken on the Echo in the kitchen, so nobody has to open an app. This part is a concept for now."),
    ("aws", "aws", "We use AWS for more than hosting. In the code today, Amazon Bedrock can understand the sentence and choose the action, and Amazon Cognito can sign the family in. For deployment, the server runs on EC2 or Fargate, DynamoDB keeps the households and the dose log, EventBridge Scheduler fires each reminder ten minutes ahead, SNS and Alexa Plus deliver it, and Transcribe turns speech into text. Textract and S3 will read a photo of a prescription."),
    ("future", "future", "Next: a photo of a prescription or a pill box adds the medicines automatically, more family members join the same household with their own sign-in, and reminders reach every Echo."),
    ("close", "close", "Family Dose Check. A household log you can hear. It does not give medical advice."),
]

VOICE_LINE = "Raj needs to take dopamine at 8 AM and 8 PM."
