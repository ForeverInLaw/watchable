from relay.apns import AlertPush


def test_replyable_push_matches_tz_example() -> None:
    push = AlertPush(
        title="WhatsApp",
        body="Привет",
        source_package="com.whatsapp",
        event_id="018f",
        replyable=True,
    )

    assert push.to_payload() == {
        "aps": {
            "alert": {"title": "WhatsApp", "body": "Привет"},
            "sound": "default",
            "category": "MESSAGE_REPLY",
            "thread-id": "com.whatsapp",
            "interruption-level": "active",
        },
        "event_id": "018f",
        "replyable": True,
        "source_package": "com.whatsapp",
    }


def test_non_replyable_push_has_no_reply_category() -> None:
    push = AlertPush(
        title="Bank",
        body="Card charged",
        source_package="com.bank",
        event_id="018f",
        replyable=False,
    )

    payload = push.to_payload()

    assert "category" not in payload["aps"]
    assert payload["replyable"] is False
