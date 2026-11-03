"""Tests for app/voice.py: text clean-up, sentence splitting and the speaking pipeline (Polly faked)."""
import io
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import voice  # noqa: E402


def test_clean_for_speech_removes_markdown_emoji_and_reads_grades_naturally():
    text = "**Great job!** 🎉\n- You need a B+ or an A- in OS\n- Final: 90%"
    assert voice.clean_for_speech(text) == "Great job!\nYou need a B plus or an A minus in OS\nFinal: 90%"


def test_grade_words_are_left_alone():
    assert voice.clean_for_speech("A-level maths and a B+student") == "A-level maths and a B+student"


def test_sentence_splitter_releases_whole_sentences_only():
    splitter = voice.SentenceSplitter()
    assert splitter.feed("Your courses are all saved now. Next") == ["Your courses are all saved now."]
    assert splitter.feed(" you can add your marks. And") == ["Next you can add your marks."]
    assert splitter.flush() == ["And"]


def test_short_sentences_are_joined_with_the_next_one():
    splitter = voice.SentenceSplitter()
    assert splitter.feed("Hi! Your OS grade is looking good so far. ") == ["Hi! Your OS grade is looking good so far."]
    assert splitter.feed("Okay. ") == []  # still too short on its own: waits for the next sentence


def test_sentence_splitter_works_one_character_at_a_time():
    splitter, sentences = voice.SentenceSplitter(), []
    for character in "The first sentence is right here. The second one follows right now.":
        sentences += splitter.feed(character)
    assert sentences + splitter.flush() == ["The first sentence is right here.", "The second one follows right now."]


class FakePolly:
    def __init__(self, unsupported=()):
        self.unsupported, self.calls = unsupported, []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["Engine"] in self.unsupported:
            raise ClientError({"Error": {"Code": "ValidationException", "Message": "engine not supported"}}, "SynthesizeSpeech")
        return {"AudioStream": io.BytesIO(kwargs["Text"].encode())}


def test_speak_falls_back_to_neural_when_generative_is_not_supported(monkeypatch):
    polly = FakePolly(unsupported=("generative",))
    monkeypatch.setattr(voice, "polly_client", lambda region: polly)
    assert voice.speak("Hello **there**", "Ruth", "us-east-1") == b"Hello there"
    assert [c["Engine"] for c in polly.calls] == ["generative", "neural"]


def test_speak_raises_other_errors(monkeypatch):
    class Denied(FakePolly):
        def synthesize_speech(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "SynthesizeSpeech")

    monkeypatch.setattr(voice, "polly_client", lambda region: Denied())
    with pytest.raises(ClientError):
        voice.speak("Hello", "Ruth", "us-east-1")


def test_streaming_speaker_returns_clips_in_sentence_order(monkeypatch):
    monkeypatch.setattr(voice, "speak", lambda text, *args: text.encode())
    speaker = voice.StreamingSpeaker("Ruth", "us-east-1")
    clips = []
    for chunk in ["Your first sentence is ready. ", "And the second sentence is here. ", "Last bit"]:
        clips += speaker.feed(chunk)
    clips += list(speaker.finish())
    assert clips == [b"Your first sentence is ready.", b"And the second sentence is here.", b"Last bit"]
    assert speaker.error is None


def test_streaming_speaker_survives_polly_errors(monkeypatch):
    def broken(*args):
        raise RuntimeError("polly is down")

    monkeypatch.setattr(voice, "speak", broken)
    speaker = voice.StreamingSpeaker("Ruth", "us-east-1")
    speaker.feed("This sentence will not be spoken. ")
    assert list(speaker.finish()) == [] and "polly is down" in str(speaker.error)


def test_player_html_embeds_every_clip():
    html = voice.player_html([b"abc", b"def"])
    assert "data:audio/mpeg;base64,YWJj" in html and "data:audio/mpeg;base64,ZGVm" in html
    assert "__studyTts" in voice.stop_html()
