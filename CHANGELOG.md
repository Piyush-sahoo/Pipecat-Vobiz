# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-11-04

### Changed

- Import from `pipecat_vobiz`. `pipecat.serializers.vobiz` still works, with a
  `DeprecationWarning`, and will be removed in a later release.
- Aligned with Pipecat's built-in telephony serializers: call
  `FrameSerializer.__init__`, inherit its `InputParams`, and ignore RTVI messages.
- `auto_hang_up` now ends calls with a REST `DELETE`, and raises `ValueError` at
  construction when `call_id`, `auth_id` or `auth_token` is missing.
- `parse_vobiz_start` raises `ValueError` when the first message is not a valid
  `start` event, and no longer returns `raw`.
- L16 audio is little-endian, confirmed on real calls. `l16_byte_order` is removed.
- Inbound and outbound formats are set independently, with `output_encoding` and
  `output_sample_rate`. L16 at 24000 Hz is supported outbound.
- Requires `pipecat-ai>=1.12.0,<2` and Python 3.11 or newer.

### Removed

- `InputParams.hangup_method`, and start-event format negotiation inside the
  serializer. Pass the values from `parse_vobiz_start` instead.
- Inbound formats Vobiz does not support: μ-law at 16000 or 24000 Hz, and L16 at 24000 Hz.
- `examples/server.py`. [Vobiz-X-Pipecat](https://github.com/vobiz-ai/Vobiz-X-Pipecat)
  covers recording and transfers.

### Added

- A unit test suite, and CI on Pipecat 1.12.0 and 1.15.0.
- A single-file example, `examples/bot.py`.

## [0.0.3] - 2026-05-15

### Added

- `audio/x-l16` (16-bit linear PCM) encoding support alongside `audio/x-mulaw`.
- Multi-rate support: `8000`, `16000`, `24000` Hz wire sample rates.
- `parse_vobiz_start(websocket)` helper — reads the Vobiz `start` event
  off the WebSocket and returns the full Vobiz-specific payload
  (`callId`, `streamId`, `mediaFormat.encoding`, `mediaFormat.sampleRate`).
  Drop-in replacement for `parse_telephony_websocket` when you want the
  negotiated mediaFormat instead of just provider-agnostic IDs.
- `start`-event auto-negotiation: the serializer adopts the wire format
  Vobiz declares in `mediaFormat` and logs a warning on mismatch.
- Handling for inbound `playedStream` and `clearedAudio` events
  (previously dropped silently as unknown events; now debug-logged).
- Outbound `stop` event support — sends Vobiz's documented
  `{"event":"stop","streamId":...}` on `EndFrame` / `CancelFrame`.
- `InputParams.hangup_method` config (`"ws_stop"` | `"rest"` | `"both"`,
  default `"both"`): WebSocket `stop` event with REST `DELETE` as
  background safety-net, so call termination is reliable even when
  auth creds are missing or the WS has already closed.
- `InputParams.encoding` and `InputParams.l16_byte_order` fields.
- `ValueError` raised at construction time for unsupported encoding,
  sample rate, byte order, or hangup method.

### Fixed

- `playAudio.contentType` now reflects the negotiated wire encoding
  (was hardcoded to `audio/x-mulaw`, breaking L16 outbound).

### Notes

- L16 byte order: RFC 2586 and the Vobiz docs say network byte order
  (big-endian), and that is the serializer default. Some Vobiz accounts
  empirically transport L16 as little-endian on the wire — if you see
  STT produce no transcripts while `media` frames arrive at the expected
  size and rate, set `l16_byte_order="le"`.
- 24000 Hz is accepted by the XML parser but, on at least one
  production region (`prod-voice-ap-south-1`), the media server silently
  declines to upgrade the WebSocket. 8000 and 16000 are confirmed
  working for both μ-law and L16.

## [0.0.1] - 2025-01-23

### Added

- Initial release of `pipecat-vobiz`
- `VobizFrameSerializer` implementation
- Support for 8kHz μ-law audio streaming
- Support for DTMF events
- Automatic call hangup on pipeline end
