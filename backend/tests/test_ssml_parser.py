from backend.modules.ssml_parser import flatten_to_timeline


def test_basic_text_and_break() -> None:
    ssml = '<speak>Hello<break time="250ms"/>world</speak>'
    timeline = flatten_to_timeline(ssml, {"voiceId": "en_GB-alan-medium", "speed": 1.0})
    assert len(timeline) == 2
    assert timeline[0].text == "Hello"
    assert timeline[0].breaksAfterMs == 250
    assert timeline[1].text == "world"


def test_voice_switch_and_rate() -> None:
    ssml = '<speak><voice name="en_US-amy-low">Hi</voice><prosody rate="120%">there</prosody></speak>'
    timeline = flatten_to_timeline(ssml, {"voiceId": "en_GB-alan-medium", "speed": 1.0})
    assert timeline[0].voiceId == "en_US-amy-low"
    assert timeline[1].speed > 1.19
    assert timeline[1].text == "there"


def test_say_as_variants() -> None:
    ssml = '<speak><say-as interpret-as="digits">123</say-as> <say-as interpret-as="date">2025-09-26</say-as></speak>'
    timeline = flatten_to_timeline(ssml, {"voiceId": "en_GB-alan-medium"})
    assert timeline[0].text == "1 2 3"
    assert timeline[1].text == "2025 09 26"


def test_strip_unknown_ok() -> None:
    ssml = '<speak><unknown>BAD</unknown>OK</speak>'
    timeline = flatten_to_timeline(ssml, {"voiceId": "en_GB-alan-medium"}, stripUnknown=True, errorMode="warn")
    assert len(timeline) == 1
    assert timeline[0].text == "OK"


def test_error_mode_fail_on_depth() -> None:
    deep = "<speak>" + ("<p>" * 13) + "x" + ("</p>" * 13) + "</speak>"
    try:
        flatten_to_timeline(deep, {"voiceId": "en_GB-alan-medium"}, validate=True, errorMode="fail")
    except ValueError:
        assert True
    else:
        assert False, "Expected ValueError for excessive depth"
