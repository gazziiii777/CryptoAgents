from app.clients.lunarcrush.client import _topic_slug


def test_symbol_plus_single_word_name():
    assert _topic_slug("btc bitcoin", "btc") == "bitcoin"
    assert _topic_slug("sol solana", "sol") == "solana"


def test_symbol_plus_multiword_name_keeps_full_name():
    assert _topic_slug("near near protocol", "near") == "near protocol"


def test_single_word_topic_used_as_is():
    assert _topic_slug("bitcoin", "btc") == "bitcoin"


def test_empty_topic_falls_back():
    assert _topic_slug("", "doge") == "doge"
    assert _topic_slug("   ", "doge") == "doge"
