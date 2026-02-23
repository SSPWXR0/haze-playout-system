from __future__ import annotations

import struct
import logging
from typing import Optional

log = logging.getLogger(__name__)

TS_PACKET_SIZE = 188
TS_SYNC_BYTE = 0x47
METADATA_PID = 0x0021
PMT_PID = 0x0020
PAT_PID = 0x0000


def _encode_syncsafe(n: int) -> bytes:
    result = bytearray(4)
    for i in range(3, -1, -1):
        result[i] = n & 0x7F
        n >>= 7
    return bytes(result)


def _id3_text_frame(frame_id: str, text: str) -> bytes:
    encoded = text.encode("utf-8")
    return (
        frame_id.encode("ascii")
        + struct.pack(">I", len(encoded) + 1)
        + b"\x00"
        + b"\x03"
        + encoded
    )


def build_id3_tag(title: str, artist: str, album: str) -> bytes:
    frames = b""
    if title:
        frames += _id3_text_frame("TIT2", title)
    if artist:
        frames += _id3_text_frame("TPE1", artist)
    if album:
        frames += _id3_text_frame("TALB", album)

    size = _encode_syncsafe(len(frames))
    header = b"ID3" + b"\x03\x00" + b"\x00" + size
    return header + frames


def _ts_packet(pid: int, payload: bytes, pusi: bool = True, cc: int = 0) -> bytes:
    header = bytes([
        TS_SYNC_BYTE,
        (0x40 if pusi else 0x00) | ((pid >> 8) & 0x1F),
        pid & 0xFF,
        0x10 | (cc & 0x0F),
    ])

    max_payload = TS_PACKET_SIZE - 4
    if len(payload) < max_payload:
        payload = payload + bytes([0xFF] * (max_payload - len(payload)))
    else:
        payload = payload[:max_payload]

    return header + payload


def _adaptation_field_packet(pid: int, payload: bytes, pcr: Optional[int], pusi: bool, cc: int) -> bytes:
    af = bytearray()

    if pcr is not None:
        flags = 0x10
        pcr_base = pcr // 300
        pcr_ext = pcr % 300
        pcr_bytes = (
            ((pcr_base >> 25) & 0xFF),
            ((pcr_base >> 17) & 0xFF),
            ((pcr_base >> 9) & 0xFF),
            ((pcr_base >> 1) & 0xFF),
            (((pcr_base & 0x01) << 7) | 0x7E | ((pcr_ext >> 8) & 0x01)),
            (pcr_ext & 0xFF),
        )
        af += bytes([flags]) + bytes(pcr_bytes)
    else:
        af += bytes([0x00])

    af_len = len(af)
    max_payload = TS_PACKET_SIZE - 4 - 2 - af_len
    if len(payload) > max_payload:
        payload = payload[:max_payload]

    padding = TS_PACKET_SIZE - 4 - 2 - af_len - len(payload)
    if padding > 0:
        af += bytes([0xFF] * padding)
        af_len += padding

    header = bytes([
        TS_SYNC_BYTE,
        (0x40 if pusi else 0x00) | ((pid >> 8) & 0x1F),
        pid & 0xFF,
        0x30 | (cc & 0x0F),
        af_len,
    ])

    return header + bytes(af) + payload


class MetadataInjector:
    def __init__(self, ffmpeg_stdin):
        self._stdin = ffmpeg_stdin
        self._cc: dict[int, int] = {}
        self._current_id3: Optional[bytes] = None

    def _next_cc(self, pid: int) -> int:
        cc = self._cc.get(pid, 0)
        self._cc[pid] = (cc + 1) & 0x0F
        return cc

    def update(self, title: str, artist: str, album: str):
        self._current_id3 = build_id3_tag(title, artist, album)
        self._inject()

    def _inject(self):
        if self._current_id3 is None or self._stdin is None:
            return
        try:
            data = self._current_id3
            offset = 0
            pusi = True

            while offset < len(data):
                chunk = data[offset:offset + TS_PACKET_SIZE - 4]
                pkt = _ts_packet(METADATA_PID, chunk, pusi=pusi, cc=self._next_cc(METADATA_PID))
                self._stdin.write(pkt)
                offset += len(chunk)
                pusi = False

            self._stdin.flush()
        except BrokenPipeError:
            log.error("MetadataInjector: broken pipe")
        except Exception as e:
            log.debug(f"MetadataInjector inject error: {e}")