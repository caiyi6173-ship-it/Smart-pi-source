
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import audioop
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    import dashscope  # type: ignore
    from dashscope.audio.asr.recognition import Recognition  # type: ignore
    from dashscope.audio.tts_v2 import AudioFormat as TtsAudioFormat  # type: ignore
    from dashscope.audio.tts_v2 import SpeechSynthesizer as TtsSynthesizer  # type: ignore

    DASHSCOPE_READY = True
except Exception:
    dashscope = None  # type: ignore
    Recognition = None  # type: ignore
    TtsAudioFormat = None  # type: ignore
    TtsSynthesizer = None  # type: ignore
    DASHSCOPE_READY = False

try:
    from faster_whisper import WhisperModel  # type: ignore

    FASTER_WHISPER_READY = True
except Exception:
    WhisperModel = None  # type: ignore
    FASTER_WHISPER_READY = False

try:
    import webrtcvad  # type: ignore

    WEBRTCVAD_READY = True
except Exception:
    webrtcvad = None  # type: ignore
    WEBRTCVAD_READY = False

PLACEHOLDER_RESULT = "暂无分析结果。"
DEFAULT_WHISPER_INITIAL_PROMPT = "smartpi 舌象分析、摄像头识别、心率、血氧、皮肤温度、读取分析结果、重新分析。"
DEFAULT_WAKE_PROMPT = ""
DEFAULT_DIRECT_LLM_SYSTEM_PROMPT = (
    "你是 smartpi 的中文语音助手。"
    "你运行在 smartpi 设备内部，能够触发 smartpi 已接入的摄像头、传感器和分析接口。"
    "请优先自然、简洁地回答用户。"
    "当用户明确是在控制 smartpi 设备或读取 smartpi 数据时，"
    "你可以在回复最后单独追加一行动作标记，格式必须是 [[SMARTPI_ACTION:动作名]]。"
    "动作名只能从以下白名单中选择："
    "camera.start,camera.stop,sensor.temperature.start,sensor.temperature.stop,"
    "sensor.pulseox.start,sensor.pulseox.stop,telemetry.temperature.read,"
    "telemetry.pulseox.read,analysis.latest,analysis.trigger。"
    "如果只是闲聊、解释、安抚、普通问答，或者你不确定需要触发设备动作，就不要追加动作标记。"
    "不要说你无法访问摄像头、无法控制设备，也不要给出电脑或手机的通用操作教程。"
    "示例：用户说“帮我把摄像头打开”，你可以回复“好的，这就为你打开摄像头识别。[[SMARTPI_ACTION:camera.start]]”。"
    "用户说“把摄像头关掉”，你可以回复“好的，已为你关闭摄像头识别。[[SMARTPI_ACTION:camera.stop]]”。"
    "不要输出 Markdown，不要输出代码块。"
)
DEFAULT_MEMORY_SUMMARY_SYSTEM_PROMPT = (
    "你是 smartpi 语音会话记忆压缩助手。"
    "请把用户与助手的旧对话压缩成后续继续聊天时有用的中文摘要。"
    "只保留用户背景、身体状态主诉、分析趋势、未解决问题和重要偏好。"
    "删除寒暄、重复表述和无意义废话。"
    "输出 3 到 6 句中文，不要使用列表、编号、Markdown。"
)
DEFAULT_REPLY_COMPRESSION_SYSTEM_PROMPT = (
    "你是 smartpi 语音播报压缩助手。"
    "请把一段较长中文回复压缩成适合语音播报的 1 到 2 句自然中文。"
    "保留核心结论和行动建议，不要使用编号、列表、Markdown，不要编造新事实。"
)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def json_dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def clamp_record_seconds(value: float) -> float:
    return max(0.6, min(15.0, value))


def normalize_match_text(value: str) -> str:
    chars: list[str] = []
    for char in value.strip().lower():
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            chars.append(char)
    return "".join(chars)


