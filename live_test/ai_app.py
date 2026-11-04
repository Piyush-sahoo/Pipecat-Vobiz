"""Real-call test of pipecat-vobiz from PyPI, with every AI stage on Gemini.

Modes: example (examples/bot.py itself), cascaded (Gemini STT, LLM and TTS) and
realtime (Gemini Live). Every route sits under TEST_TOKEN, because this server
holds real credentials.
"""

import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiModalities
from pipecat.services.google.gemini_live.stt import GeminiSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.tts import GeminiTTSService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from pipecat_vobiz import VobizFrameSerializer, parse_vobiz_start

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
import bot as example_bot  # noqa: E402

TOKEN = os.environ["TEST_TOKEN"]
KEY = os.environ["GOOGLE_API_KEY"]
EVENTS: list[dict] = []
CAPTURE: dict[str, bytearray] = {}
T0 = time.monotonic()
app = FastAPI()

SYSTEM = (
    "You are a helpful assistant on a phone call. Replies are spoken aloud, so use plain "
    "sentences with no lists or formatting. Answer questions directly and briefly."
)
GREETING = (
    "Welcome the caller, then describe a calm spring morning in five long sentences. "
    "If the caller speaks, stop and answer them."
)


def log(what: str, **extra) -> None:
    EVENTS.append({"t": round(time.monotonic() - T0, 3), "what": what, **extra})
    print(EVENTS[-1], flush=True)


def check(token: str) -> None:
    if not secrets.compare_digest(token, TOKEN):
        raise HTTPException(status_code=404)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/{token}/events")
async def events(token: str) -> list[dict]:
    check(token)
    return EVENTS


@app.get("/{token}/capture/{name}")
async def capture(token: str, name: str) -> Response:
    check(token)
    return Response(content=bytes(CAPTURE.get(name, b"")), media_type="application/octet-stream")


@app.api_route("/{token}/answer", methods=["GET", "POST"])
async def answer(token: str, request: Request) -> Response:
    check(token)
    q = dict(request.query_params)
    log("answer url requested", q=q.get("name"))
    url = f"wss://{request.headers['host']}/{TOKEN}/ws?{urlencode(q)}"
    ct = q.get("ct", "audio/x-mulaw;rate=8000")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Stream bidirectional="true" keepCallAlive="true" contentType="{ct}">'
        f"{escape(url)}</Stream></Response>"
    )
    return Response(content=xml, media_type="application/xml")


class Logged(VobizFrameSerializer):
    played = 0
    name_ = ""

    async def serialize(self, frame):
        out = await super().serialize(frame)
        if out:
            msg = json.loads(out)
            if msg.get("event") == "playAudio":
                self.played += 1
                if self.played == 1:
                    log(
                        "first playAudio sent",
                        fmt=msg["media"]["contentType"],
                        rate=msg["media"]["sampleRate"],
                    )
            else:
                log(f"sent {msg.get('event')}", play_audio_so_far=self.played)
        return out

    async def deserialize(self, data):
        msg = json.loads(data)
        if msg.get("event") != "media":
            log(f"received {msg.get('event')}", raw=str(msg)[:200])
        frame = await super().deserialize(data)
        if frame is not None and msg.get("event") == "media":
            CAPTURE.setdefault(self.name_, bytearray()).extend(frame.audio)
        if frame is not None and msg.get("event") == "dtmf":
            log("InputDTMFFrame", digit=frame.button.value)
        return frame

    async def _hang_up_call(self):
        log("auto_hang_up running")
        await super()._hang_up_call()
        log("auto_hang_up finished")


@app.websocket("/{token}/ws")
async def ws(websocket: WebSocket, token: str) -> None:
    if not secrets.compare_digest(token, TOKEN):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    start = await parse_vobiz_start(websocket)
    log("parse_vobiz_start", start=start | {"stream_id": ""})
    q = dict(websocket.query_params)
    mode = q.get("mode", "cascaded")
    if mode == "example":
        log("running examples/bot.py run_bot")
        await example_bot.run_bot(websocket, start)
        log("examples/bot.py run_bot returned")
        return

    in_rate = start["sample_rate"]
    serializer = Logged(
        stream_id=start["stream_id"],
        call_id=start["call_id"],
        auth_id=os.environ["VOBIZ_AUTH_ID"],
        auth_token=os.environ["VOBIZ_AUTH_TOKEN"],
        params=VobizFrameSerializer.InputParams(
            encoding=start["encoding"],
            vobiz_sample_rate=in_rate,
            output_encoding=q.get("out_enc") or start["encoding"],
            output_sample_rate=int(q.get("out_rate") or in_rate),
        ),
    )
    serializer.name_ = q.get("name", "x")
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True, audio_out_enabled=True, serializer=serializer
        ),
    )
    vad = LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    if mode == "realtime":
        llm = GeminiLiveLLMService(
            api_key=KEY,
            settings=GeminiLiveLLMService.Settings(
                model=os.getenv("GEMINI_LIVE_MODEL", "models/gemini-3.8-live"),
                voice="Charon",
                system_instruction=SYSTEM,
                modalities=GeminiModalities.AUDIO,
            ),
        )
        context = LLMContext([{"role": "user", "content": GREETING}])
        user, assistant = LLMContextAggregatorPair(
            context, user_params=vad, realtime_service_mode=True
        )
        stages = [transport.input(), user, llm, transport.output(), assistant]
    else:
        stt = GeminiSTTService(api_key=KEY)
        llm = GoogleLLMService(
            api_key=KEY, model=os.getenv("GEMINI_MODEL"), system_instruction=SYSTEM
        )
        tts = GeminiTTSService(
            api_key=KEY,
            settings=GeminiTTSService.Settings(model="gemini-3.8-flash-lite-tts", voice="Kore"),
        )
        context = LLMContext([{"role": "developer", "content": GREETING}])
        user, assistant = LLMContextAggregatorPair(context, user_params=vad)
        stages = [transport.input(), stt, user, llm, tts, transport.output(), assistant]

    worker = PipelineWorker(
        Pipeline(stages),
        params=PipelineParams(audio_in_sample_rate=in_rate, audio_out_sample_rate=24000),
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    log("pipeline ready", mode=mode)

    @transport.event_handler("on_client_connected")
    async def connected(t, c):
        await worker.queue_frames([LLMRunFrame()])
        hang_up_after = float(q.get("hangup_after") or 0)
        if hang_up_after:

            async def end() -> None:
                await asyncio.sleep(hang_up_after)
                log("queueing EndFrame")
                await worker.queue_frames([EndFrame()])

            asyncio.create_task(end())

    @transport.event_handler("on_client_disconnected")
    async def disconnected(t, c):
        log("websocket closed", play_audio=serializer.played)
        await runner.cancel()

    await runner.run()
    log("runner finished")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
