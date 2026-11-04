# pipecat-vobiz

Connect a [Pipecat](https://github.com/pipecat-ai/pipecat) voice agent to phone calls on [Vobiz](https://www.vobiz.ai), a global telephony provider for voice AI.

`VobizFrameSerializer` translates between Pipecat frames and the WebSocket protocol opened by the Vobiz [`<Stream>`](https://www.vobiz.ai/docs/xml/stream/initiate) XML verb. It follows the same structure as Pipecat's built-in Plivo and Twilio serializers.

This integration is maintained by Vobiz.

## Installation

```bash
uv add pipecat-vobiz
```

Or use `pip install pipecat-vobiz`.

## How it works

```text
Phone call <-> Vobiz <-> WebSocket <-> FastAPIWebsocketTransport + VobizFrameSerializer <-> your pipeline
```

| Pipecat | Vobiz |
| --- | --- |
| `media` event | `InputAudioRawFrame` |
| `OutputAudioRawFrame` | `playAudio` event |
| `InterruptionFrame` | `clearAudio` event |
| `EndFrame` or `CancelFrame` | REST `DELETE` on the call, when `auto_hang_up` is on |

## Usage

Answer the call with XML that opens a bidirectional stream:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">wss://your-domain.com/ws/your-secret</Stream>
</Response>
```

Then read the `start` event and give the serializer to the transport:

```python
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat_vobiz import VobizFrameSerializer, parse_vobiz_start

await websocket.accept()
start = await parse_vobiz_start(websocket)

serializer = VobizFrameSerializer(
    stream_id=start["stream_id"],
    call_id=start["call_id"],
    auth_id=os.environ["VOBIZ_AUTH_ID"],
    auth_token=os.environ["VOBIZ_AUTH_TOKEN"],
    params=VobizFrameSerializer.InputParams(
        encoding=start["encoding"],
        vobiz_sample_rate=start["sample_rate"],
    ),
)
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        serializer=serializer,
    ),
)
```

[`examples/bot.py`](examples/bot.py) is a complete agent in one file.

## Configuration

`VobizFrameSerializer` takes `stream_id`, `call_id`, `auth_id`, `auth_token` and `params`. The three credentials are required while `auto_hang_up` is on.

| `InputParams` field | Default | Description |
| --- | --- | --- |
| `encoding` | `audio/x-mulaw` | Inbound encoding: `audio/x-mulaw` or `audio/x-l16`. Must match the `<Stream>` `contentType`. |
| `vobiz_sample_rate` | `8000` | Inbound rate. μ-law supports 8000 Hz. L16 supports 8000 and 16000 Hz. |
| `output_encoding` | inbound encoding | Outbound encoding, set independently of inbound. |
| `output_sample_rate` | inbound rate | Outbound rate. L16 also supports 24000 Hz outbound. |
| `sample_rate` | `None` | Overrides the pipeline input sample rate. |
| `auto_hang_up` | `True` | End the call on `EndFrame` or `CancelFrame`. |

L16 audio is little-endian on the wire.

`auto_hang_up` deletes the whole call. If your XML has a verb after `<Stream>`, such as `<Dial>` for a transfer, set `auto_hang_up=False` so that the verb can run.

## Run the example

You need a [Vobiz account](https://console.vobiz.ai) with a phone number, plus Deepgram and Google API keys.

1. Install the dependencies and add your keys:

   ```bash
   uv pip install "pipecat-vobiz[example]"
   cp examples/env.example .env
   ```

2. Start the bot, and expose port 8765 at a public HTTPS URL:

   ```bash
   python examples/bot.py
   ngrok http 8765
   ```

3. In the Vobiz console, create an [application](https://www.vobiz.ai/docs/applications/create-application) with `https://<your-url>/answer` as its answer URL, and attach your number to it.

4. Call the number.

For recording, transfers and a dashboard, see [Vobiz-X-Pipecat](https://github.com/vobiz-ai/Vobiz-X-Pipecat). The full setup guide is at [vobiz.ai/docs/integrations/pipecat](https://www.vobiz.ai/docs/integrations/pipecat).

## Pipecat compatibility

Tested on real phone calls with Pipecat 1.15, across every inbound and outbound format above. Unit tests run against Pipecat 1.12.0 and 1.15.0, on Python 3.11 to 3.13.

DTMF digits sent through the Vobiz REST API did not reach the stream in testing, so treat `InputDTMFFrame` as unverified.

## Development

```bash
uv pip install -e ".[dev]"
pytest
ruff check .
```

## License

BSD 2-Clause. See [LICENSE](LICENSE).
