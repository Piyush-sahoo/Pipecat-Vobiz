# Pipecat Vobiz Integration

Community integration for using [Vobiz](https://vobiz.ai) telephony with [Pipecat](https://github.com/pipecat-ai/pipecat).

## Installation

```bash
pip install pipecat-vobiz
```

Or install from source:

```bash
pip install git+https://github.com/Piyush-sahoo/Pipecat-Vobiz.git
```

## Usage

```python
from pipecat.serializers.vobiz import VobizFrameSerializer, parse_vobiz_start
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)

# Read Vobiz's `start` event off the WebSocket to learn the negotiated
# wire format (encoding + sample rate + stream/call IDs).
parsed = await parse_vobiz_start(websocket)

# Create the serializer using the wire format Vobiz actually negotiated.
serializer = VobizFrameSerializer(
    stream_id=parsed["stream_id"],
    call_id=parsed["call_id"],
    auth_id="YOUR_VOBIZ_AUTH_ID",
    auth_token="YOUR_VOBIZ_AUTH_TOKEN",
    params=VobizFrameSerializer.InputParams(
        encoding=parsed["encoding"] or "audio/x-mulaw",
        vobiz_sample_rate=parsed["sample_rate"] or 8000,
        # l16_byte_order="le",     # if your account transports L16 LE
        # hangup_method="both",    # default; "ws_stop" or "rest" also valid
    ),
)

# Use it with the FastAPI WebSocket transport
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        serializer=serializer,
    ),
)
```

## Features

- Audio streaming in **`audio/x-mulaw`** or **`audio/x-l16`** at
  **8000 / 16000 Hz** (24000 Hz is in the protocol but not reliable on
  all regions — see CHANGELOG).
- Self-negotiation from Vobiz's `start` event — adopts the encoding and
  sample rate Vobiz actually declares on the wire, with a warning if it
  disagrees with your config.
- DTMF event handling.
- Barge-in via Pipecat's `InterruptionFrame` → Vobiz `clearAudio`.
- Reliable call termination: sends Vobiz's documented `stop` event on
  the WebSocket **and** issues a REST `DELETE` as a background safety
  net (configurable via `hangup_method`).
- Compatible with Pipecat's pipeline architecture.

## Example

See the [examples/bot.py](examples/bot.py) for a complete working example.

## Pipecat Version Compatibility

Tested with Pipecat v0.0.86+

## License

BSD 2-Clause License
