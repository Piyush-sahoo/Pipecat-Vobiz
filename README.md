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
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)

# Create the serializer with your Vobiz credentials
serializer = VobizFrameSerializer(
    stream_id=stream_id,
    call_id=call_id,
    auth_id="YOUR_VOBIZ_AUTH_ID",
    auth_token="YOUR_VOBIZ_AUTH_TOKEN",
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

- 8kHz μ-law audio streaming
- DTMF event handling
- Automatic call termination on pipeline end
- Compatible with Pipecat's pipeline architecture

## Example

See the [examples/bot.py](examples/bot.py) for a complete working example.

## Pipecat Version Compatibility

Tested with Pipecat v0.0.86+

## License

BSD 2-Clause License
