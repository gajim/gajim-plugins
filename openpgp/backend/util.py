from __future__ import annotations


def parse_uid(uid: str, compat=False) -> str:
    if uid.startswith("xmpp:"):
        return uid[5:]

    # Compat with uids of form "Name <xmpp:my@jid.com>"
    if compat and "<xmpp:" in uid and uid.endswith(">"):
        return uid[:-1].split("<xmpp:", maxsplit=1)[1]

    raise ValueError("Unknown UID format: %s" % uid)
