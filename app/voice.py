"""Voice: speak the agent's answer with Amazon Polly while it is still being written.

Waiting for the whole answer before speaking feels slow, so we cut the streamed text into sentences
and send each finished sentence to Polly in the background. The audio clips come back in order and
the browser plays them one after another, so speech starts a second or two after the first words.

Polly has three "engines". "generative" sounds the most natural (it is the least robotic), "neural"
is a good fallback, and "standard" is the old robotic one. If a voice does not support the engine we
ask for, speak() quietly falls back to neural.
"""
import base64
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

POLLY_MAX_CHARS = 2900      # Polly accepts up to 3000 characters per request
MIN_SENTENCE_CHARS = 25     # speak very short sentences together with the next one, so the voice keeps its flow
DEFAULT_VOICE = "Ruth"
DEFAULT_ENGINE = "generative"


@lru_cache(maxsize=None)
def polly_client(region: str):
    """One client per region, reused for every sentence (creating a client is slow)."""
    return boto3.client("polly", region_name=region)


def clean_for_speech(text: str) -> str:
    """Remove things that sound strange when read aloud: markdown marks, emoji, 'B+' read as 'B plus'."""
    text = re.sub(r"[*_#`>]", "", text)                                       # markdown emphasis, headings, code
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)               # bullet points
    text = re.sub(r"\b([A-DF])\+(?!\w)", r"\1 plus", text)                    # grades: B+ -> B plus
    text = re.sub(r"\b([A-DF])-(?!\w)", r"\1 minus", text)                    # grades: A- -> A minus
    text = "".join(c for c in text if unicodedata.category(c) != "So" and c not in "️‍")  # emoji
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r" ?\n ?", "\n", text).strip()


class SentenceSplitter:
    """Collect streamed text and hand back whole sentences as soon as they are complete."""

    def __init__(self):
        self.buffer = ""   # text of the sentence that is still being written
        self.carry = ""    # a finished but very short sentence, waiting to be joined with the next one

    def feed(self, chunk: str) -> list[str]:
        self.buffer += chunk
        parts = re.split(r"(?<=[.!?:])\s+|\n+", self.buffer)
        self.buffer = parts.pop()  # the last part may be unfinished
        ready = []
        for part in parts:
            self.carry = f"{self.carry} {part}".strip()
            if len(self.carry) >= MIN_SENTENCE_CHARS:
                ready.append(self.carry)
                self.carry = ""
        return ready

    def flush(self) -> list[str]:
        """The answer is finished: return whatever text is left."""
        rest = f"{self.carry} {self.buffer}".strip()
        self.buffer = self.carry = ""
        return [rest] if rest else []


def speak(text: str, voice: str = DEFAULT_VOICE, region: str = "us-east-1", engine: str = DEFAULT_ENGINE) -> bytes:
    """Turn text into MP3 bytes with Amazon Polly. Falls back to the neural engine if needed."""
    text = clean_for_speech(text)[:POLLY_MAX_CHARS]
    engines = list(dict.fromkeys([engine, "neural"]))
    for index, name in enumerate(engines):
        try:
            response = polly_client(region).synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice, Engine=name)
            return response["AudioStream"].read()
        except ClientError as error:
            wrong_engine = error.response["Error"]["Code"] in ("ValidationException", "InvalidParameterException")
            if not wrong_engine or index == len(engines) - 1:
                raise
    raise RuntimeError("unreachable")


class StreamingSpeaker:
    """Feed it the answer as it streams in; it returns audio clips, in order, as they become ready."""

    def __init__(self, voice: str, region: str, engine: str = DEFAULT_ENGINE):
        self.voice, self.region, self.engine = voice, region, engine
        self.splitter = SentenceSplitter()
        self.pool = ThreadPoolExecutor(max_workers=3)  # synthesize later sentences while the browser plays the first
        polly_client(region)  # create the client now, so the first sentence doesn't pay for it
        self.pending = []  # futures, in sentence order
        self.error = None  # the first Polly error, so the app can show it once instead of crashing the chat

    def _submit(self, sentences: list[str]) -> None:
        for sentence in sentences:
            self.pending.append(self.pool.submit(speak, sentence, self.voice, self.region, self.engine))

    def _next_clip(self) -> bytes | None:
        """Take the oldest sentence's audio off the queue (waits until it is ready), or None if Polly failed."""
        try:
            return self.pending.pop(0).result()
        except Exception as error:  # noqa: BLE001 - speech is a bonus: never break the chat because of it
            self.error = self.error or error
            return None

    def feed(self, chunk: str) -> list[bytes]:
        """Give it the next piece of the answer. Returns the clips that are ready right now (often none)."""
        self._submit(self.splitter.feed(chunk))
        clips = []
        while self.pending and self.pending[0].done():  # keep sentence order: stop at the first unfinished one
            clip = self._next_clip()
            if clip:
                clips.append(clip)
        return clips

    def finish(self):
        """The answer is complete. Yields the remaining clips one by one, each as soon as it is ready,
        so the browser can start playing the next sentence without waiting for the last one."""
        self._submit(self.splitter.flush())
        while self.pending:
            clip = self._next_clip()
            if clip:
                yield clip
        self.pool.shutdown()


def player_html(clips: list[bytes]) -> str:
    """A tiny invisible page that adds clips to the browser's playback queue and starts playing.

    Each Streamlit component lives in its own iframe, but the queue lives in the main page (window.parent),
    so clips from different iframes play one after another instead of on top of each other.
    """
    urls = ",".join('"data:audio/mpeg;base64,' + base64.b64encode(clip).decode() + '"' for clip in clips)
    return """<script>
(function () {
  var page = window.parent;
  var tts = page.__studyTts = page.__studyTts || {queue: [], current: null};
  function playNext() {
    if (tts.current || tts.queue.length === 0) { return; }
    var audio = new page.Audio(tts.queue.shift());
    tts.current = audio;
    var next = function () { tts.current = null; playNext(); };
    audio.onended = next;
    audio.onerror = next;
    audio.play().catch(next);
  }
  [%s].forEach(function (url) { tts.queue.push(url); });
  playNext();
})();
</script>""" % urls


def stop_html() -> str:
    """Silence anything still playing or queued (used when the student sends a new message)."""
    return """<script>
(function () {
  var tts = window.parent.__studyTts;
  if (!tts) { return; }
  tts.queue = [];
  if (tts.current) { tts.current.pause(); tts.current = null; }
})();
</script>"""
