from dataclasses import dataclass
import os
from pathlib import Path
from typing import List

import tomllib
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class User:
    """Single user: WSP credentials, Telegram chat and optional tag."""

    wsp_login: str
    wsp_password: str
    tg_chat_id: str
    tg_tag: str | None = None


@dataclass(frozen=True)
class Settings:
    tg_bot_token: str = os.environ["TG_BOT_TOKEN"]
    remote_url: str = os.getenv("REMOTE_URL", "http://selenium:4444/wd/hub")
    base_url: str = os.getenv("BASE_URL", "https://wsp.kbtu.kz/RegistrationOnline")
    schedule_path: str = os.getenv("SCHEDULE_PATH", "schedule.toml")
    users_path: str = os.getenv("USERS_PATH", "users.toml")
    users: tuple = ()  # (User, ...) filled by get_settings()


def _load_users_from_toml(path: str) -> List[User]:
    path_obj = Path(path)
    if not path_obj.is_file():
        return []
    with open(path_obj, "rb") as f:
        data = tomllib.load(f)
    raw_list = data.get("user") or data.get("users") or []
    if not isinstance(raw_list, list):
        return []
    out: List[User] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        login = entry.get("wsp_login") or entry.get("login")
        password = entry.get("wsp_password") or entry.get("password")
        chat_id = entry.get("tg_chat_id") or entry.get("chat_id")
        tag = entry.get("tg_tag") or entry.get("tag")
        if login is not None and password is not None and chat_id is not None:
            out.append(
                User(
                    wsp_login=str(login).strip(),
                    wsp_password=str(password),
                    tg_chat_id=str(chat_id).strip(),
                    tg_tag=str(tag).strip() if tag is not None else None,
                )
            )
    return out


def _single_user_from_env() -> List[User]:
    login = os.getenv("WSP_LOGIN")
    password = os.getenv("WSP_PASSWORD")
    chat_id = os.getenv("TG_CHAT_ID")
    tag = os.getenv("TG_TAG")
    if not all((login, password, chat_id)):
        return []
    return [
        User(
            wsp_login=login.strip(),
            wsp_password=password,
            tg_chat_id=chat_id.strip(),
            tg_tag=tag.strip() if tag else None,
        )
    ]


def get_settings() -> Settings:
    base = Settings(users=())
    users = _load_users_from_toml(base.users_path)
    if not users:
        users = _single_user_from_env()
    if not users:
        raise RuntimeError(
            f"No users configured. Either add {base.users_path} with [[user]] entries "
            "or set WSP_LOGIN, WSP_PASSWORD, TG_CHAT_ID in .env"
        )
    return Settings(
        tg_bot_token=base.tg_bot_token,
        remote_url=base.remote_url,
        base_url=base.base_url,
        schedule_path=base.schedule_path,
        users_path=base.users_path,
        users=tuple(users),
    )
