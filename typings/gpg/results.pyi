from typing import Any

class Result(object): ...
class InvalidKey(Result): ...

class EncryptResult(Result):
    invalid_recipients: list[Any]

class Recipient(Result):
    keyid: str
    pubkey_algo: int
    status: int

class DecryptResult(Result):
    file_name: str | None
    is_de_vs: bool
    is_mime: int
    legacy_cipher_nomdc: int
    recipients: list[Recipient]
    symkey_algo: str
    wrong_key_usage: bool

class NewSignature(Result): ...

class SignResult(Result):
    invalid_signers: InvalidKey
    signatures: NewSignature

class Notation(Result): ...

class Signature(Result):
    _type = dict(wrong_key_usage=bool, chain_model=bool, is_de_vs=bool)
    notations: list[Notation]
    chain_model: bool
    exp_timestamp: int
    fpr: str
    hash_algo: int
    is_de_vs: bool
    pka_trust: int
    pubkey_algo: int
    status: int
    summary: int
    timestamp: int
    validity: int
    validity_reason: int
    wrong_key_usage: bool

class VerifyResult(Result):
    file_name: str | None
    is_mime: int
    signatures: list[Signature]

class ImportStatus(Result):
    fpr: str
    result: int
    status: int

class ImportResult(Result):
    imported: int
    imported_rsa: int
    imports: list[ImportStatus]
    new_revocations: int
    new_signatures: int
    new_sub_keys: int
    new_user_ids: int
    no_user_id: int
    not_imported: int
    secret_imported: int
    secret_read: int
    secret_unchanged: int
    skipped_new_keys: int
    skipped_v3_keys: int
    unchanged: int

class GenkeyResult(Result):
    _type = dict(primary=bool, sub=bool)
    fpr: str

class KeylistResult(Result):
    _type = dict(truncated=bool)

class VFSMountResult(Result): ...
class EngineInfo(Result): ...
