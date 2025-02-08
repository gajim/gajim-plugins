from typing import Any

class Result(object): ...
class InvalidKey(Result): ...

class EncryptResult(Result):
    invalid_recipients: list[Any]

class Recipient(Result): ...

class DecryptResult(Result):
    recipients: Recipient

class NewSignature(Result): ...

class SignResult(Result):
    invalid_signers: InvalidKey
    signatures: NewSignature

class Notation(Result): ...

class Signature(Result):
    _type = dict(wrong_key_usage=bool, chain_model=bool, is_de_vs=bool)
    notations: Notation

class VerifyResult(Result):
    signatures: Signature

class ImportStatus(Result): ...

class ImportResult(Result):
    imports: ImportStatus

class GenkeyResult(Result):
    _type = dict(primary=bool, sub=bool)

class KeylistResult(Result):
    _type = dict(truncated=bool)

class VFSMountResult(Result): ...
class EngineInfo(Result): ...
