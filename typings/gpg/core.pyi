from typing import Any

from collections.abc import Iterator

from gpg.results import DecryptResult
from gpg.results import EncryptResult
from gpg.results import SignResult
from gpg.results import VerifyResult

class GpgmeWrapper(object): ...

class Context(GpgmeWrapper):
    def __init__(
        self,
        armor: bool = ...,
        textmode: bool = ...,
        offline: bool = ...,
        signers: list[str] = [],
        pinentry_mode: str = ...,
        protocol: str = ...,
        wrapped: Any | None = ...,
        home_dir: str | None = ...,
    ) -> None: ...
    def __enter__(self) -> Context: ...
    def __exit__(self, type: Any, value: Any, tb: Any) -> bool: ...
    def encrypt(
        self,
        plaintext: bytes,
        recipients: list[Any] = [],
        sign: bool = ...,
        sink: Any | None = ...,
        passphrase: str | None = ...,
        always_trust: bool = ...,
        add_encrypt_to: bool = ...,
        prepare: bool = ...,
        expect_sign: bool = ...,
        compress: bool = ...,
    ) -> tuple[bytes, EncryptResult, SignResult]: ...
    def decrypt(
        self,
        ciphertext: bytes,
        sink: Any | None = ...,
        passphrase: str | None = ...,
        verify: bool = ...,
        filter_signatures: bool = ...,
    ) -> tuple[bytes, DecryptResult, VerifyResult]: ...
    def key_import(self, data: bytes) -> str: ...
    def key_export_minimal(self, pattern: Any | None = ...) -> bytes | None: ...
    def keylist(
        self,
        pattern: Any | None = ...,
        secret: bool = ...,
        mode: str = ...,
        source: Any | None = None,
    ) -> Iterator[Any]: ...
    def create_key(
        self,
        userid: str,
        algorithm: str | None = ...,
        expires_in: int = ...,
        expires: bool = ...,
        sign: bool = ...,
        encrypt: bool = ...,
        certify: bool = ...,
        authenticate: bool = ...,
        passphrase: str | None = ...,
        force: bool = ...,
    ) -> str: ...
    def get_key(self, fpr: str, secret: bool = ...) -> Any | None: ...
