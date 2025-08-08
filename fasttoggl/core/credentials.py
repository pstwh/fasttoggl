import base64
import getpass
import json
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_MASTER_PASSWORD_CACHE = None


class CredentialsManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/config/fasttoggl")
        self.credentials_file = os.path.join(self.config_dir, "credentials.json")
        self.key_file = os.path.join(self.config_dir, "key.bin")

    def _ensure_config_dir(self):
        os.makedirs(self.config_dir, exist_ok=True)

    def _generate_key(self, password: str) -> bytes:
        salt = b"fasttoggl_salt_2025"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def _encrypt_password(self, password: str, master_password: str) -> str:
        key = self._generate_key(master_password)
        f = Fernet(key)
        encrypted = f.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()

    def _decrypt_password(self, encrypted_password: str, master_password: str) -> str:
        key = self._generate_key(master_password)
        f = Fernet(key)
        encrypted = base64.b64decode(encrypted_password.encode())
        decrypted = f.decrypt(encrypted)
        return decrypted.decode()

    def _get_master_password(self, prompt: str = "Enter your master password: ") -> str:
        global _MASTER_PASSWORD_CACHE
        if _MASTER_PASSWORD_CACHE is None:
            _MASTER_PASSWORD_CACHE = getpass.getpass(prompt)
        return _MASTER_PASSWORD_CACHE

    def save_credentials(
        self,
        email: str,
        api_token: str,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        llm_api_key: str | None = None,
        language: str | None = None,
    ):
        self._ensure_config_dir()

        master_password = getpass.getpass(
            "Enter a master password to encrypt your credentials: "
        )
        confirm_master = getpass.getpass("Confirm the master password: ")

        if master_password != confirm_master:
            raise ValueError("Master passwords do not match")

        encrypted_password = self._encrypt_password(api_token, master_password)
        credentials = {
            "email": email,
            "encrypted_password": encrypted_password,
            "language": language or "pt-BR",
        }
        if llm_api_key:
            encrypted_llm_key = self._encrypt_password(llm_api_key, master_password)
            credentials["llm"] = {
                "provider": llm_provider or "google",
                "model": llm_model or "gemini-2.5-flash",
                "encrypted_key": encrypted_llm_key,
            }

        with open(self.credentials_file, "w") as f:
            json.dump(credentials, f, indent=2)

        print(f"Credentials saved at: {self.credentials_file}")

    def load_credentials(self) -> tuple[str, str]:
        if not os.path.exists(self.credentials_file):
            return None, None

        with open(self.credentials_file, "r") as f:
            credentials = json.load(f)
        master_password = self._get_master_password("Enter your master password: ")

        try:
            decrypted_password = self._decrypt_password(
                credentials["encrypted_password"], master_password
            )
            return credentials["email"], decrypted_password
        except Exception as e:
            print(f"Error decrypting password: {e}")
            global _MASTER_PASSWORD_CACHE
            _MASTER_PASSWORD_CACHE = None
            return None, None

    def credentials_exist(self) -> bool:
        return os.path.exists(self.credentials_file)

    def load_llm_config(self) -> tuple[str | None, str, str | None]:
        if not os.path.exists(self.credentials_file):
            return None, "gemini-2.5-flash", None
        with open(self.credentials_file, "r") as f:
            credentials = json.load(f)
        llm = credentials.get("llm") or {}
        provider = llm.get("provider") or "google"
        model = llm.get("model") or "gemini-2.5-flash"
        encrypted_key = llm.get("encrypted_key")
        if encrypted_key is None:
            return provider, model, None
        master_password = self._get_master_password("Enter your master password: ")
        try:
            key = self._decrypt_password(encrypted_key, master_password)
            return provider, model, key
        except Exception as e:
            print(f"Error decrypting LLM key: {e}")
            global _MASTER_PASSWORD_CACHE
            _MASTER_PASSWORD_CACHE = None
            return provider, model, None

    def load_language(self) -> str:
        if not os.path.exists(self.credentials_file):
            return "pt-BR"
        try:
            with open(self.credentials_file, "r") as f:
                credentials = json.load(f)
            language = credentials.get("language")
            return language or "pt-BR"
        except Exception:
            return "pt-BR"
