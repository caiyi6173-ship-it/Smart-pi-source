import argparse
import json
from urllib import error

from edge.smartpi_voice_agent import VoiceAgent


def make_args(**overrides):
    values = dict(
        host="127.0.0.1",
        port=8093,
        bridge_base_url="http://127.0.0.1:8092",
        wake_word="你好小智",
        assistant_name="smartpi Voice",
        record_device="default",
        playback_device="default",
        record_seconds=3.0,
        record_sample_rate=16000,
        dashscope_api_key="",
        asr_model="paraformer-realtime-v2",
        tts_model="cosyvoice-v2",
        tts_voice="longxiaochun_v2",
        enable_cloud_speech=False,
        enable_local_stt=False,
        enable_local_tts=False,
        enable_wake_listen=False,
        enable_keyword_spotter=False,
        wake_listen_window_seconds=1.8,
        wake_listen_command_seconds=5.0,
        command_max_record_seconds=5.0,
        command_silence_stop_ms=700,
        command_min_speech_ms=300,
        command_rms_threshold=220,
        wake_rms_threshold=160,
        enable_webrtcvad=False,
        vad_mode=1,
        vad_frame_ms=30,
        wake_listen_cooldown_seconds=0.25,
        wake_word_aliases="",
        wake_fuzzy_max_distance=1,
        wake_fuzzy_prefix_window_chars=8,
        wake_ack_text="",
        whisper_model="tiny",
        whisper_device="cpu",
        whisper_compute_type="int8",
        whisper_language="zh",
        whisper_initial_prompt="",
        wake_whisper_model="tiny",
        wake_whisper_compute_type="int8",
        wake_whisper_initial_prompt="",
        keyword_spotter_command="sherpa-onnx-keyword-spotter",
        keyword_spotter_cli_command="sherpa-onnx-cli",
        kws_model_dir="",
        kws_tokens_type="",
        kws_keywords_threshold=0.35,
        kws_keywords_score=1.8,
        kws_num_threads=2,
        kws_inline_command=False,
        piper_command="piper",
        piper_model_path="",
        piper_config_path="",
        tts_cache_dir="D:/RAG/Smart-pi-source/.tmp_tts_cache",
        enable_remote_tts=False,
        remote_tts_base_url="",
        remote_tts_model="tts-1",
        remote_tts_voice="smartpi",
        remote_tts_timeout_seconds=30,
        enable_direct_llm=False,
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        llm_timeout_seconds=20,
        llm_temperature=0.2,
        llm_system_prompt="",
        enable_openclaw=False,
        openclaw_command="",
        openclaw_timeout_seconds=12,
        enable_agent_orchestrator=True,
        agent_orchestrator_url="http://127.0.0.1:8096",
        agent_orchestrator_timeout_seconds=1,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def test_agent_orchestrator_reply_success(monkeypatch):
    def fake_urlopen(req, timeout):
        assert req.full_url == "http://127.0.0.1:8096/api/v1/agent/chat"
        body = json.loads(req.data.decode("utf-8"))
        assert body["message"] == "舌苔黄腻说明什么？"
        assert body["input_type"] == "voice"
        return FakeHttpResponse({"answer": "这是 Agent 回答。", "actions": []})

    monkeypatch.setattr("edge.smartpi_voice_agent.request.urlopen", fake_urlopen)
    agent = VoiceAgent(make_args())

    reply, action_planned = agent.ask_agent_orchestrator_reply("舌苔黄腻说明什么？")

    assert reply == "这是 Agent 回答。"
    assert action_planned is False


def test_agent_orchestrator_device_dry_run_is_not_executed(monkeypatch):
    def fake_urlopen(req, timeout):
        return FakeHttpResponse(
            {
                "answer": "已规划打开摄像头识别动作。",
                "actions": [
                    {
                        "action": "camera.start",
                        "action_marker": "[[SMARTPI_ACTION:camera.start]]",
                        "dry_run": True,
                        "executed": False,
                    }
                ],
            }
        )

    monkeypatch.setattr("edge.smartpi_voice_agent.request.urlopen", fake_urlopen)
    agent = VoiceAgent(make_args())

    reply, action_planned = agent.ask_agent_orchestrator_reply("打开摄像头识别")

    assert action_planned is True
    assert "[[SMARTPI_ACTION:camera.start]]" in reply
    assert "未执行" in reply


def test_agent_orchestrator_failure_returns_none(monkeypatch):
    def fake_urlopen(req, timeout):
        raise error.URLError("offline")

    monkeypatch.setattr("edge.smartpi_voice_agent.request.urlopen", fake_urlopen)
    agent = VoiceAgent(make_args())

    reply, action_planned = agent.ask_agent_orchestrator_reply("舌苔黄腻说明什么？")

    assert reply is None
    assert action_planned is False
    assert "Agent Orchestrator 调用失败" in agent.last_error


def test_route_command_prefers_agent_orchestrator(monkeypatch):
    agent = VoiceAgent(make_args())

    monkeypatch.setattr(
        agent,
        "ask_agent_orchestrator_reply",
        lambda text: ("已规划打开摄像头识别动作。\n已进入旁路规划模式，设备动作 camera.start 未执行。", True),
    )

    reply = agent.route_command("打开摄像头识别")

    assert "旁路规划模式" in reply
    assert "未执行" in reply
