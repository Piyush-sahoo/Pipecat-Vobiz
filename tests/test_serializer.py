#
# Copyright (c) 2026, Vobiz
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Tests for VobizFrameSerializer, using the message shapes in the Vobiz docs."""

import array
import base64
import json
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageUrgentFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameProcessorSetup

from pipecat_vobiz import VobizFrameSerializer, parse_vobiz_start

STREAM_ID = "c4dfd815-a92a-4140-ab85-5ff28c004116"
CALL_ID = "5401fd2e-6344-40df-a22c-c8ffea7a92e7"
START_EVENT = {
    "sequenceNumber": 0,
    "event": "start",
    "start": {
        "callId": CALL_ID,
        "streamId": STREAM_ID,
        "accountId": "500025",
        "tracks": ["inbound"],
        "mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 16000},
    },
    "extra_headers": "{}",
}


def _setup(sample_rate: int) -> FrameProcessorSetup:
    setup = MagicMock(spec=FrameProcessorSetup)
    setup.audio_in_sample_rate = sample_rate
    setup.audio_out_sample_rate = sample_rate
    return setup


def _params(**kwargs) -> VobizFrameSerializer.InputParams:
    return VobizFrameSerializer.InputParams(auto_hang_up=False, **kwargs)


def _media(payload: bytes) -> str:
    return json.dumps({"event": "media", "media": {"payload": base64.b64encode(payload).decode()}})


def _session(status: int) -> MagicMock:
    response = MagicMock(status=status)
    response.text = AsyncMock(return_value="error body")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.delete = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class TestParseStart(unittest.IsolatedAsyncioTestCase):
    async def _parse(self, message: str) -> dict:
        websocket = MagicMock()
        websocket.receive_text = AsyncMock(return_value=message)
        return await parse_vobiz_start(websocket)

    async def test_reads_ids_and_media_format(self):
        result = await self._parse(json.dumps(START_EVENT))
        self.assertEqual(
            result,
            {
                "stream_id": STREAM_ID,
                "call_id": CALL_ID,
                "encoding": "audio/x-l16",
                "sample_rate": 16000,
            },
        )

    async def test_missing_media_format_defaults_to_mulaw_8k(self):
        event = {"event": "start", "start": {"streamId": STREAM_ID, "callId": CALL_ID}}
        result = await self._parse(json.dumps(event))
        self.assertEqual((result["encoding"], result["sample_rate"]), ("audio/x-mulaw", 8000))

    async def test_invalid_first_messages_raise_value_error(self):
        for message in (
            "not json",
            "[]",
            '{"event": "media"}',
            '{"event": "start", "start": {}}',
            '{"start": {"streamId": "x"}}',
        ):
            with self.subTest(message=message), self.assertRaises(ValueError):
                await self._parse(message)


class TestConstructor(unittest.TestCase):
    def test_auto_hang_up_requires_credentials(self):
        with self.assertRaisesRegex(ValueError, "call_id, auth_id, auth_token"):
            VobizFrameSerializer(stream_id=STREAM_ID)

    def test_credentials_not_required_without_auto_hang_up(self):
        VobizFrameSerializer(stream_id=STREAM_ID, params=_params())

    def test_rejects_formats_vobiz_does_not_support_inbound(self):
        for encoding, rate in (
            ("audio/x-mulaw", 16000),
            ("audio/x-l16", 24000),
            ("audio/x-alaw", 8000),
        ):
            with self.subTest(encoding=encoding, rate=rate), self.assertRaises(ValueError):
                VobizFrameSerializer(
                    stream_id=STREAM_ID, params=_params(encoding=encoding, vobiz_sample_rate=rate)
                )


class TestSerialize(unittest.IsolatedAsyncioTestCase):
    async def _serializer(self, rate: int = 8000, **params) -> VobizFrameSerializer:
        serializer = VobizFrameSerializer(
            stream_id=STREAM_ID, params=_params(vobiz_sample_rate=rate, **params)
        )
        await serializer.setup(_setup(rate))
        return serializer

    async def test_audio_becomes_play_audio_in_mulaw(self):
        serializer = await self._serializer()
        pcm = array.array("h", [0, 1000, -1000, 8000] * 40).tobytes()
        message = json.loads(
            await serializer.serialize(
                OutputAudioRawFrame(audio=pcm, sample_rate=8000, num_channels=1)
            )
        )
        self.assertEqual(message["event"], "playAudio")
        self.assertEqual(message["streamId"], STREAM_ID)
        self.assertEqual(message["media"]["contentType"], "audio/x-mulaw")
        self.assertEqual(message["media"]["sampleRate"], 8000)
        self.assertEqual(len(base64.b64decode(message["media"]["payload"])), 160)

    async def test_l16_is_little_endian_on_the_wire(self):
        serializer = await self._serializer(encoding="audio/x-l16")
        pcm = (0x0102).to_bytes(2, "little") * 160
        message = json.loads(
            await serializer.serialize(
                OutputAudioRawFrame(audio=pcm, sample_rate=8000, num_channels=1)
            )
        )
        self.assertEqual(message["media"]["contentType"], "audio/x-l16")
        self.assertEqual(base64.b64decode(message["media"]["payload"]), b"\x02\x01" * 160)

    async def test_outbound_formats_are_independent_of_inbound(self):
        for encoding, rate, size in (
            ("audio/x-mulaw", 8000, 160),
            ("audio/x-l16", 8000, 320),
            ("audio/x-l16", 16000, 640),
            ("audio/x-l16", 24000, 960),
        ):
            with self.subTest(encoding=encoding, rate=rate):
                serializer = await self._serializer(
                    output_encoding=encoding, output_sample_rate=rate
                )
                message = json.loads(
                    await serializer.serialize(
                        OutputAudioRawFrame(
                            audio=b"\x00\x10" * int(rate * 0.02), sample_rate=rate, num_channels=1
                        )
                    )
                )
                self.assertEqual(message["media"]["contentType"], encoding)
                self.assertEqual(message["media"]["sampleRate"], rate)
                self.assertEqual(len(base64.b64decode(message["media"]["payload"])), size)

    async def test_interruption_becomes_clear_audio(self):
        serializer = await self._serializer()
        message = json.loads(await serializer.serialize(InterruptionFrame()))
        self.assertEqual(message, {"event": "clearAudio", "streamId": STREAM_ID})

    async def test_transport_message_passes_through_but_rtvi_is_ignored(self):
        serializer = await self._serializer()
        custom = {"event": "checkpoint", "streamId": STREAM_ID, "name": "response-3"}
        self.assertEqual(
            json.loads(await serializer.serialize(OutputTransportMessageUrgentFrame(custom))),
            custom,
        )
        rtvi = OutputTransportMessageUrgentFrame({"label": "rtvi-ai", "type": "x"})
        self.assertIsNone(await serializer.serialize(rtvi))

    async def test_unhandled_frame_returns_none(self):
        serializer = await self._serializer()
        self.assertIsNone(await serializer.serialize(TextFrame("hello")))


class TestDeserialize(unittest.IsolatedAsyncioTestCase):
    async def _serializer(self, rate: int = 8000, **params) -> VobizFrameSerializer:
        serializer = VobizFrameSerializer(
            stream_id=STREAM_ID, params=_params(vobiz_sample_rate=rate, **params)
        )
        await serializer.setup(_setup(rate))
        return serializer

    async def test_mulaw_media_becomes_input_audio(self):
        serializer = await self._serializer()
        frame = await serializer.deserialize(_media(b"\xff" * 160))
        self.assertIsInstance(frame, InputAudioRawFrame)
        self.assertEqual((frame.sample_rate, frame.num_channels), (8000, 1))
        self.assertEqual(len(frame.audio), 320)

    async def test_l16_media_becomes_input_audio(self):
        for rate, size in ((8000, 320), (16000, 640)):
            with self.subTest(rate=rate):
                serializer = await self._serializer(rate, encoding="audio/x-l16")
                frame = await serializer.deserialize(_media(b"\x10\x00" * (size // 2)))
                self.assertEqual((frame.sample_rate, len(frame.audio)), (rate, size))

    async def test_invalid_messages_are_ignored_not_raised(self):
        serializer = await self._serializer()
        for message in (
            "not json",
            '{"foo": "bar"}',
            '{"event": "media", "media": {}}',
            '{"event": "playedStream", "name": "response-3"}',
            json.dumps({"event": "clearedAudio", "streamId": STREAM_ID}),
        ):
            with self.subTest(message=message):
                self.assertIsNone(await serializer.deserialize(message))


class TestHangUp(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.serializer = VobizFrameSerializer(
            stream_id=STREAM_ID, call_id=CALL_ID, auth_id="MA_TEST", auth_token="token"
        )
        await self.serializer.setup(_setup(8000))

    async def test_end_frame_deletes_the_call_with_vobiz_auth_headers(self):
        session = _session(204)
        with patch("aiohttp.ClientSession", return_value=session):
            self.assertIsNone(await self.serializer.serialize(EndFrame()))
        session.delete.assert_called_once_with(
            f"https://api.vobiz.ai/api/v1/Account/MA_TEST/Call/{CALL_ID}/",
            headers={"X-Auth-ID": "MA_TEST", "X-Auth-Token": "token"},
        )

    async def test_hangs_up_only_once(self):
        session = _session(204)
        with patch("aiohttp.ClientSession", return_value=session):
            await self.serializer.serialize(EndFrame())
            await self.serializer.serialize(CancelFrame())
        session.delete.assert_called_once()

    async def test_failures_do_not_raise(self):
        for status in (404, 500):
            with self.subTest(status=status):
                self.serializer._hangup_attempted = False
                with patch("aiohttp.ClientSession", return_value=_session(status)):
                    self.assertIsNone(await self.serializer.serialize(EndFrame()))
        self.serializer._hangup_attempted = False
        with patch("aiohttp.ClientSession", side_effect=OSError("network down")):
            self.assertIsNone(await self.serializer.serialize(CancelFrame()))

    async def test_no_hang_up_when_disabled(self):
        serializer = VobizFrameSerializer(stream_id=STREAM_ID, params=_params())
        await serializer.setup(_setup(8000))
        with patch("aiohttp.ClientSession") as client_session:
            self.assertIsNone(await serializer.serialize(EndFrame()))
        client_session.assert_not_called()


class TestDeprecatedImport(unittest.TestCase):
    def test_old_path_warns_and_exports_the_same_class(self):
        sys.modules.pop("pipecat.serializers.vobiz", None)
        try:
            with self.assertWarnsRegex(DeprecationWarning, "pipecat_vobiz"):
                import pipecat.serializers.vobiz as old
        except ModuleNotFoundError:
            self.skipTest("The compatibility module only exists in a built wheel")
        self.assertIs(old.VobizFrameSerializer, VobizFrameSerializer)