def normalize_match_mapping(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index_map: list[int] = []
    for index, char in enumerate(value.strip().lower()):
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            chars.append(char)
            index_map.append(index)
    return "".join(chars), index_map


def split_aliases(value: str) -> list[str]:
    if not value:
        return []
    aliases = [item.strip() for item in re.split(r"[,，;；|/]+", value) if item.strip()]
    deduped: list[str] = []
    for alias in aliases:
        if alias not in deduped:
            deduped.append(alias)
    return deduped


def edit_distance(left: str, right: str, max_distance: int | None = None) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for row_index, left_char in enumerate(left, start=1):
        current = [row_index]
        row_min = current[0]
        for col_index, right_char in enumerate(right, start=1):
            insertion = current[col_index - 1] + 1
            deletion = previous[col_index] + 1
            substitution = previous[col_index - 1] + (0 if left_char == right_char else 1)
            value = min(insertion, deletion, substitution)
            current.append(value)
            row_min = min(row_min, value)
        if max_distance is not None and row_min > max_distance:
            return row_min
        previous = current
    return previous[-1]


def prompt_is_corrupted(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    chinese_chars = sum(1 for char in stripped if "\u4e00" <= char <= "\u9fff")
    question_marks = stripped.count("?")
    replacement_marks = stripped.count("\ufffd")
    return chinese_chars == 0 and (question_marks >= 3 or replacement_marks > 0)


def resolve_prompt(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = value.strip()
    return fallback if prompt_is_corrupted(cleaned) else cleaned


def contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


ACTION_MARKER_RE = re.compile(r"\[\[SMARTPI_ACTION:([a-zA-Z0-9._-]+)\]\]")


def split_command_parts(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    try:
        return shlex.split(cleaned)
    except ValueError:
        return [cleaned]


def command_exists(value: str) -> bool:
    command_parts = split_command_parts(value)
    if not command_parts:
        return False
    executable = command_parts[0]
    return Path(executable).is_file() or shutil.which(executable) is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="smartpi voice agent with local STT/TTS and OpenClaw support")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--bridge-base-url", default="http://127.0.0.1:8092")
    parser.add_argument("--wake-word", default="小中医")
    parser.add_argument("--assistant-name", default="smartpi Voice")
    parser.add_argument("--record-device", default="default")
    parser.add_argument("--playback-device", default="default")
    parser.add_argument("--record-seconds", type=float, default=3.0)
    parser.add_argument("--record-sample-rate", type=int, default=16000)
    parser.add_argument("--dashscope-api-key", default=os.environ.get("DASHSCOPE_API_KEY", ""))
    parser.add_argument("--asr-model", default=os.environ.get("DASHSCOPE_ASR_MODEL", "paraformer-realtime-v2"))
    parser.add_argument("--tts-model", default=os.environ.get("DASHSCOPE_TTS_MODEL", "cosyvoice-v2"))
    parser.add_argument("--tts-voice", default=os.environ.get("DASHSCOPE_TTS_VOICE", "longxiaochun_v2"))
    parser.add_argument("--enable-cloud-speech", action="store_true")
    parser.add_argument("--enable-local-stt", action="store_true")
    parser.add_argument("--enable-local-tts", action="store_true")
    parser.add_argument("--enable-wake-listen", action="store_true")
    parser.add_argument("--enable-keyword-spotter", action="store_true")
    parser.add_argument("--wake-listen-window-seconds", type=float, default=1.8)
    parser.add_argument("--wake-listen-command-seconds", type=float, default=5.0)
    parser.add_argument("--command-max-record-seconds", type=float, default=5.0)
    parser.add_argument("--command-silence-stop-ms", type=int, default=700)
    parser.add_argument("--command-min-speech-ms", type=int, default=300)
    parser.add_argument("--command-rms-threshold", type=int, default=220)
    parser.add_argument("--wake-rms-threshold", type=int, default=160)
    parser.add_argument("--enable-webrtcvad", action="store_true")
    parser.add_argument("--vad-mode", type=int, default=1)
    parser.add_argument("--vad-frame-ms", type=int, default=30)
    parser.add_argument("--wake-listen-cooldown-seconds", type=float, default=0.25)
    parser.add_argument("--wake-word-aliases", default=os.environ.get("WAKE_WORD_ALIASES", ""))
    parser.add_argument("--wake-fuzzy-max-distance", type=int, default=1)
    parser.add_argument("--wake-fuzzy-prefix-window-chars", type=int, default=8)
    parser.add_argument("--wake-ack-text", default=os.environ.get("WAKE_ACK_TEXT", ""))
    parser.add_argument("--whisper-model", default=os.environ.get("FASTER_WHISPER_MODEL", "tiny"))
    parser.add_argument("--whisper-device", default=os.environ.get("FASTER_WHISPER_DEVICE", "cpu"))
    parser.add_argument("--whisper-compute-type", default=os.environ.get("FASTER_WHISPER_COMPUTE_TYPE", "int8"))
    parser.add_argument("--whisper-language", default=os.environ.get("FASTER_WHISPER_LANGUAGE", "zh"))
    parser.add_argument(
        "--whisper-initial-prompt",
        default=os.environ.get(
            "FASTER_WHISPER_INITIAL_PROMPT",
            DEFAULT_WHISPER_INITIAL_PROMPT,
        ),
    )
    parser.add_argument("--wake-whisper-model", default=os.environ.get("FASTER_WHISPER_WAKE_MODEL", "tiny"))
    parser.add_argument("--wake-whisper-compute-type", default=os.environ.get("FASTER_WHISPER_WAKE_COMPUTE_TYPE", "int8"))
    parser.add_argument(
        "--wake-whisper-initial-prompt",
        default=os.environ.get("FASTER_WHISPER_WAKE_INITIAL_PROMPT", DEFAULT_WAKE_PROMPT),
    )
    parser.add_argument("--keyword-spotter-command", default=os.environ.get("SHERPA_KWS_COMMAND", "sherpa-onnx-keyword-spotter"))
    parser.add_argument("--keyword-spotter-cli-command", default=os.environ.get("SHERPA_KWS_CLI", "sherpa-onnx-cli"))
    parser.add_argument("--kws-model-dir", default=os.environ.get("SHERPA_KWS_MODEL_DIR", ""))
    parser.add_argument("--kws-tokens-type", default=os.environ.get("SHERPA_KWS_TOKENS_TYPE", ""))
    parser.add_argument("--kws-keywords-threshold", type=float, default=float(os.environ.get("SHERPA_KWS_KEYWORDS_THRESHOLD", "0.35")))
    parser.add_argument("--kws-keywords-score", type=float, default=float(os.environ.get("SHERPA_KWS_KEYWORDS_SCORE", "1.8")))
    parser.add_argument("--kws-num-threads", type=int, default=int(os.environ.get("SHERPA_KWS_NUM_THREADS", "2")))
    parser.add_argument("--kws-inline-command", action="store_true")
    parser.add_argument("--piper-command", default=os.environ.get("PIPER_COMMAND", "piper"))
    parser.add_argument("--piper-model-path", default=os.environ.get("PIPER_MODEL_PATH", ""))
    parser.add_argument("--piper-config-path", default=os.environ.get("PIPER_CONFIG_PATH", ""))
    parser.add_argument("--tts-cache-dir", default=os.environ.get("TTS_CACHE_DIR", "/home/pi/smartpi/cache/tts"))
    parser.add_argument("--enable-remote-tts", action="store_true")
    parser.add_argument("--remote-tts-base-url", default=os.environ.get("REMOTE_TTS_BASE_URL", ""))
    parser.add_argument("--remote-tts-model", default=os.environ.get("REMOTE_TTS_MODEL", "tts-1"))
    parser.add_argument("--remote-tts-voice", default=os.environ.get("REMOTE_TTS_VOICE", "smartpi"))
    parser.add_argument("--remote-tts-timeout-seconds", type=float, default=float(os.environ.get("REMOTE_TTS_TIMEOUT_SECONDS", "30")))
    parser.add_argument("--enable-direct-llm", action="store_true")
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("DIRECT_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
    )
    parser.add_argument("--llm-api-key", default=os.environ.get("DIRECT_LLM_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "")))
    parser.add_argument("--llm-model", default=os.environ.get("DIRECT_LLM_MODEL", "qwen3-vl-flash-2026-01-22"))
    parser.add_argument("--llm-timeout-seconds", type=float, default=float(os.environ.get("DIRECT_LLM_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--llm-temperature", type=float, default=float(os.environ.get("DIRECT_LLM_TEMPERATURE", "0.2")))
    parser.add_argument(
        "--llm-system-prompt",
        default=os.environ.get("DIRECT_LLM_SYSTEM_PROMPT", DEFAULT_DIRECT_LLM_SYSTEM_PROMPT),
    )
    parser.add_argument("--enable-openclaw", action="store_true")
    parser.add_argument("--openclaw-command", default=os.environ.get("OPENCLAW_COMMAND", ""))
    parser.add_argument("--openclaw-timeout-seconds", type=float, default=12.0)
    return parser


@dataclass
class CommandOutcome:
    reply: str
    status: str = "IDLE"
    recognized_text: str | None = None
    audio_path: str | None = None


class PlaybackInterrupted(RuntimeError):
    pass


class VoiceAgent:
    # 论文 5.6语音交互程序设计：VoiceAgent 是树莓派侧语音助手主程序，
    # 负责唤醒监听、录音、语音识别、命令分流、大模型问答、语音合成和状态上报。
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.startup_log("voice agent init start")
        self.status = "IDLE"
        self.last_command: str | None = None
        self.last_reply: str | None = None
        self.last_error: str | None = None
        self.last_audio_path: str | None = None
        self.last_heard_text: str | None = None
        self.last_wake_detected_at: str | None = None
        self.turn_id: str | None = None
        self.turn_started_at: str | None = None
        self.turn_finished_at: str | None = None
        self.updated_at = iso_now()
        self.last_wake_ms: int | None = None
        self.last_record_ms: int | None = None
        self.last_stt_ms: int | None = None
        self.last_route_ms: int | None = None
        self.last_llm_ms: int | None = None
        self.last_tts_ms: int | None = None
        self.last_tts_synthesis_ms: int | None = None
        self.last_tts_playback_launch_ms: int | None = None
        self.last_tts_leading_silence_ms: int | None = None
        self.last_end_to_end_ms: int | None = None
        self.last_stt_provider: str | None = None
        self.last_tts_provider: str | None = None
        self.memory_enabled = True
        self.conversation_summary = ""
        self.recent_turns: list[dict[str, str]] = []
        self.memory_turn_count = 0
        self.memory_updated_at: str | None = None
        self.voice_context_cache: dict[str, Any] | None = None
        self.voice_context_cache_expires_at = 0.0
        self.memory_lock = threading.RLock()
        self.wake_word_aliases = split_aliases(args.wake_word_aliases)
        self.whisper_models: dict[tuple[str, str, str], Any] = {}
        self.piper_command_parts = split_command_parts(args.piper_command)
        self.whisper_initial_prompt = resolve_prompt(args.whisper_initial_prompt, DEFAULT_WHISPER_INITIAL_PROMPT)
        self.wake_whisper_initial_prompt = resolve_prompt(args.wake_whisper_initial_prompt, DEFAULT_WAKE_PROMPT)
        self.cloud_speech_enabled = bool(args.enable_cloud_speech and args.dashscope_api_key and DASHSCOPE_READY)
        self.local_stt_enabled = bool(args.enable_local_stt and FASTER_WHISPER_READY)
        self.local_tts_enabled = bool(
            args.enable_local_tts and command_exists(args.piper_command) and args.piper_model_path and Path(args.piper_model_path).is_file()
        )
        self.remote_tts_enabled = bool(args.enable_remote_tts and args.remote_tts_base_url and args.remote_tts_model)
        self.webrtcvad_enabled = bool(args.enable_webrtcvad and WEBRTCVAD_READY)
        self.keyword_spotter_enabled = bool(
            args.enable_keyword_spotter
            and bool(args.kws_model_dir)
            and bool(shutil.which(args.keyword_spotter_command))
            and bool(shutil.which(args.keyword_spotter_cli_command))
        )
        self.kws_assets_ready = False
        self.wake_listen_enabled = bool(
            args.enable_wake_listen and (self.keyword_spotter_enabled or self.local_stt_enabled or self.cloud_speech_enabled)
        )
        self.direct_llm_enabled = bool(args.enable_direct_llm and args.llm_api_key and args.llm_base_url and args.llm_model)
        self.openclaw_enabled = bool(args.enable_openclaw and args.openclaw_command)
        self.audio_lock = threading.RLock()
        self.playback_lock = threading.RLock()
        self.turn_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.playback_interrupt_event = threading.Event()
        self.manual_capture_active = threading.Event()
        self.listener_thread: threading.Thread | None = None
        self.manual_capture_thread: threading.Thread | None = None
        self.current_playback_process: Any | None = None
        self.current_playback_path: str | None = None
        self.pending_wake_request: dict[str, Any] | None = None
        self.muted_until = 0.0
        self.wake_tone_path = self.build_wake_tone_file()
        self.tts_cache_dir = Path(args.tts_cache_dir)
        self.webrtcvad = webrtcvad.Vad(args.vad_mode) if self.webrtcvad_enabled and webrtcvad is not None else None
        if self.cloud_speech_enabled and dashscope is not None:
            dashscope.api_key = args.dashscope_api_key
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)
        if self.local_stt_enabled:
            try:
                self.startup_log(f"loading wake whisper model: {args.wake_whisper_model or args.whisper_model}")
                self.get_whisper_model(stage="wake")
                self.startup_log("wake whisper model ready")
            except Exception:
                self.local_stt_enabled = False
                self.startup_log("wake whisper model unavailable; local STT disabled")
                self.wake_listen_enabled = bool(
                    args.enable_wake_listen and (self.keyword_spotter_enabled or self.local_stt_enabled or self.cloud_speech_enabled)
                )
        if self.keyword_spotter_enabled:
            try:
                self.startup_log("preparing keyword spotter assets")
                self.prepare_keyword_spotter_assets()
                self.startup_log("keyword spotter assets ready")
            except Exception:
                self.keyword_spotter_enabled = False
                self.startup_log("keyword spotter disabled due to asset preparation failure")
                self.wake_listen_enabled = bool(args.enable_wake_listen and (self.local_stt_enabled or self.cloud_speech_enabled))
        self.startup_log("prewarming cached replies")
        self.prewarm_cached_replies()
        self.startup_log("voice agent init done")

    def run(self) -> None:
        if self.wake_listen_enabled:
            self.start_background_listener()
        self.startup_log(f"starting HTTP server on {self.args.host}:{self.args.port}")
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                if self.path.startswith("/health"):
                    self.respond(HTTPStatus.OK, outer.health())
                    return
                if self.path.startswith("/config"):
                    self.respond(HTTPStatus.OK, outer.config())
                    return
                self.respond(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def do_POST(self) -> None:
                if self.path.startswith("/command"):
                    payload = self.read_json()
                    speak_reply = bool(payload.get("speakReply", False))
                    outcome = outer.listenless_handle(str(payload.get("text", "")).strip(), speak_reply=speak_reply)
                    self.respond(HTTPStatus.OK, outer.outcome_payload(outcome))
                    return
                if self.path.startswith("/manual-wake"):
                    payload = self.read_json()
                    speak_reply = bool(payload.get("speakReply", True))
                    try:
                        outcome = outer.manual_wake(speak_reply=speak_reply)
                        self.respond(HTTPStatus.OK, outer.outcome_payload(outcome))
                    except Exception as exc:
                        self.respond(HTTPStatus.BAD_GATEWAY, outer.error_payload(f"手动唤醒失败：{exc}"))
                    return
                if self.path.startswith("/listen-command"):
                    payload = self.read_json()
                    duration = clamp_record_seconds(float(payload.get("durationSeconds", outer.args.record_seconds)))
                    speak_reply = bool(payload.get("speakReply", True))
                    try:
                        outcome = outer.listen_and_handle(duration_seconds=duration, speak_reply=speak_reply)
                        self.respond(HTTPStatus.OK, outer.outcome_payload(outcome))
                    except Exception as exc:
                        self.respond(HTTPStatus.BAD_GATEWAY, outer.error_payload(f"语音识别失败：{exc}"))
                    return
                if self.path.startswith("/speak"):
                    payload = self.read_json()
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        self.respond(HTTPStatus.BAD_REQUEST, outer.error_payload("请输入要播报的文本。"))
                        return
                    try:
                        audio_path = outer.speak_text(text)
                        outer.status = outer.idle_status()
                        outer.updated_at = iso_now()
                        self.respond(HTTPStatus.OK, {**outer.health(), "reply": f"已播报：{text}", "audioPath": audio_path})
                    except PlaybackInterrupted:
                        outer.updated_at = iso_now()
                        self.respond(HTTPStatus.OK, {**outer.health(), "reply": "当前播报已被新的唤醒打断。", "audioPath": outer.last_audio_path})
                    except Exception as exc:
                        self.respond(HTTPStatus.BAD_GATEWAY, outer.error_payload(f"语音播报失败：{exc}"))
                    return
                if self.path.startswith("/config/wake-word"):
                    payload = self.read_json()
                    wake_word = str(payload.get("wakeWord", "")).strip()
                    if not wake_word:
                        self.respond(HTTPStatus.BAD_REQUEST, outer.error_payload("wakeWord 不能为空。"))
                        return
                    self.respond(HTTPStatus.OK, outer.update_wake_word(wake_word))
                    return
                if self.path.startswith("/memory/clear"):
                    self.respond(HTTPStatus.OK, outer.clear_memory(clear_visible_turn=True))
                    return
                self.respond(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except json.JSONDecodeError:
                    return {}

            def respond(self, status: int, payload: dict[str, Any]) -> None:
                data = json_dumps(payload)
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    return

        ThreadingHTTPServer((self.args.host, self.args.port), Handler).serve_forever()

    def startup_log(self, message: str) -> None:
        print(f"[voice-agent] {message}", flush=True)

    def start_background_listener(self) -> None:
        # 常驻监听线程在服务启动后运行，使前端不用每次手动调用录音接口。
        if self.listener_thread and self.listener_thread.is_alive():
            return
        self.status = self.idle_status()
        self.updated_at = iso_now()
        self.listener_thread = threading.Thread(target=self.wake_listen_loop, name="smartpi-wake-listener", daemon=True)
        self.listener_thread.start()

    def wake_listen_loop(self) -> None:
        # 唤醒词循环采用短窗录音，命中后才进入较长的命令录音阶段，减少无效 STT 调用。
        while not self.stop_event.is_set():
            try:
                if self.manual_capture_active.is_set():
                    time.sleep(0.05)
                    continue
                if self.status in {"AWAKENED", "LISTENING_COMMAND", "PROCESSING"}:
                    time.sleep(0.05)
                    continue
                if time.monotonic() < self.muted_until:
                    time.sleep(0.1)
                    continue

                if self.status != "SPEAKING" and not self.is_playing_audio():
                    self.status = self.idle_status()
                    self.updated_at = iso_now()
                wake_started = time.monotonic()
                with self.audio_lock:
                    wake_audio_path = self.record_audio(self.args.wake_listen_window_seconds)
                    if not self.audio_has_speech(wake_audio_path, rms_threshold=self.args.wake_rms_threshold):
                        continue
                    if self.keyword_spotter_enabled:
                        detected = self.detect_wake_keyword(wake_audio_path)
                        recognized_text = ""
                    else:
                        detected = False
                        recognized_text = self.transcribe_audio(wake_audio_path, allow_empty=True, stage="wake")

                wake_command = self.extract_wake_command(recognized_text) if not self.keyword_spotter_enabled else ("" if detected else None)
                if wake_command is None:
                    continue

                if self.status == "SPEAKING" or self.is_playing_audio():
                    self.request_wake_interrupt(
                        source="wake-word",
                        speak_reply=True,
                        empty_reply="已检测到唤醒词，但没有识别到后续命令。",
                        inline_command=wake_command or None,
                    )
                    time.sleep(max(0.1, self.args.wake_listen_cooldown_seconds))
                    continue

                self.begin_turn()
                self.last_wake_ms = int((time.monotonic() - wake_started) * 1000)
                self.last_wake_detected_at = iso_now()
                self.last_error = None
                self.status = "AWAKENED"
                self.updated_at = iso_now()

                if wake_command:
                    self.last_heard_text = wake_command
                    self.updated_at = iso_now()
                    self.handle_text_command(wake_command, speak_reply=True)
                else:
                    self.capture_and_handle_post_wake(
                        speak_reply=True,
                        empty_reply="已检测到唤醒词，但没有识别到后续命令。",
                    )

                time.sleep(max(0.1, self.args.wake_listen_cooldown_seconds))
            except Exception as exc:
                self.last_error = f"常驻监听异常：{exc}"
                self.status = "ERROR"
                self.updated_at = iso_now()
                self.finish_turn()
                time.sleep(max(0.6, self.args.wake_listen_cooldown_seconds))

    def health(self) -> dict[str, Any]:
        return {
            "voiceAssistantStatus": self.status,
            "lastVoiceCommand": self.last_command,
            "lastReply": self.last_reply,
            "lastError": self.last_error,
            "lastAudioPath": self.last_audio_path,
            "lastHeardText": self.last_heard_text,
            "lastWakeDetectedAt": self.last_wake_detected_at,
            "wakeWord": self.args.wake_word,
            "wakeWordAliases": self.wake_word_aliases,
            "assistantName": self.args.assistant_name,
            "cloudSpeechEnabled": self.cloud_speech_enabled,
            "localSttEnabled": self.local_stt_enabled,
            "localTtsEnabled": self.local_tts_enabled,
            "remoteTtsEnabled": self.remote_tts_enabled,
            "remoteTtsModel": self.args.remote_tts_model if self.remote_tts_enabled else None,
            "wakeListeningEnabled": self.wake_listen_enabled,
            "keywordSpotterEnabled": self.keyword_spotter_enabled,
            "kwsAssetsReady": self.kws_assets_ready,
            "dashscopeReady": DASHSCOPE_READY,
            "fasterWhisperReady": FASTER_WHISPER_READY,
            "webrtcvadReady": WEBRTCVAD_READY,
            "directLlmEnabled": self.direct_llm_enabled,
            "llmModel": self.args.llm_model if self.direct_llm_enabled else None,
            "openClawEnabled": self.openclaw_enabled,
            "turnId": self.turn_id,
            "turnStartedAt": self.turn_started_at,
            "turnFinishedAt": self.turn_finished_at,
            "lastWakeMs": self.last_wake_ms,
            "lastRecordMs": self.last_record_ms,
            "lastSttMs": self.last_stt_ms,
            "lastRouteMs": self.last_route_ms,
            "lastLlmMs": self.last_llm_ms,
            "lastTtsMs": self.last_tts_ms,
            "lastTtsSynthesisMs": self.last_tts_synthesis_ms,
            "lastTtsPlaybackLaunchMs": self.last_tts_playback_launch_ms,
            "lastTtsLeadingSilenceMs": self.last_tts_leading_silence_ms,
            "ttsLatencyRule": "llm_to_first_audio_ms",
            "lastEndToEndMs": self.last_end_to_end_ms,
            "audioPipelineMode": self.audio_pipeline_mode(),
            "memoryEnabled": self.memory_enabled,
            "memoryTurnCount": self.memory_turn_count,
            "memoryUpdatedAt": self.memory_updated_at,
            "updatedAt": self.updated_at,
        }

    def config(self) -> dict[str, Any]:
        return {
            "wakeWord": self.args.wake_word,
            "wakeWordAliases": self.wake_word_aliases,
            "assistantName": self.args.assistant_name,
            "updatedAt": self.updated_at,
        }

    def audio_pipeline_mode(self) -> str:
        stt_mode = self.last_stt_provider or (
            "keyword-spotter"
            if self.keyword_spotter_enabled
            else ("local-stt" if self.local_stt_enabled else ("cloud-stt" if self.cloud_speech_enabled else "stt-unavailable"))
        )
        tts_mode = self.last_tts_provider or (
            "local-tts"
            if self.local_tts_enabled
            else ("remote-openai-tts" if self.remote_tts_enabled else ("cloud-tts" if self.cloud_speech_enabled else "tts-unavailable"))
        )
        return f"{stt_mode}/{tts_mode}"

    def update_wake_word(self, wake_word: str) -> dict[str, Any]:
        self.args.wake_word = wake_word
        if self.keyword_spotter_enabled:
            self.prepare_keyword_spotter_assets()
        self.updated_at = iso_now()
        return {**self.health(), "wakeWord": self.args.wake_word}

    def clear_memory(self, clear_visible_turn: bool = False) -> dict[str, Any]:
        # 清空运行期会话记忆，用于前端语音区“清空记忆”按钮。
        with self.memory_lock:
            self.conversation_summary = ""
            self.recent_turns = []
            self.memory_turn_count = 0
            self.memory_updated_at = iso_now()
            self.voice_context_cache = None
            self.voice_context_cache_expires_at = 0.0

        if clear_visible_turn:
            self.turn_id = None
            self.turn_started_at = None
            self.turn_finished_at = None
            self.last_heard_text = None
            self.last_command = None
            self.last_reply = None
            self.last_audio_path = None
            self.last_error = None
            self.last_record_ms = None
            self.last_stt_ms = None
            self.last_route_ms = None
            self.last_llm_ms = None
            self.last_tts_ms = None
            self.last_tts_synthesis_ms = None
            self.last_tts_playback_launch_ms = None
            self.last_tts_leading_silence_ms = None
            self.last_end_to_end_ms = None
            self.last_stt_provider = None
            self.last_tts_provider = None
            self.status = self.idle_status()
        self.updated_at = iso_now()
        return self.health()

    def outcome_payload(self, outcome: CommandOutcome) -> dict[str, Any]:
        return {
            **self.health(),
            "reply": outcome.reply,
            "recognizedText": outcome.recognized_text,
            "audioPath": outcome.audio_path,
        }

    def error_payload(self, message: str) -> dict[str, Any]:
        self.status = "ERROR"
        self.last_error = message
        self.updated_at = iso_now()
        return {**self.health(), "reply": message}

    def begin_turn(self) -> None:
        self.turn_id = f"voice-turn-{int(time.time() * 1000)}"
        self.turn_started_at = iso_now()
        self.turn_finished_at = None
        self.last_record_ms = None
        self.last_stt_ms = None
        self.last_route_ms = None
        self.last_llm_ms = None
        self.last_tts_ms = None
        self.last_tts_synthesis_ms = None
        self.last_tts_playback_launch_ms = None
        self.last_tts_leading_silence_ms = None
        self.last_end_to_end_ms = None
        self.last_stt_provider = None
        self.last_tts_provider = None
        self.updated_at = iso_now()

    def finish_turn(self) -> None:
        self.turn_finished_at = iso_now()
        if self.turn_started_at:
            started_at = datetime.fromisoformat(self.turn_started_at)
            self.last_end_to_end_ms = int((datetime.now(timezone.utc).astimezone() - started_at).total_seconds() * 1000)
        self.status = self.idle_status()
        self.updated_at = iso_now()
        self.launch_pending_wake_request_if_any()

    def request_wake_interrupt(
        self,
        source: str,
        speak_reply: bool,
        empty_reply: str,
        inline_command: str | None = None,
    ) -> bool:
        queued = False
        normalized_command = inline_command.strip() if inline_command else None
        with self.turn_lock:
            if self.pending_wake_request is None:
                self.pending_wake_request = {
                    "source": source,
                    "speak_reply": speak_reply,
                    "empty_reply": empty_reply,
                    "inline_command": normalized_command,
                }
                queued = True
            elif normalized_command and not self.pending_wake_request.get("inline_command"):
                self.pending_wake_request["inline_command"] = normalized_command
                queued = True
        interrupted = self.interrupt_playback()
        if queued:
            self.updated_at = iso_now()
        return interrupted or queued

    def launch_pending_wake_request_if_any(self) -> None:
        with self.turn_lock:
            if self.pending_wake_request is None or self.manual_capture_active.is_set():
                return
            request_payload = self.pending_wake_request
            self.pending_wake_request = None

        self.begin_turn()
        self.last_wake_ms = 0
        self.last_wake_detected_at = iso_now()
        self.last_error = None
        self.status = "AWAKENED"
        self.updated_at = iso_now()
        self.manual_capture_active.set()
        self.manual_capture_thread = threading.Thread(
            target=self.capture_and_handle_post_wake_async,
            args=(
                bool(request_payload.get("speak_reply", True)),
                str(request_payload.get("empty_reply", "已检测到唤醒词，但没有识别到后续命令。")),
                request_payload.get("inline_command"),
            ),
            name="smartpi-pending-wake-capture",
            daemon=True,
        )
        self.manual_capture_thread.start()

    def interrupt_playback(self) -> bool:
        with self.playback_lock:
            process = self.current_playback_process
            if process is None or process.poll() is not None:
                return False
            self.playback_interrupt_event.set()
            try:
                process.terminate()
            except Exception:
                return False
        return True

    def is_playing_audio(self) -> bool:
        with self.playback_lock:
            process = self.current_playback_process
            return bool(process is not None and process.poll() is None)

    def prewarm_cached_replies(self) -> None:
        if not self.local_tts_enabled:
            return

        for phrase in (
            "已为你打开摄像头识别。",
            "已关闭摄像头识别。",
            "正在读取最近分析结果。",
            "当前暂无可用数据。",
        ):
            cache_path = self.cached_tts_path(phrase)
            if cache_path.exists():
                continue
            try:
                self.generate_local_tts(phrase, cache_path)
            except Exception:
                return

    def locate_kws_model_files(self) -> dict[str, str]:
        model_dir = Path(self.args.kws_model_dir)
        if not model_dir.is_dir():
            raise RuntimeError(f"关键词模型目录不存在：{model_dir}")

        def find_file(patterns: tuple[str, ...]) -> Path:
            for pattern in patterns:
                matches = sorted(model_dir.glob(pattern))
                if matches:
                    return matches[0]
            raise RuntimeError(f"在 {model_dir} 中找不到关键词模型文件：{patterns}")

        encoder = find_file(("encoder-epoch-*.int8.onnx", "encoder-epoch-*.onnx", "*encoder*.int8.onnx", "*encoder*.onnx"))
        decoder = find_file(("decoder-epoch-*.int8.onnx", "decoder-epoch-*.onnx", "*decoder*.int8.onnx", "*decoder*.onnx"))
        joiner = find_file(("joiner-epoch-*.int8.onnx", "joiner-epoch-*.onnx", "*joiner*.int8.onnx", "*joiner*.onnx"))
        tokens = find_file(("tokens.txt",))
        return {
            "encoder": str(encoder),
            "decoder": str(decoder),
            "joiner": str(joiner),
            "tokens": str(tokens),
        }

    def prepare_keyword_spotter_assets(self) -> None:
        if not self.keyword_spotter_enabled:
            return

        model_files = self.locate_kws_model_files()
        model_dir = Path(self.args.kws_model_dir)
        tokens_type = self.resolve_kws_tokens_type(model_dir)
        raw_keywords_path = model_dir / "smartpi_keywords_raw.txt"
        keywords_path = model_dir / "smartpi_keywords.txt"
        aliases = self.iter_wake_words()
        raw_lines = [f"{alias} @{alias.replace(' ', '_')}" for alias in aliases]
        raw_keywords_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

        command = [
            self.args.keyword_spotter_cli_command,
            "text2token",
            "--tokens",
            model_files["tokens"],
            "--tokens-type",
            tokens_type,
        ]
        lexicon_path = model_dir / "lexicon.txt"
        if tokens_type == "phone+ppinyin" and lexicon_path.is_file():
            command.extend(["--lexicon", str(lexicon_path)])
        command.extend([str(raw_keywords_path), str(keywords_path)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "关键词表生成失败")

        self.kws_assets_ready = True

    def resolve_kws_tokens_type(self, model_dir: Path) -> str:
        configured = self.args.kws_tokens_type.strip()
        if configured:
            return configured

        config_path = model_dir / "configuration.json"
        if config_path.is_file():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                modeling_unit = str(payload.get("modeling_unit", "")).strip()
                if modeling_unit:
                    return modeling_unit
            except Exception:
                pass
        return "ppinyin"

    def detect_wake_keyword(self, audio_path: str) -> bool:
        if not self.keyword_spotter_enabled or not self.kws_assets_ready:
            return False

        model_files = self.locate_kws_model_files()
        keywords_path = Path(self.args.kws_model_dir) / "smartpi_keywords.txt"
        command = [
            self.args.keyword_spotter_command,
            f"--encoder={model_files['encoder']}",
            f"--decoder={model_files['decoder']}",
            f"--joiner={model_files['joiner']}",
            f"--tokens={model_files['tokens']}",
            f"--keywords-file={keywords_path}",
            f"--keywords-score={self.args.kws_keywords_score}",
            f"--keywords-threshold={self.args.kws_keywords_threshold}",
            f"--num-threads={self.args.kws_num_threads}",
            audio_path,
        ]
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=max(5.0, self.args.wake_listen_window_seconds + 5))
        self.last_wake_ms = int((time.monotonic() - started) * 1000)
        self.last_stt_provider = "keyword-spotter"
        if result.returncode != 0:
            self.last_error = f"关键词唤醒检测失败：{result.stderr.strip() or result.stdout.strip()}"
            return False

        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        for line in output.splitlines():
            cleaned = line.strip()
            if not cleaned or not cleaned.startswith("{"):
                continue
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            keyword = str(payload.get("keyword", "")).strip()
            if keyword and keyword in self.iter_wake_words():
                return True
        return False

    def cached_tts_path(self, text: str) -> Path:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return self.tts_cache_dir / f"tts_{digest}.wav"

    def detect_leading_silence_ms(self, audio_path: str, threshold: int = 512) -> int:
        try:
            with wave.open(audio_path, "rb") as wav_file:
                frame_rate = wav_file.getframerate() or 16000
                channels = max(1, wav_file.getnchannels())
                sample_width = wav_file.getsampwidth()
                frame_count = wav_file.getnframes()
                if frame_count <= 0:
                    return 0
                if sample_width != 2:
                    return 0
                raw = wav_file.readframes(frame_count)
        except Exception:
            return 0

        if not raw:
            return 0

        samples = struct.iter_unpack("<h", raw)
        sample_index = 0
        for sample in samples:
            value = abs(sample[0])
            if value >= threshold:
                frame_index = sample_index // channels
                return int(frame_index * 1000 / frame_rate)
            sample_index += 1

        return int(frame_count * 1000 / frame_rate)

    def play_audio(self, audio_path: str) -> tuple[int, int]:
        cmd = ["aplay", "-D", self.args.playback_device, "-q", audio_path]
        started = time.monotonic()
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        launch_ms = int((time.monotonic() - started) * 1000)
        self.playback_interrupt_event.clear()
        with self.playback_lock:
            self.current_playback_process = process
            self.current_playback_path = audio_path
        try:
            deadline = time.monotonic() + 30
            stdout = ""
            stderr = ""
            while True:
                if self.playback_interrupt_event.is_set():
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    try:
                        stdout, stderr = process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                    raise PlaybackInterrupted("当前播报已被新的唤醒打断。")
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        process.kill()
                        stdout, stderr = process.communicate()
                        raise RuntimeError("音频播放超时")
                    continue
            total_ms = int((time.monotonic() - started) * 1000)
        finally:
            with self.playback_lock:
                if self.current_playback_process is process:
                    self.current_playback_process = None
                    self.current_playback_path = None
            self.playback_interrupt_event.clear()
        if process.returncode != 0:
            raise RuntimeError((stderr or stdout or "音频播放失败").strip())
        return launch_ms, total_ms

    def set_tts_latency(self, synthesis_ms: int, playback_launch_ms: int, leading_silence_ms: int, provider: str, audio_path: str) -> None:
        self.last_tts_synthesis_ms = max(0, synthesis_ms)
        self.last_tts_playback_launch_ms = max(0, playback_launch_ms)
        self.last_tts_leading_silence_ms = max(0, leading_silence_ms)
        self.last_tts_ms = self.last_tts_synthesis_ms + self.last_tts_playback_launch_ms + self.last_tts_leading_silence_ms
        self.last_tts_provider = provider
        self.last_audio_path = audio_path
        self.last_error = None
        self.muted_until = time.monotonic() + max(0.6, self.args.wake_listen_cooldown_seconds)

    def remote_tts_endpoint(self) -> str:
        base = (self.args.remote_tts_base_url or "").strip().rstrip("/")
        if not base:
            raise RuntimeError("远程 TTS 服务地址未配置。")
        if base.endswith("/v1/audio/speech"):
            return base
        return f"{base}/v1/audio/speech"

    def listenless_handle(self, text: str, speak_reply: bool) -> CommandOutcome:
        if not text:
            return self.reply("请先提供一条语音识别后的文本命令。", status="ERROR")
        self.begin_turn()
        self.last_heard_text = text
        self.updated_at = iso_now()
        return self.handle_text_command(text, speak_reply=speak_reply)

    def handle_text_command(self, text: str, speak_reply: bool = False) -> CommandOutcome:
        if not text:
            self.finish_turn()
            return self.reply("请先提供一条语音识别后的文本命令。", status="ERROR")

        if not self.turn_id:
            self.begin_turn()

        self.status = "PROCESSING"
        self.last_command = text
        self.last_heard_text = text
        self.last_error = None
        self.updated_at = iso_now()

        try:
            route_started = time.monotonic()
            reply_text = self.route_command(text)
            self.last_route_ms = int((time.monotonic() - route_started) * 1000)
            self.last_reply = reply_text
            self.updated_at = iso_now()
            audio_path: str | None = None
            if speak_reply and reply_text:
                try:
                    audio_path = self.speak_text(reply_text)
                except PlaybackInterrupted:
                    self.last_error = None
                    self.updated_at = iso_now()
                except Exception as exc:
                    self.last_error = f"语音播报失败：{exc}"
                    self.updated_at = iso_now()
            outcome = CommandOutcome(reply=reply_text, recognized_text=text, audio_path=audio_path)
            self.finish_turn()
            return outcome
        except Exception as exc:
            self.last_error = f"语音命令执行失败：{exc}"
            self.last_reply = self.last_error
            self.updated_at = iso_now()
            self.finish_turn()
            return CommandOutcome(reply=self.last_error, status="ERROR", recognized_text=text)

    def listen_and_handle(self, duration_seconds: float, speak_reply: bool = True) -> CommandOutcome:
        # 调试接口：直接录一段固定或 VAD 早停的命令音频，再进入文本命令处理流程。
        if not (self.local_stt_enabled or self.cloud_speech_enabled):
            raise RuntimeError("本地与云端语音识别都未启用。")
        self.begin_turn()
        with self.audio_lock:
            record_started = time.monotonic()
            audio_path = self.record_command_audio(duration_seconds)
            self.last_record_ms = int((time.monotonic() - record_started) * 1000)
            recognized_text = self.transcribe_audio(audio_path, stage="command")
        self.last_heard_text = recognized_text
        self.updated_at = iso_now()
        outcome = self.handle_text_command(recognized_text, speak_reply=speak_reply)
        outcome.recognized_text = recognized_text
        if not outcome.audio_path:
            outcome.audio_path = audio_path
        return outcome

    def manual_wake(self, speak_reply: bool = True) -> CommandOutcome:
        # 手动唤醒接口：前端按钮触发，绕过唤醒词检测，适合答辩演示和排查唤醒不灵敏问题。
        if not (self.local_stt_enabled or self.cloud_speech_enabled):
            raise RuntimeError("本地与云端语音识别都未启用。")

        if self.status == "SPEAKING" or self.is_playing_audio():
            self.request_wake_interrupt(
                source="manual-wake",
                speak_reply=speak_reply,
                empty_reply="已手动唤醒，但没有识别到后续命令。",
            )
            return CommandOutcome(reply="已打断当前播报，请直接对树莓派麦克风说命令。", status="AWAKENED")

        active_states = {"AWAKENED", "LISTENING_COMMAND", "PROCESSING"}
        if self.status in active_states or self.manual_capture_active.is_set():
            return CommandOutcome(reply="语音助手正在处理上一条命令，请稍后再试。", status=self.status)

        self.begin_turn()
        self.last_wake_ms = 0
        self.last_wake_detected_at = iso_now()
        self.last_error = None
        self.status = "AWAKENED"
        self.updated_at = iso_now()
        self.manual_capture_active.set()
        self.manual_capture_thread = threading.Thread(
            target=self.capture_and_handle_post_wake_async,
            args=(speak_reply, "已手动唤醒，但没有识别到后续命令。"),
            name="smartpi-manual-capture",
            daemon=True,
        )
        self.manual_capture_thread.start()
        return CommandOutcome(reply="已手动唤醒语音助手，请直接对树莓派麦克风说命令。", status="AWAKENED")

    def capture_and_handle_post_wake_async(self, speak_reply: bool, empty_reply: str, inline_command: str | None = None) -> None:
        try:
            self.capture_and_handle_post_wake(speak_reply=speak_reply, empty_reply=empty_reply, inline_command=inline_command)
        except Exception as exc:
            self.last_error = f"唤醒后命令采集失败：{exc}"
            self.last_reply = self.last_error
            self.updated_at = iso_now()
            self.finish_turn()
        finally:
            self.manual_capture_active.clear()

    def capture_and_handle_post_wake(self, speak_reply: bool, empty_reply: str, inline_command: str | None = None) -> CommandOutcome:
        # 唤醒后的主流程：播放提示音、采集命令、STT 转写、执行命令并可选播报回复。
        if inline_command:
            self.last_heard_text = inline_command
            self.updated_at = iso_now()
            return self.handle_text_command(inline_command, speak_reply=speak_reply)

        self.play_wake_tone()
        self.status = "LISTENING_COMMAND"
        self.updated_at = iso_now()
        with self.audio_lock:
            record_started = time.monotonic()
            command_audio_path = self.record_command_audio(self.args.command_max_record_seconds)
            self.last_record_ms = int((time.monotonic() - record_started) * 1000)
            command_text = self.transcribe_audio(command_audio_path, allow_empty=True, stage="command")

        if command_text:
            self.last_heard_text = command_text
            self.updated_at = iso_now()
            outcome = self.handle_text_command(command_text, speak_reply=speak_reply)
            if not outcome.audio_path:
                outcome.audio_path = command_audio_path
            return outcome

        self.last_reply = empty_reply
        self.last_audio_path = command_audio_path
        self.updated_at = iso_now()
        self.finish_turn()
        return CommandOutcome(reply=empty_reply, recognized_text="", audio_path=command_audio_path)

    def iter_wake_words(self) -> list[str]:
        wake_words = [self.args.wake_word, *self.wake_word_aliases]
        deduped: list[str] = []
        for wake_word in wake_words:
            cleaned = wake_word.strip()
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        return deduped

    def effective_wake_prompt(self) -> str | None:
        configured = self.wake_whisper_initial_prompt.strip()
        if configured and not contains_any(configured, ("摄像头", "分析", "心率", "血氧", "温度", "读取", "打开", "关闭")):
            return configured
        wake_words = "，".join(self.iter_wake_words())
        return wake_words or None

    def find_exact_wake_match(self, text: str) -> tuple[int, int] | None:
        normalized_text, index_map = normalize_match_mapping(text)
        if not normalized_text:
            return None

        best_match: tuple[int, int] | None = None
        for wake_word in self.iter_wake_words():
            normalized_wake_word = normalize_match_text(wake_word)
            if not normalized_wake_word:
                continue
            start_index = normalized_text.find(normalized_wake_word)
            if start_index < 0:
                continue
            if best_match is None or start_index < best_match[0]:
                best_match = (start_index, start_index + len(normalized_wake_word))

        if best_match is None:
            return None

        start_index, end_index = best_match
        if end_index <= 0 or end_index > len(index_map):
            return None
        return start_index, index_map[end_index - 1] + 1

    def find_fuzzy_wake_match(self, text: str) -> tuple[int, int] | None:
        normalized_text, index_map = normalize_match_mapping(text)
        if not normalized_text:
            return None

        prefix_window = max(1, self.args.wake_fuzzy_prefix_window_chars)
        max_distance = max(0, self.args.wake_fuzzy_max_distance)
        best_match: tuple[int, int, int] | None = None

        for wake_word in self.iter_wake_words():
            normalized_wake_word = normalize_match_text(wake_word)
            if not normalized_wake_word:
                continue
            candidate_length = len(normalized_wake_word)
            max_start = min(max(0, len(normalized_text) - candidate_length), prefix_window)
            for start_index in range(max_start + 1):
                segment = normalized_text[start_index : start_index + candidate_length]
                if len(segment) != candidate_length:
                    continue
                if not segment or segment[0] != normalized_wake_word[0]:
                    continue
                distance = edit_distance(segment, normalized_wake_word, max_distance=max_distance)
                if distance > max_distance:
                    continue
                candidate = (distance, start_index, start_index + candidate_length)
                if best_match is None or candidate < best_match:
                    best_match = candidate

        if best_match is None:
            return None

        _distance, start_index, end_index = best_match
        if end_index <= 0 or end_index > len(index_map):
            return None
        return start_index, index_map[end_index - 1] + 1

    def extract_wake_command(self, text: str) -> str | None:
        if not text:
            return None

        match = self.find_exact_wake_match(text) or self.find_fuzzy_wake_match(text)
        if match is None:
            return None

        _normalized_start, original_end = match
        tail = text[original_end:]
        return tail.strip(" ，。,.;；：:!！?？")

    def idle_status(self) -> str:
        return "AWAITING_WAKE_WORD" if self.wake_listen_enabled else "IDLE"

    def route_command(self, text: str) -> str:
        # 命令分流：设备控制优先走本地快路径，自由聊天再交给百炼或 OpenClaw。
        fallback_reply = self.route_command_locally(text)
        if fallback_reply:
            return fallback_reply

        if self.direct_llm_enabled:
            direct_reply, _action_executed = self.ask_direct_llm_reply(text)
            if direct_reply:
                return direct_reply
            if self.last_error:
                lowered = self.last_error.lower()
                if "free tier" in lowered or "额度" in self.last_error:
                    return "当前语音助手的自由对话模型额度已用尽，请稍后再试或切换到可用额度。"
                if "404 the model" in lowered or "does not exist" in lowered:
                    return "当前语音助手的自由对话模型配置异常，请检查百炼模型配置。"

        if self.openclaw_enabled:
            openclaw_reply, _action_executed = self.ask_openclaw_reply(text)
            if openclaw_reply:
                return openclaw_reply
            if self.last_error:
                lowered = self.last_error.lower()
                if "free tier" in lowered or "额度" in self.last_error:
                    return "当前语音助手的自由对话模型额度已用尽，请稍后再试或切换到可用额度。"
                if "404 the model" in lowered or "does not exist" in lowered:
                    return "当前语音助手的自由对话模型配置异常，请检查 OpenClaw 模型配置。"
        return "我听到了，但当前无法完成这个请求。"

    def is_probably_device_command(self, text: str) -> bool:
        normalized = text.replace(" ", "")
        return contains_any(
            normalized,
            (
                "摄像头",
                "相机",
                "识别",
                "测温",
                "温度检测",
                "心率",
                "血氧",
                "分析结果",
                "重新分析",
                "触发分析",
            ),
        )

    def route_command_locally(self, text: str) -> str | None:
        # 本地快路径通过关键词和近义表达匹配常见控制命令，降低摄像头和传感器控制延迟。
        normalized = text.replace(" ", "")

        if (
            contains_any(normalized, ("打开摄像头", "开启摄像头", "打开相机", "开启相机识别", "开始看舌头", "开始舌象识别", "打开识别"))
            or (contains_any(normalized, ("摄像头", "相机")) and contains_any(normalized, ("打开", "开启", "启动")))
        ):
            return self.execute_action("camera.start")

        if (
            contains_any(normalized, ("关闭摄像头", "停止识别", "别看了", "结束摄像头识别", "关掉相机识别", "关闭相机"))
            or (contains_any(normalized, ("摄像头", "相机")) and contains_any(normalized, ("关闭", "关掉", "停止", "结束")))
        ):
            return self.execute_action("camera.stop")

        if contains_any(normalized, ("打开温度检测", "开始测温", "打开体温检测", "测一下温度", "开始温度检测", "启动温度检测")):
            return self.execute_action("sensor.temperature.start")

        if contains_any(normalized, ("关闭温度检测", "停止测温", "关闭体温检测", "结束温度检测")):
            return self.execute_action("sensor.temperature.stop")

        if contains_any(normalized, ("打开心率血氧检测", "测心率", "测血氧", "开始夹手指", "开始测心率和血氧", "打开心率检测", "启动心率血氧检测")):
            return self.execute_action("sensor.pulseox.start")

        if contains_any(normalized, ("关闭心率血氧检测", "停止测心率", "停止测血氧", "结束心率血氧检测", "关掉心率检测")):
            return self.execute_action("sensor.pulseox.stop")

        if contains_any(normalized, ("皮肤温度", "现在多少度", "读一下温度", "当前温度是多少", "温度多少")):
            return self.execute_action("telemetry.temperature.read")

        if contains_any(normalized, ("现在心率多少", "血氧怎么样", "读一下心率血氧", "当前心率和血氧是多少", "心率多少", "血氧多少", "心率血氧")):
            return self.execute_action("telemetry.pulseox.read")

        if contains_any(normalized, ("看看上次结果", "读一下分析", "告诉我分析结果", "最近一次舌象分析怎么样", "上次检查结果是什么", "最近一次分析结果", "上次结果")):
            return self.execute_action("analysis.latest")

        if contains_any(normalized, ("再分析一次", "重新看一下", "再测一遍", "重新分析", "再做一次分析", "重新触发分析")):
            return self.execute_action("analysis.trigger")
        return None

    def execute_action(self, action: str) -> str:
        # 具体动作通过 smartpi 边缘桥接服务执行，语音层不直接操作摄像头或 I2C 硬件。
        if action == "camera.start":
            self.bridge_post("/control/camera/start", {"profile": "low-latency"})
            return "已为你打开摄像头识别。"

        if action == "camera.stop":
            self.bridge_post("/control/camera/stop", {})
            return "已关闭摄像头识别。"

        if action == "sensor.temperature.start":
            self.bridge_post("/control/sensors/temperature/start", {})
            return "皮肤温度监测已开启。"

        if action == "sensor.temperature.stop":
            self.bridge_post("/control/sensors/temperature/stop", {})
            return "皮肤温度监测已关闭。"

        if action == "sensor.pulseox.start":
            self.bridge_post("/control/sensors/pulseox/start", {})
            return "心率血氧监测已开启。"

        if action == "sensor.pulseox.stop":
            self.bridge_post("/control/sensors/pulseox/stop", {})
            return "心率血氧监测已关闭。"
        if action == "telemetry.temperature.read":
            telemetry = self.bridge_get("/telemetry/latest")
            value = telemetry.get("skinTemperatureC")
            if value is None:
                return "当前还没有可用的皮肤温度数据。"
            return f"当前皮肤温度为 {value} 摄氏度。"

        if action == "telemetry.pulseox.read":
            telemetry = self.bridge_get("/telemetry/latest")
            heart_rate = telemetry.get("heartRate")
            spo2 = telemetry.get("spo2")
            if heart_rate is None and spo2 is None:
                return "当前还没有可用的心率血氧数据。"
            return f"当前心率 {heart_rate or '--'} 次每分钟，血氧 {spo2 or '--'} 百分比。"

        if action == "analysis.latest":
            latest = self.bridge_get("/analysis/latest")
            data = latest.get("data", latest)
            summary = data.get("symptomSummary") or data.get("postureSummary") or data.get("advice") or PLACEHOLDER_RESULT
            return f"最近一次舌象体态分析提示：{summary}"

        if action == "analysis.trigger":
            triggered = self.bridge_post("/analysis/trigger", {})
            self.invalidate_voice_context_cache()
            nested = triggered.get("data") if isinstance(triggered.get("data"), dict) else triggered
            analysis_id = nested.get("analysisId") if isinstance(nested, dict) else None
            suffix = f"，分析编号 {analysis_id}" if analysis_id else ""
            return f"已重新触发一次分析{suffix}。"

        return "当前命令未匹配到已支持的 smartpi 动作。"

    def invalidate_voice_context_cache(self) -> None:
        self.voice_context_cache = None
        self.voice_context_cache_expires_at = 0.0

    def get_voice_context(self, force_refresh: bool = False) -> dict[str, Any] | None:
        if not force_refresh and self.voice_context_cache and time.monotonic() < self.voice_context_cache_expires_at:
            return self.voice_context_cache
        try:
            context = self.bridge_get("/voice/context")
        except Exception:
            return self.voice_context_cache
        self.voice_context_cache = context
        self.voice_context_cache_expires_at = time.monotonic() + 60.0
        return context

    def render_recent_turns(self) -> str:
        lines: list[str] = []
        for index, turn in enumerate(self.recent_turns, start=1):
            user_text = turn.get("user", "").strip()
            assistant_text = turn.get("assistant", "").strip()
            if user_text:
                lines.append(f"第{index}轮用户：{user_text}")
            if assistant_text:
                lines.append(f"第{index}轮助手：{assistant_text}")
        return "\n".join(lines)

    def build_free_chat_messages(self, text: str) -> list[dict[str, str]]:
        # 自由聊天上下文会注入用户资料、最近三次历史分析和当前运行期记忆。
        messages: list[dict[str, str]] = [{"role": "system", "content": self.args.llm_system_prompt}]
        context_blocks: list[str] = []

        context = self.get_voice_context()
        if isinstance(context, dict):
            profile_summary = str(context.get("userProfileSummary") or "").strip()
            analyses_summary = str(context.get("recentAnalysesSummary") or "").strip()
            if profile_summary:
                context_blocks.append(f"用户资料：\n{profile_summary}")
            if analyses_summary:
                context_blocks.append(f"最近三次历史分析：\n{analyses_summary}")

        if self.conversation_summary.strip():
            context_blocks.append(f"当前会话摘要：\n{self.conversation_summary.strip()}")

        recent_turns_text = self.render_recent_turns()
        if recent_turns_text:
            context_blocks.append(f"最近自由聊天原文：\n{recent_turns_text}")

        if context_blocks:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下是本轮回答必须优先参考的背景信息。"
                        "当用户在询问近期身体状况、趋势变化或调理方向时，请优先依据这些事实回答。"
                        "如果信息不足，请明确说明依据不足，不要编造。"
                        "\n\n"
                        + "\n\n".join(context_blocks)
                    ),
                }
            )
        messages.append({"role": "user", "content": text})
        return messages

    def should_compress_reply(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        return len(normalized) > 120 or normalized.count("\n") > 1

    def direct_llm_completion(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        payload = {
            "model": self.args.llm_model,
            "messages": messages,
            "temperature": self.args.llm_temperature if temperature is None else temperature,
            # Raw DashScope HTTP expects these fields at top level. The OpenAI
            # SDK's extra_body wrapper is not expanded here, so nesting it keeps
            # Qwen thinking enabled and adds seconds of reasoning latency.
            "enable_thinking": False,
            "max_tokens": 220,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.args.llm_base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.args.llm_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        llm_started = time.monotonic()
        try:
            with request.urlopen(req, timeout=max(5.0, self.args.llm_timeout_seconds)) as resp:
                response_text = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            try:
                error_payload = json.loads(response_text).get("error", {})
                message = str(error_payload.get("message") or response_text).strip()
            except Exception:
                message = response_text.strip() or str(exc)
            raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
        elapsed_ms = int((time.monotonic() - llm_started) * 1000)
        self.last_llm_ms = elapsed_ms if self.last_llm_ms is None else self.last_llm_ms + elapsed_ms

        data = json.loads(response_text)
        error_payload = data.get("error")
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message") or error_payload.get("code") or "百炼模型调用失败").strip()
            raise RuntimeError(message)

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("百炼模型返回了空内容。")

        message_payload = choices[0].get("message", {})
        content = message_payload.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            reply_text = "".join(parts).strip()
        else:
            reply_text = str(content or "").strip()

        if not reply_text:
            raise RuntimeError("百炼模型返回了空内容。")

        lowered_reply = reply_text.lower()
        if (
            lowered_reply.startswith("403 ")
            or lowered_reply.startswith("404 ")
            or "free tier" in lowered_reply
            or "does not exist or you do not have access to it" in lowered_reply
            or "input data may contain inappropriate content" in lowered_reply
        ):
            raise RuntimeError(reply_text)

        return reply_text

    def compress_reply_for_voice(self, reply_text: str) -> str:
        if not self.should_compress_reply(reply_text):
            return reply_text.strip()
        try:
            compressed = self.direct_llm_completion(
                [
                    {"role": "system", "content": DEFAULT_REPLY_COMPRESSION_SYSTEM_PROMPT},
                    {"role": "user", "content": reply_text},
                ],
                temperature=0.2,
            ).strip()
            if compressed:
                return compressed
        except Exception:
            pass
        fallback = " ".join(reply_text.split()).strip()
        return fallback[:100].rstrip() + ("…" if len(fallback) > 100 else "")

    def should_summarize_memory(self) -> bool:
        if len(self.recent_turns) > 4:
            return True
        char_count = len(self.conversation_summary)
        for turn in self.recent_turns:
            char_count += len(turn.get("user", "")) + len(turn.get("assistant", ""))
        return char_count > 800 and len(self.recent_turns) > 2

    def summarize_memory_if_needed(self) -> None:
        if not self.should_summarize_memory():
            return
        older_turns = self.recent_turns[:-2]
        if not older_turns:
            return
        turn_text = []
        for turn in older_turns:
            user_text = turn.get("user", "").strip()
            assistant_text = turn.get("assistant", "").strip()
            if user_text:
                turn_text.append(f"用户：{user_text}")
            if assistant_text:
                turn_text.append(f"助手：{assistant_text}")
        if not turn_text:
            return
        prompt = "\n".join(turn_text)
        try:
            summary = self.direct_llm_completion(
                [
                    {"role": "system", "content": DEFAULT_MEMORY_SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"已有摘要：{self.conversation_summary or '无'}\n"
                            f"需要压缩的旧对话：\n{prompt}"
                        ),
                    },
                ],
                temperature=0.2,
            ).strip()
            if summary:
                self.conversation_summary = summary
                self.recent_turns = self.recent_turns[-2:]
                self.memory_updated_at = iso_now()
                return
        except Exception:
            pass
        self.recent_turns = self.recent_turns[-4:]
        self.memory_updated_at = iso_now()

    def remember_free_chat_turn(self, user_text: str, assistant_text: str) -> None:
        # 只记忆自由聊天，不记录设备控制命令；超长上下文会在 summarize_memory_if_needed 中压缩。
        with self.memory_lock:
            self.recent_turns.append(
                {
                    "user": user_text.strip(),
                    "assistant": assistant_text.strip(),
                    "createdAt": iso_now(),
                }
            )
            self.memory_turn_count += 1
            self.memory_updated_at = iso_now()
            self.summarize_memory_if_needed()

    def ask_openclaw_reply(self, text: str) -> tuple[str | None, bool]:
        if not self.openclaw_enabled:
            return None, False

        command = self.args.openclaw_command.format(text=shlex.quote(text))
        try:
            llm_started = time.monotonic()
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=max(3.0, self.args.openclaw_timeout_seconds),
            )
            self.last_llm_ms = int((time.monotonic() - llm_started) * 1000)
        except subprocess.TimeoutExpired:
            self.last_error = f"OpenClaw 调用超时（>{self.args.openclaw_timeout_seconds} 秒）"
            return None, False
        if result.returncode != 0:
            self.last_error = f"OpenClaw 调用失败：{result.stderr.strip() or result.stdout.strip()}"
            return None, False

        reply_text = (result.stdout or "").strip()
        if not reply_text:
            self.last_error = "OpenClaw 返回了空内容。"
            return None, False

        lowered_reply = reply_text.lower()
        if (
            lowered_reply.startswith("403 ")
            or lowered_reply.startswith("404 ")
            or "free tier" in lowered_reply
            or "does not exist or you do not have access to it" in lowered_reply
            or "embedded run failover decision" in lowered_reply
            or "input data may contain inappropriate content" in lowered_reply
        ):
            self.last_error = reply_text
            return None, False

        marker = ACTION_MARKER_RE.search(reply_text)
        if not marker:
            return reply_text, False

        action = marker.group(1).strip()
        clean_reply = ACTION_MARKER_RE.sub("", reply_text).strip()
        action_reply = self.execute_action(action)
        if clean_reply and clean_reply != action_reply:
            return f"{clean_reply}\n{action_reply}", True
        return action_reply, True

    def ask_direct_llm_reply(self, text: str) -> tuple[str | None, bool]:
        if not self.direct_llm_enabled:
            return None, False
        try:
            reply_text = self.direct_llm_completion(self.build_free_chat_messages(text))
        except Exception as exc:
            self.last_error = f"百炼模型调用失败：{exc}"
            return None, False

        marker = ACTION_MARKER_RE.search(reply_text)
        if not marker:
            final_reply = self.compress_reply_for_voice(reply_text)
            self.remember_free_chat_turn(text, final_reply)
            return final_reply, False

        action = marker.group(1).strip()
        clean_reply = ACTION_MARKER_RE.sub("", reply_text).strip()
        action_reply = self.execute_action(action)
        if clean_reply and clean_reply != action_reply:
            return f"{clean_reply}\n{action_reply}", True
        return action_reply, True

    def reply(self, text: str, status: str = "IDLE") -> CommandOutcome:
        self.status = self.idle_status() if status == "IDLE" else status
        self.last_reply = text
        self.updated_at = iso_now()
        return CommandOutcome(reply=text, status=status)

    def bridge_get(self, path: str) -> dict[str, Any]:
        req = request.Request(f"{self.args.bridge_base_url}{path}", method="GET")
        with request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def bridge_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.args.bridge_base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def record_audio(self, duration_seconds: float) -> str:
        duration_seconds = clamp_record_seconds(duration_seconds)
        duration_seconds_int = max(1, int(math.ceil(duration_seconds)))
        target = Path(tempfile.gettempdir()) / f"smartpi_voice_{int(time.time() * 1000)}.wav"
        cmd = [
            "arecord",
            "-q",
            "-D",
            self.args.record_device,
            "-d",
            str(duration_seconds_int),
            "-f",
            "S16_LE",
            "-r",
            str(self.args.record_sample_rate),
            "-c",
            "1",
            str(target),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_seconds_int + 8)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "录音失败")
        self.last_audio_path = str(target)
        return str(target)

    def record_command_audio(self, max_duration_seconds: float) -> str:
        # 命令录音使用 arecord 读取 USB 麦克风，并根据 VAD 静音时长提前结束录音。
        max_duration_seconds = clamp_record_seconds(max_duration_seconds)
        chunk_ms = self.args.vad_frame_ms if self.webrtcvad_enabled else 100
        sample_width = 2
        chunk_size = int(self.args.record_sample_rate * sample_width * chunk_ms / 1000)
        target = Path(tempfile.gettempdir()) / f"smartpi_voice_{int(time.time() * 1000)}.wav"
        command = [
            "arecord",
            "-q",
            "-D",
            self.args.record_device,
            "-f",
            "S16_LE",
            "-r",
            str(self.args.record_sample_rate),
            "-c",
            "1",
            "-t",
            "raw",
        ]

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        frames: list[bytes] = []
        speech_detected = False
        spoken_ms = 0
        silence_ms = 0
        start_time = time.monotonic()
        stderr_output = b""

        try:
            assert process.stdout is not None
            while time.monotonic() - start_time < max_duration_seconds:
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                frames.append(chunk)
                if self.chunk_contains_speech(chunk, sample_width):
                    speech_detected = True
                    spoken_ms += chunk_ms
                    silence_ms = 0
                elif speech_detected:
                    silence_ms += chunk_ms

                if speech_detected and spoken_ms >= self.args.command_min_speech_ms and silence_ms >= self.args.command_silence_stop_ms:
                    break
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                stdout_tail, stderr_tail = process.communicate(timeout=2)
                if stdout_tail:
                    frames.append(stdout_tail)
                stderr_output = stderr_tail or b""
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_tail, stderr_tail = process.communicate()
                if stdout_tail:
                    frames.append(stdout_tail)
                stderr_output = stderr_tail or b""

        if process.returncode not in (0, -15, 143) and not frames:
            fallback_error = stderr_output or "录音失败".encode("utf-8")
            raise RuntimeError(fallback_error.decode("utf-8", errors="ignore").strip() or "录音失败")

        with wave.open(str(target), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(self.args.record_sample_rate)
            wav_file.writeframes(b"".join(frames))

        self.last_audio_path = str(target)
        return str(target)

    def chunk_contains_speech(self, chunk: bytes, sample_width: int, rms_threshold: int | None = None) -> bool:
        if self.webrtcvad is not None:
            expected_frame_bytes = int(self.args.record_sample_rate * self.args.vad_frame_ms / 1000) * sample_width
            if len(chunk) == expected_frame_bytes:
                try:
                    return bool(self.webrtcvad.is_speech(chunk, self.args.record_sample_rate))
                except Exception:
                    pass
        threshold = self.args.command_rms_threshold if rms_threshold is None else rms_threshold
        return audioop.rms(chunk, sample_width) >= threshold

    def audio_has_speech(self, audio_path: str, rms_threshold: int | None = None) -> bool:
        sample_width = 2
        try:
            with wave.open(audio_path, "rb") as wav_file:
                frame_rate = wav_file.getframerate()
                sample_width = wav_file.getsampwidth()
                channels = wav_file.getnchannels()
                frame_ms = self.args.vad_frame_ms if self.webrtcvad_enabled else 100
                frame_count = int(frame_rate * frame_ms / 1000)
                while True:
                    chunk = wav_file.readframes(frame_count)
                    if not chunk:
                        break
                    if channels > 1:
                        chunk = audioop.tomono(chunk, sample_width, 1, 1)
                    if self.chunk_contains_speech(chunk, sample_width, rms_threshold=rms_threshold):
                        return True
        except Exception:
            return True
        return False

    def get_whisper_model(self, stage: str = "command") -> Any:
        if not self.local_stt_enabled:
            raise RuntimeError("本地 Whisper 未启用")
        model_name = self.args.wake_whisper_model if stage == "wake" and self.args.wake_whisper_model else self.args.whisper_model
        compute_type = self.args.wake_whisper_compute_type if stage == "wake" and self.args.wake_whisper_compute_type else self.args.whisper_compute_type
        cache_key = (model_name, self.args.whisper_device, compute_type)
        if cache_key not in self.whisper_models:
            assert WhisperModel is not None
            self.whisper_models[cache_key] = WhisperModel(
                model_name,
                device=self.args.whisper_device,
                compute_type=compute_type,
            )
        return self.whisper_models[cache_key]

    def transcribe_audio(self, audio_path: str, allow_empty: bool = False, stage: str = "command") -> str:
        # STT 支持本地 faster-whisper 和云端阿里云识别两种模式，实际耗时会写入状态接口。
        if self.local_stt_enabled:
            started = time.monotonic()
            model = self.get_whisper_model(stage=stage)
            initial_prompt = self.effective_wake_prompt() if stage == "wake" else self.whisper_initial_prompt
            segments, _info = model.transcribe(
                audio_path,
                language=self.args.whisper_language,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
                initial_prompt=initial_prompt or None,
            )
            transcript = "".join(segment.text for segment in segments).strip()
            self.last_stt_ms = int((time.monotonic() - started) * 1000)
            self.last_stt_provider = f"local-stt-{stage}"
            if not transcript and not allow_empty:
                raise RuntimeError("本地语音识别结果为空")
            return transcript

        if not self.cloud_speech_enabled:
            raise RuntimeError("本地与云端语音识别都未启用")
        assert Recognition is not None
        started = time.monotonic()
        recognizer = Recognition(
            model=self.args.asr_model,
            callback=None,
            format="wav",
            sample_rate=self.args.record_sample_rate,
        )
        result = recognizer.call(audio_path)
        sentence = result.get_sentence()
        transcript = self.extract_transcript(sentence).strip()
        self.last_stt_ms = int((time.monotonic() - started) * 1000)
        self.last_stt_provider = "cloud-stt"
        if not transcript and not allow_empty:
            raise RuntimeError("语音识别结果为空")
        return transcript

    def extract_transcript(self, sentence: Any) -> str:
        if sentence is None:
            return ""
        if isinstance(sentence, list):
            texts = []
            for item in sentence:
                if isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        texts.append(text)
            return "".join(texts)
        if isinstance(sentence, dict):
            return str(sentence.get("text", "")).strip()
        return str(sentence).strip()

    def speak_text(self, text: str) -> str:
        # TTS 统一返回可播放 wav 文件路径，优先缓存命中，再按本地、远程本机、云端顺序选择。
        cleaned_text = " ".join(text.split()).strip()
        if not cleaned_text:
            raise RuntimeError("语音播报文本为空")

        self.status = "SPEAKING"
        self.updated_at = iso_now()
        cached_path = self.cached_tts_path(cleaned_text)
        if cached_path.exists():
            leading_silence_ms = self.detect_leading_silence_ms(str(cached_path))
            playback_launch_ms, _ = self.play_audio(str(cached_path))
            self.set_tts_latency(0, playback_launch_ms, leading_silence_ms, "local-tts-cache", str(cached_path))
            return str(cached_path)

        if self.local_tts_enabled:
            started = time.monotonic()
            self.generate_local_tts(cleaned_text, cached_path)
            synthesis_ms = int((time.monotonic() - started) * 1000)
            leading_silence_ms = self.detect_leading_silence_ms(str(cached_path))
            playback_launch_ms, _ = self.play_audio(str(cached_path))
            self.set_tts_latency(synthesis_ms, playback_launch_ms, leading_silence_ms, "local-tts", str(cached_path))
            return str(cached_path)

        if self.remote_tts_enabled:
            started = time.monotonic()
            req = request.Request(
                self.remote_tts_endpoint(),
                data=json.dumps(
                    {
                        "model": self.args.remote_tts_model,
                        "input": cleaned_text,
                        "voice": self.args.remote_tts_voice,
                        "response_format": "wav",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=max(5.0, self.args.remote_tts_timeout_seconds)) as resp:
                    audio_bytes = resp.read()
                    content_type = str(resp.headers.get("Content-Type", "")).lower()
            except Exception as exc:
                raise RuntimeError(f"远程本机 TTS 调用失败：{exc}") from exc

            if not audio_bytes:
                raise RuntimeError("远程本机 TTS 返回了空音频。")

            if content_type.startswith("application/json") or audio_bytes[:1] == b"{":
                try:
                    payload = json.loads(audio_bytes.decode("utf-8"))
                except Exception:
                    raise RuntimeError("远程本机 TTS 返回了非音频错误内容。")
                detail = payload.get("detail") if isinstance(payload, dict) else payload
                raise RuntimeError(f"远程本机 TTS 返回错误：{detail}")

            cached_path.write_bytes(audio_bytes)
            synthesis_ms = int((time.monotonic() - started) * 1000)
            leading_silence_ms = self.detect_leading_silence_ms(str(cached_path))
            playback_launch_ms, _ = self.play_audio(str(cached_path))
            self.set_tts_latency(synthesis_ms, playback_launch_ms, leading_silence_ms, "remote-openai-tts", str(cached_path))
            return str(cached_path)

        if not self.cloud_speech_enabled:
            raise RuntimeError("本地与云端语音合成都未启用")

        assert TtsSynthesizer is not None and TtsAudioFormat is not None
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                started = time.monotonic()
                synthesizer = TtsSynthesizer(
                    model=self.args.tts_model,
                    voice=self.args.tts_voice,
                    format=TtsAudioFormat.WAV_16000HZ_MONO_16BIT,
                )
                audio_bytes = synthesizer.call(cleaned_text)
                if not audio_bytes:
                    raise RuntimeError("语音合成结果为空")
                cached_path.write_bytes(audio_bytes)
                synthesis_ms = int((time.monotonic() - started) * 1000)
                leading_silence_ms = self.detect_leading_silence_ms(str(cached_path))
                playback_launch_ms, _ = self.play_audio(str(cached_path))
                self.set_tts_latency(synthesis_ms, playback_launch_ms, leading_silence_ms, "cloud-tts", str(cached_path))
                return str(cached_path)
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    time.sleep(0.5 * attempt)
                    continue
        raise RuntimeError(str(last_exc) if last_exc else "语音播报失败")

    def generate_local_tts(self, text: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not self.piper_command_parts:
            raise RuntimeError("Piper 命令未配置。")
        command = [*self.piper_command_parts, "--model", self.args.piper_model_path, "--output_file", str(target)]
        if self.args.piper_config_path:
            command.extend(["--config", self.args.piper_config_path])
        result = subprocess.run(
            command,
            input=text,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not target.exists():
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Piper 语音合成失败")

    def build_wake_tone_file(self) -> str:
        target = Path(tempfile.gettempdir()) / "smartpi_wake_tone.wav"
        if target.exists():
            return str(target)

        sample_rate = 16000
        duration_seconds = 0.12
        frequency = 880.0
        amplitude = 12000
        frames = bytearray()
        frame_count = int(sample_rate * duration_seconds)
        for index in range(frame_count):
            sample = int(amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate))
            frames.extend(struct.pack("<h", sample))

        with wave.open(str(target), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(frames))
        return str(target)

    def play_wake_tone(self) -> None:
        try:
            self.play_audio(self.wake_tone_path)
            self.muted_until = time.monotonic() + 0.2
            if self.args.wake_ack_text:
                self.last_reply = self.args.wake_ack_text
                self.updated_at = iso_now()
        except Exception as exc:
            self.last_error = f"唤醒提示音失败：{exc}"
            self.updated_at = iso_now()


def main() -> None:
    VoiceAgent(build_parser().parse_args()).run()


if __name__ == "__main__":
    main()
