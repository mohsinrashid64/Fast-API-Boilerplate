import bcrypt

# bcrypt only uses the first 72 bytes of a password; truncate explicitly so
# bcrypt>=5 doesn't raise, and hashing/verifying stay consistent.
_MAX_BCRYPT_BYTES = 72


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


class Hash:
    @staticmethod
    def hash(password: str) -> str:
        return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify(plain_password: str, hashed_password: str | None) -> bool:
        if not hashed_password:
            return False
        try:
            return bcrypt.checkpw(_encode(plain_password), hashed_password.encode("utf-8"))
        except ValueError:
            return False
