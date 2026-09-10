from __future__ import annotations

import asyncio
import ctypes.util
import importlib.util
import math
import os
import random
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

from cogs.admin_command_utils import (
    create_error_splash,
    create_info_splash,
    create_success_splash,
    format_duration_seconds,
)
from services.admin_service import AdminService
from services.music_player_service import MusicPlayerService
from services.role_permission_service import RolePermissionService
from ui.bot.player_ui import (
    MusicPlayerView,
    PlayerCardData,
    build_player_file,
    normalize_accent_color,
)
from ui.bot.play_config_ui import PlayerThemeModal, PlayConfigMenu, build_play_config_embed


IDLE_TIMEOUT_SECONDS = 300
PLAYER_SYNC_SECONDS = 30
PLAYER_RENDER_LEAD_SECONDS = 2
MAX_QUEUE_ITEMS = 80
QUEUE_PAGE_SIZE = 12
DEFAULT_VOLUME = 0.65
FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"
VOICE_CONNECT_TIMEOUT = 20
VOICE_RETRY_TIMEOUT = 35
VOICE_RESET_DELAY = 1.5
YTDLP_SEARCH_TIMEOUT = 35
YTDLP_STREAM_TIMEOUT = 45
TTS_CREATE_TIMEOUT = 25
PLAYBACK_START_GRACE_SECONDS = 1.2
WINDOWS_OPUS_NAMES = (
    "libopus-0.x64.dll",
    "libopus-0.x86.dll",
    "libopus-0.dll",
    "opus.dll",
    "libopus.dll",
)
POSIX_OPUS_NAMES = ("libopus", "opus")


@dataclass
class AudioItem:
    title: str
    query: str
    requester_id: int
    requester_name: str
    item_type: str = "music"
    webpage_url: str | None = None
    stream_url: str | None = None
    duration: int | None = None
    thumbnail: str | None = None
    local_file: str | None = None
    video_id: str | None = None
    artist: str | None = None
    uploader: str | None = None
    album: str | None = None


@dataclass
class GuildAudioState:
    queue: list[AudioItem] = field(default_factory=list)
    current: AudioItem | None = None
    voice_client: discord.VoiceClient | None = None
    voice_owner_id: int | None = None
    voice_owner_name: str | None = None
    text_channel_id: int | None = None
    volume: float = DEFAULT_VOLUME
    loop_current: bool = False
    autoplay: bool = False
    idle_task: asyncio.Task | None = None
    skip_requested: bool = False
    stop_requested: bool = False
    player_message_id: int | None = None
    player_channel_id: int | None = None
    playback_started_at: float | None = None
    playback_elapsed: float = 0.0
    player_card_task: asyncio.Task | None = None
    player_sync_task: asyncio.Task | None = None
    autoplay_history: list[str] = field(default_factory=list)
    last_music_item: AudioItem | None = None
    preference_user_id: int | None = None


class BotVoiceCog(commands.Cog):
    PLAY_ACTIONS = {
        "queue": "queue",
        "q": "queue",
        "list": "queue",
        "shuffle": "shuffle",
        "shufle": "shuffle",
        "sh": "shuffle",
        "sf": "shuffle",
        "autoplay": "autoplay",
        "auto": "autoplay",
        "ap": "autoplay",
        "a": "autoplay",
        "skip": "skip",
        "s": "skip",
        "next": "skip",
        "pause": "pause",
        "p": "pause",
        "pa": "pause",
        "resume": "resume",
        "continue": "resume",
        "r": "resume",
        "stop": "stop",
        "st": "stop",
        "clear": "clear",
        "c": "clear",
        "leave": "leave",
        "disconnect": "leave",
        "dc": "leave",
        "l": "leave",
        "out": "leave",
        "now": "now",
        "n": "now",
        "np": "now",
        "current": "now",
        "volume": "volume",
        "vol": "volume",
        "v": "volume",
        "loop": "loop",
        "lo": "loop",
        "repeat": "loop",
        "remove": "remove",
        "rm": "remove",
        "delete": "remove",
        "del": "remove",
        "settings": "settings",
        "setting": "settings",
        "config": "settings",
        "ui": "settings",
        "debug": "debug",
        "diag": "debug",
        "test": "voice_test",
        "tone": "voice_test",
        "beep": "voice_test",
        "soundtest": "voice_test",
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, GuildAudioState] = {}
        self.tts_dir = Path(tempfile.gettempdir()) / "black_lous_tts"
        self.tts_dir.mkdir(parents=True, exist_ok=True)
        self._last_opus_error: str | None = None
        self._dll_directory_handles: list[Any] = []
        self._ffmpeg_path: str | None = None
        self._player_message_locks: dict[int, asyncio.Lock] = {}
        self.admins = AdminService()
        self.role_permissions = RolePermissionService()
        self.player_service = MusicPlayerService()
        bot.add_view(MusicPlayerView(self, 0))

    def cog_unload(self):
        for state in self.states.values():
            if state.idle_task and not state.idle_task.done():
                state.idle_task.cancel()
            if state.player_sync_task and not state.player_sync_task.done():
                state.player_sync_task.cancel()
            if state.player_card_task and not state.player_card_task.done():
                state.player_card_task.cancel()

    def _get_state(self, guild_id: int) -> GuildAudioState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildAudioState()
        return self.states[guild_id]

    def _player_message_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._player_message_locks:
            self._player_message_locks[guild_id] = asyncio.Lock()
        return self._player_message_locks[guild_id]

    def _apply_user_preferences(self, state: GuildAudioState, user_id: int):
        preferences = self.player_service.get_user_preferences(user_id)
        state.volume = int(preferences["volume"]) / 100
        state.preference_user_id = int(user_id)

    def _save_user_preferences(
        self,
        state: GuildAudioState,
        user_id: int,
        *,
        volume: int | None = None,
    ):
        values = {}
        if volume is not None:
            values["volume"] = volume
        self.player_service.set_user_preferences(user_id, **values)
        state.preference_user_id = int(user_id)

    @staticmethod
    def _set_voice_owner(state: GuildAudioState, member: discord.Member):
        state.voice_owner_id = member.id
        state.voice_owner_name = member.display_name

    @staticmethod
    def _clear_voice_owner(state: GuildAudioState):
        state.voice_owner_id = None
        state.voice_owner_name = None

    @staticmethod
    def _voice_owner_text(state: GuildAudioState) -> str:
        if state.voice_owner_id:
            return f"<@{state.voice_owner_id}>"
        if state.voice_owner_name:
            return f"`{state.voice_owner_name}`"
        return "người đã mời bot vào voice"

    @staticmethod
    def _has_package(package_name: str) -> bool:
        return importlib.util.find_spec(package_name) is not None

    def _refresh_voice_dependency_flags(self) -> tuple[bool, str | None]:
        try:
            import nacl.secret  # noqa: F401
            import nacl.utils  # noqa: F401
        except ImportError:
            return False, "PyNaCl"

        try:
            import davey  # noqa: F401
        except ImportError:
            return False, "davey"

        try:
            import discord.voice_client as voice_client

            voice_client.has_nacl = True
            voice_client.has_dave = True
            voice_client.VoiceClient.warn_nacl = False
        except Exception:
            pass

        if not self._load_opus_library():
            return False, "libopus"
        return True, None

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def _add_dll_directory(self, directory: Path):
        if os.name != "nt" or not hasattr(os, "add_dll_directory"):
            return
        try:
            handle = os.add_dll_directory(str(directory))
            self._dll_directory_handles.append(handle)
        except (FileNotFoundError, OSError):
            pass

    def _iter_opus_candidates(self) -> list[str]:
        candidates: list[str] = []
        env_path = os.getenv("DISCORD_OPUS_LIBRARY") or os.getenv("OPUS_LIBRARY")
        if env_path:
            candidates.append(env_path)

        project_root = self._project_root()
        python_dir = Path(sys.executable).resolve().parent
        if os.name == "nt":
            discord_bin = Path(discord.opus.__file__).resolve().parent / "bin"
            architecture = "x64" if ctypes.sizeof(ctypes.c_void_p) * 8 > 32 else "x86"
            search_dirs = [
                discord_bin,
                project_root,
                project_root / "bin",
                project_root / "libs",
                python_dir,
                python_dir / "DLLs",
                Path("C:/ffmpeg/bin"),
                Path("C:/Program Files/ffmpeg/bin"),
                Path("C:/Program Files/Opus/bin"),
            ]
            candidates.append(str(discord_bin / f"libopus-0.{architecture}.dll"))
            for directory in search_dirs:
                for name in WINDOWS_OPUS_NAMES:
                    candidates.append(str(directory / name))
            for name in WINDOWS_OPUS_NAMES:
                found = shutil.which(name)
                if found:
                    candidates.append(found)
                candidates.append(name)
        else:
            candidates.extend(
                [
                    "/opt/homebrew/lib/libopus.dylib",
                    "/opt/homebrew/opt/opus/lib/libopus.dylib",
                    "/usr/local/lib/libopus.dylib",
                    "/usr/local/opt/opus/lib/libopus.dylib",
                    "/usr/lib/x86_64-linux-gnu/libopus.so.0",
                    "/usr/lib/aarch64-linux-gnu/libopus.so.0",
                    "/usr/local/lib/libopus.so",
                ]
            )
            candidates.extend(POSIX_OPUS_NAMES)

        found_library = ctypes.util.find_library("opus")
        if found_library:
            candidates.append(found_library)

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(candidate).strip()
            if normalized and normalized.lower() not in seen:
                deduped.append(normalized)
                seen.add(normalized.lower())
        return deduped

    def _load_opus_library(self) -> bool:
        if discord.opus.is_loaded():
            return True

        errors: list[str] = []
        default_loader = getattr(discord.opus, "_load_default", None)
        if callable(default_loader):
            try:
                if default_loader() and discord.opus.is_loaded():
                    self._last_opus_error = None
                    return True
            except Exception as exc:
                errors.append(f"discord.py bundled Opus: {exc}")

        for candidate in self._iter_opus_candidates():
            try:
                candidate_path = Path(candidate)
                if os.name == "nt" and candidate_path.is_absolute() and candidate_path.parent.exists():
                    self._add_dll_directory(candidate_path.parent)
                discord.opus.load_opus(candidate)
                if discord.opus.is_loaded():
                    self._last_opus_error = None
                    return True
            except (OSError, TypeError, AttributeError) as exc:
                if len(errors) < 6:
                    errors.append(f"{candidate}: {exc}")
                continue
        self._last_opus_error = "\n".join(errors)
        return False

    def _opus_install_hint(self) -> str:
        if os.name == "nt":
            detail = (
                "Không load được Opus đi kèm `discord.py` trên Windows.\n"
                "Chạy trong thư mục bot rồi restart process:\n"
                "```bat\n"
                ".venv\\Scripts\\python.exe -m pip install --upgrade --force-reinstall \"discord.py[voice]\"\n"
                "```\n"
                "Bot sẽ tự nhận file `.venv\\Lib\\site-packages\\discord\\bin\\libopus-0.x64.dll`; "
                "không cần tự chép DLL từ FFmpeg.\n"
                "Nếu file có tồn tại nhưng vẫn không load được, cài Microsoft Visual C++ Redistributable x64."
            )
            if self._last_opus_error:
                detail += f"\n\nLần thử gần nhất:\n```text\n{self._short_text(self._last_opus_error, 650)}\n```"
            return detail
        if sys.platform == "darwin":
            return "Không load được `libopus`. Trên macOS dùng `brew install opus`, hoặc set `DISCORD_OPUS_LIBRARY=/opt/homebrew/lib/libopus.dylib`."
        return "Không load được `libopus`. Trên Linux cài `libopus0`/`opus-tools`, hoặc set `DISCORD_OPUS_LIBRARY=/usr/lib/x86_64-linux-gnu/libopus.so.0`."

    @staticmethod
    def _pip_install_hint(install_name: str) -> str:
        executable = Path(sys.executable).name or "python"
        return f"Cần cài `{install_name}` cho đúng Python đang chạy bot: `{executable} -m pip install {install_name}`."

    async def _require_voice_ready(self, ctx) -> bool:
        is_ready, missing_package = self._refresh_voice_dependency_flags()
        if not is_ready:
            if missing_package == "libopus":
                detail = self._opus_install_hint()
            else:
                detail = self._pip_install_hint(str(missing_package))
            await ctx.send(
                embed=create_error_splash(
                    "❌ Thiếu Voice Library",
                    detail,
                )
            )
            return False
        return True

    def _find_ffmpeg(self) -> str | None:
        if self._ffmpeg_path and Path(self._ffmpeg_path).exists():
            return self._ffmpeg_path
        candidates = [
            shutil.which("ffmpeg"),
            str(self._project_root() / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")),
            str(Path("C:/ffmpeg/bin/ffmpeg.exe")),
            str(Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe")),
            str(Path(sys.executable).resolve().parent / "ffmpeg.exe"),
        ]
        for candidate in [item for item in candidates if item]:
            if Path(candidate).exists() or candidate == shutil.which("ffmpeg"):
                self._ffmpeg_path = str(candidate)
                return self._ffmpeg_path
        return None

    async def _require_ffmpeg(self, ctx) -> bool:
        if self._find_ffmpeg() is None:
            if os.name == "nt":
                detail = "Cần `ffmpeg.exe`. Bot sẽ tự nhận nếu có ở `C:\\ffmpeg\\bin\\ffmpeg.exe`; nếu mới cài xong hãy restart CMD/bot."
            else:
                detail = "Cần cài `ffmpeg` để phát nhạc/đọc giọng. Trên macOS dùng: `brew install ffmpeg`."
            await ctx.send(
                embed=create_error_splash(
                    "❌ Thiếu FFmpeg",
                    detail,
                )
            )
            return False
        return True

    async def _run_ffmpeg_probe(self) -> tuple[bool, str]:
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            return False, "Không tìm thấy ffmpeg."

        def run_probe():
            return subprocess.run(
                [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=1000:duration=0.2",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )

        try:
            result = await self.bot.loop.run_in_executor(None, run_probe)
        except Exception as exc:
            return False, str(exc)

        output = (result.stderr or result.stdout or "").strip()
        if result.returncode == 0:
            return True, "FFmpeg tạo audio test OK."
        return False, output or f"FFmpeg exit code {result.returncode}."

    async def _normalize_voice_state(self, guild: discord.Guild, voice_client: discord.VoiceClient):
        try:
            await guild.change_voice_state(
                channel=voice_client.channel,
                self_mute=False,
                self_deaf=False,
            )
        except (discord.Forbidden, discord.HTTPException, RuntimeError):
            pass

    async def _show_voice_debug(self, ctx, *, try_connect: bool = False):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Debug voice chỉ hoạt động trong server."))
            return

        state = self._get_state(ctx.guild.id)
        voice_client = self._find_guild_voice_client(ctx.guild) or ctx.voice_client or state.voice_client
        if voice_client and voice_client.is_connected():
            state.voice_client = voice_client

        voice_ready, missing_package = self._refresh_voice_dependency_flags()
        ffmpeg_ok, ffmpeg_detail = await self._run_ffmpeg_probe()
        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        target_channel = getattr(getattr(ctx.author, "voice", None), "channel", None)
        if try_connect and target_channel and not (voice_client and voice_client.is_connected()):
            voice_client = await self._ensure_voice(ctx)
            if voice_client and voice_client.is_connected():
                state.voice_client = voice_client
                bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        bot_voice = getattr(bot_member, "voice", None) if bot_member else None

        def ok_text(value: bool) -> str:
            return "OK" if value else "LỖI"

        lines = [
            "**Voice runtime**",
            f"Opus/PyNaCl/DAVE: `{ok_text(voice_ready)}`" + (f" (`{missing_package}`)" if missing_package else ""),
            f"FFmpeg: `{ok_text(ffmpeg_ok)}`",
            f"FFmpeg path: `{self._find_ffmpeg() or 'không tìm thấy'}`",
            f"FFmpeg test: `{self._short_text(ffmpeg_detail, 180)}`",
            "",
            "**Discord voice**",
            f"Bot connected: `{bool(voice_client and voice_client.is_connected())}`",
            f"Bot channel: `{getattr(getattr(voice_client, 'channel', None), 'name', 'không có')}`",
            f"User channel: `{getattr(target_channel, 'name', 'không có')}`",
            f"is_playing/is_paused: `{bool(voice_client and voice_client.is_playing())}` / `{bool(voice_client and voice_client.is_paused())}`",
            f"Volume: `{int(state.volume * 100)}%`",
            f"Current: `{self._short_text(state.current.title, 80) if state.current else 'không có'}`",
            f"Queue: `{len(state.queue)}`",
        ]

        if bot_voice:
            lines.extend(
                [
                    "",
                    "**Bot voice state**",
                    f"self_mute/self_deaf: `{bot_voice.self_mute}` / `{bot_voice.self_deaf}`",
                    f"server mute/deaf: `{bot_voice.mute}` / `{bot_voice.deaf}`",
                ]
            )
            if bot_voice.mute or bot_voice.deaf:
                lines.append("`CẢNH BÁO:` Bot đang bị server mute/deaf nên không thể phát tiếng.")
            if bot_voice.self_mute or bot_voice.self_deaf:
                lines.append("`CẢNH BÁO:` Bot đang self mute/deaf. Hãy dùng `leave` rồi `join` lại sau bản sửa này.")

        if target_channel and bot_member:
            permissions = target_channel.permissions_for(bot_member)
            lines.extend(
                [
                    "",
                    "**Quyền tại voice của bạn**",
                    f"Connect/Speak: `{permissions.connect}` / `{permissions.speak}`",
                ]
            )

        await ctx.send(embed=create_info_splash("🔎 Voice Debug", "\n".join(lines)))

    async def _require_package(self, ctx, package_name: str, install_name: str) -> bool:
        if not self._has_package(package_name):
            await ctx.send(
                embed=create_error_splash(
                    "❌ Thiếu Package",
                    self._pip_install_hint(install_name),
                )
            )
            return False
        return True

    @staticmethod
    async def _try_react(message: discord.Message, emoji: str):
        try:
            await message.add_reaction(emoji)
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _play_reaction(self, guild_id: int, key: str) -> str:
        theme = self.player_service.get_theme(guild_id)
        return str(theme.get(key) or "")

    @staticmethod
    def _format_player_text(template: str, **values) -> str:
        try:
            return str(template).format(**values)
        except (KeyError, ValueError):
            return str(template)

    def _queue_added_embed(
        self,
        guild_id: int,
        items: list[AudioItem],
        position: int,
    ) -> discord.Embed:
        theme = self.player_service.get_theme(guild_id)
        first = items[0]
        values = {
            "title": self._short_text(first.title, 120),
            "count": len(items),
            "position": position,
            "requester": first.requester_name,
        }
        icon = str(theme.get("icon_queue_added") or "🎶").strip()
        title = self._format_player_text(
            theme.get("message_queue_added_title") or "Đã thêm vào queue",
            **values,
        )
        body = self._format_player_text(
            theme.get("message_queue_added_body")
            or "`{title}`\nVị trí: `{position}` • Số bài: `{count}` • Yêu cầu bởi: {requester}",
            **values,
        )
        return discord.Embed(
            title=f"{icon} {title}".strip(),
            description=body,
            color=discord.Color.from_str(str(theme.get("accent_color") or "#7f314d")),
        )

    def _find_guild_voice_client(self, guild: discord.Guild) -> discord.VoiceClient | None:
        voice_client = getattr(guild, "voice_client", None)
        if voice_client and voice_client.is_connected():
            return voice_client

        for client in self.bot.voice_clients:
            client_guild = getattr(client, "guild", None)
            if client_guild and client_guild.id == guild.id and client.is_connected():
                return client
        return None

    async def _finish_voice_connect(self, ctx, state: GuildAudioState, voice_client: discord.VoiceClient):
        state.voice_client = voice_client
        state.text_channel_id = ctx.channel.id
        self._cancel_idle(state)
        await self._normalize_voice_state(ctx.guild, voice_client)
        return voice_client

    async def _force_reset_voice_session(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient | None = None,
    ) -> str | None:
        reset_error: str | None = None
        if voice_client:
            try:
                await voice_client.disconnect(force=True)
            except Exception as exc:
                reset_error = str(exc)
        try:
            await guild.change_voice_state(channel=None, self_mute=False, self_deaf=False)
        except Exception as exc:
            reset_error = str(exc)
        await asyncio.sleep(VOICE_RESET_DELAY)
        return reset_error

    async def _retry_voice_connect_after_timeout(
        self,
        ctx,
        state: GuildAudioState,
        target_channel: discord.VoiceChannel,
        voice_client: discord.VoiceClient | None = None,
    ) -> discord.VoiceClient | None:
        reset_error = await self._force_reset_voice_session(ctx.guild, voice_client)
        try:
            new_client = await target_channel.connect(
                timeout=VOICE_RETRY_TIMEOUT,
                self_deaf=False,
            )
            self._set_voice_owner(state, ctx.author)
            return await self._finish_voice_connect(ctx, state, new_client)
        except asyncio.TimeoutError:
            detail = (
                "Bot đã reset voice session và thử join lại nhưng Discord vẫn timeout.\n"
                "Nếu Opus/FFmpeg đều OK thì thường là VPS/firewall/nhà mạng đang chặn Discord voice UDP, "
                "hoặc còn một process bot cũ đang giữ voice session.\n"
                "Hãy tắt toàn bộ process bot cũ rồi chạy lại một process duy nhất; nếu vẫn lỗi, thử VPS/nhà mạng khác."
            )
            if reset_error:
                detail += f"\nReset detail: `{self._short_text(reset_error, 160)}`"
            await ctx.send(embed=create_error_splash("❌ Voice Timeout", detail))
            return None
        except discord.ClientException as exc:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Không Join Được Voice",
                    f"Sau khi reset voice session vẫn không join được.\nChi tiết: `{exc}`",
                )
            )
            return None
        except discord.Forbidden:
            await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Discord", "Bot thiếu quyền vào/nói trong voice channel này."))
            return None
        except discord.HTTPException as exc:
            await ctx.send(embed=create_error_splash("❌ Voice Lỗi", str(exc)))
            return None

    async def _ensure_voice(self, ctx) -> discord.VoiceClient | None:
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh voice chỉ hoạt động trong server."))
            return None
        if not await self._require_voice_ready(ctx):
            return None
        if not getattr(ctx.author, "voice", None) or not ctx.author.voice.channel:
            await ctx.send(embed=create_error_splash("❌ Chưa Vào Voice", "Bạn cần vào voice channel trước."))
            return None

        state = self._get_state(ctx.guild.id)
        target_channel = ctx.author.voice.channel
        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        if bot_member:
            voice_permissions = target_channel.permissions_for(bot_member)
            if not voice_permissions.connect:
                await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Voice", f"Bot thiếu quyền `Connect` trong `{target_channel.name}`."))
                return None
            if not voice_permissions.speak:
                await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Voice", f"Bot thiếu quyền `Speak` trong `{target_channel.name}` nên có vào room cũng không phát ra tiếng."))
                return None
        voice_client = self._find_guild_voice_client(ctx.guild) or ctx.voice_client or state.voice_client

        try:
            if voice_client and voice_client.is_connected():
                if voice_client.channel != target_channel:
                    if state.voice_owner_id and state.voice_owner_id != ctx.author.id:
                        await ctx.send(
                            embed=create_error_splash(
                                "❌ Voice Đang Được Giữ",
                                f"Bot đang ở `{voice_client.channel.name}` do {self._voice_owner_text(state)} mời vào. Chỉ người đó mới được chuyển phòng hoặc leave.",
                            )
                        )
                        return None
                    await asyncio.wait_for(voice_client.move_to(target_channel), timeout=VOICE_CONNECT_TIMEOUT)
                if state.voice_owner_id is None:
                    self._set_voice_owner(state, ctx.author)
            else:
                voice_client = await target_channel.connect(
                    timeout=VOICE_CONNECT_TIMEOUT,
                    self_deaf=False,
                )
                self._set_voice_owner(state, ctx.author)
            return await self._finish_voice_connect(ctx, state, voice_client)
        except asyncio.TimeoutError:
            return await self._retry_voice_connect_after_timeout(ctx, state, target_channel, voice_client)
        except discord.ClientException as exc:
            if "already connected" in str(exc).lower():
                existing_client = self._find_guild_voice_client(ctx.guild)
                if existing_client and existing_client.is_connected():
                    if existing_client.channel == target_channel:
                        if state.voice_owner_id is None:
                            self._set_voice_owner(state, ctx.author)
                        return await self._finish_voice_connect(ctx, state, existing_client)
                    await ctx.send(
                        embed=create_error_splash(
                            "❌ Voice Đang Ở Phòng Khác",
                            f"Bot đang ở `{existing_client.channel.name}`. Hãy vào đúng phòng đó hoặc dùng người giữ quyền leave để chuyển phòng.",
                        )
                    )
                    return None
                return await self._retry_voice_connect_after_timeout(ctx, state, target_channel, voice_client)
            await ctx.send(embed=create_error_splash("❌ Không Join Được Voice", str(exc)))
        except discord.Forbidden:
            await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Discord", "Bot thiếu quyền vào/nói trong voice channel này."))
        except discord.HTTPException as exc:
            await ctx.send(embed=create_error_splash("❌ Voice Lỗi", str(exc)))
        except RuntimeError as exc:
            if "PyNaCl" in str(exc) or "davey" in str(exc).lower():
                await ctx.send(
                    embed=create_error_splash(
                        "❌ Voice Library Chưa Sẵn Sàng",
                        "Voice library đã được cài nhưng process bot cũ vẫn chưa nhận. Hãy `breload bot` hoặc restart `python3 main.py` rồi thử lại.",
                    )
                )
            else:
                await ctx.send(embed=create_error_splash("❌ Voice Lỗi", str(exc)))
        return None

    def _cancel_idle(self, state: GuildAudioState):
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
        state.idle_task = None

    @staticmethod
    def _cancel_player_sync(state: GuildAudioState):
        if state.player_sync_task and not state.player_sync_task.done():
            state.player_sync_task.cancel()
        state.player_sync_task = None

    @staticmethod
    def _cancel_player_card(state: GuildAudioState):
        if state.player_card_task and not state.player_card_task.done():
            state.player_card_task.cancel()
        state.player_card_task = None

    def _schedule_now_playing_card(self, guild_id: int, item: AudioItem):
        state = self._get_state(guild_id)
        self._cancel_player_card(state)
        state.player_card_task = self.bot.loop.create_task(
            self._send_now_playing(guild_id, item)
        )

    def _schedule_player_sync(self, guild_id: int):
        state = self._get_state(guild_id)
        self._cancel_player_sync(state)
        state.player_sync_task = self.bot.loop.create_task(
            self._player_sync_loop(guild_id)
        )

    async def _player_sync_loop(self, guild_id: int):
        try:
            while True:
                await asyncio.sleep(PLAYER_SYNC_SECONDS)
                state = self._get_state(guild_id)
                voice_client = state.voice_client
                if (
                    not state.current
                    or state.current.item_type != "music"
                    or not voice_client
                    or not voice_client.is_connected()
                ):
                    return
                if voice_client.is_paused():
                    continue
                if not voice_client.is_playing():
                    return
                await self._refresh_player_message(guild_id)
        except asyncio.CancelledError:
            return

    @staticmethod
    def _playback_seconds(state: GuildAudioState) -> int:
        elapsed = state.playback_elapsed
        if state.playback_started_at is not None:
            elapsed += max(0.0, time.monotonic() - state.playback_started_at)
        return max(0, int(elapsed))

    @staticmethod
    def _pause_playback_clock(state: GuildAudioState):
        if state.playback_started_at is not None:
            state.playback_elapsed += max(0.0, time.monotonic() - state.playback_started_at)
            state.playback_started_at = None

    @staticmethod
    def _resume_playback_clock(state: GuildAudioState):
        if state.playback_started_at is None:
            state.playback_started_at = time.monotonic()

    def _schedule_idle_disconnect(self, guild_id: int):
        state = self._get_state(guild_id)
        self._cancel_idle(state)
        state.idle_task = self.bot.loop.create_task(self._idle_disconnect(guild_id))

    async def _idle_disconnect(self, guild_id: int):
        try:
            await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
            state = self._get_state(guild_id)
            voice_client = state.voice_client
            if not voice_client or not voice_client.is_connected():
                return
            if state.queue or voice_client.is_playing() or voice_client.is_paused():
                return
            await voice_client.disconnect(force=False)
            state.voice_client = None
            state.current = None
            self._clear_voice_owner(state)
        except asyncio.CancelledError:
            return

    @staticmethod
    def _is_url(value: str) -> bool:
        return bool(re.match(r"https?://", value.strip(), flags=re.IGNORECASE))

    @staticmethod
    def _short_text(value: str, limit: int = 90) -> str:
        value = " ".join(value.split())
        if len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + "..."

    @staticmethod
    def _duration_text(seconds: int | None) -> str:
        if not seconds:
            return "không rõ"
        return format_duration_seconds(int(seconds))

    async def _send_to_state_channel(self, guild_id: int, embed: discord.Embed):
        state = self._get_state(guild_id)
        if not state.text_channel_id:
            return
        channel = self.bot.get_channel(state.text_channel_id)
        if channel:
            await channel.send(embed=embed)

    async def _send_playback_start_error(self, guild_id: int, item: AudioItem, detail: str):
        ffmpeg_path = self._find_ffmpeg() or "ffmpeg"
        source_hint = item.local_file or item.stream_url or item.webpage_url or item.query
        await self._send_to_state_channel(
            guild_id,
            create_error_splash(
                "❌ Không Phát Được",
                (
                    f"`{self._short_text(item.title, 120)}`\n"
                    f"{detail}\n"
                    f"FFmpeg: `{ffmpeg_path}`\n"
                    f"Nguồn: `{self._short_text(str(source_hint), 180)}`"
                ),
            ),
        )

    async def _verify_playback_started(self, guild_id: int, item: AudioItem):
        await asyncio.sleep(PLAYBACK_START_GRACE_SECONDS)
        state = self._get_state(guild_id)
        voice_client = state.voice_client
        if state.current is not item:
            return
        if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
            return
        await self._send_playback_start_error(
            guild_id,
            item,
            (
                "Nguồn phát đã được đưa vào voice nhưng FFmpeg/Discord voice dừng ngay sau khi bắt đầu. "
                "Nếu lỗi này chỉ xảy ra trên VPS Windows, hãy kiểm tra firewall/nhà VPS có chặn UDP outbound tới Discord voice không."
            ),
        )
        state.current = None
        await self._cleanup_item(item)
        await self._play_next(guild_id)

    def _build_music_item(self, entry: dict[str, Any], requester: discord.Member, fallback_query: str) -> AudioItem | None:
        if not entry:
            return None

        title = entry.get("title") or fallback_query
        webpage_url = entry.get("webpage_url") or entry.get("original_url")
        raw_url = entry.get("url")
        if not webpage_url and raw_url:
            if entry.get("ie_key") == "Youtube" and entry.get("id") and not self._is_url(str(raw_url)):
                webpage_url = f"https://www.youtube.com/watch?v={entry['id']}"
            else:
                webpage_url = str(raw_url)

        query = webpage_url or raw_url or fallback_query
        if not query:
            return None

        return AudioItem(
            title=str(title),
            query=str(query),
            webpage_url=str(webpage_url) if webpage_url else None,
            duration=entry.get("duration"),
            thumbnail=entry.get("thumbnail"),
            requester_id=requester.id,
            requester_name=requester.display_name,
            video_id=str(entry.get("id")) if entry.get("id") else None,
            artist=entry.get("artist") or entry.get("creator"),
            uploader=entry.get("uploader") or entry.get("channel"),
            album=entry.get("album"),
        )

    async def _extract_music_items(self, query: str, requester: discord.Member) -> list[AudioItem]:
        from yt_dlp import YoutubeDL

        search_query = query.strip()
        if not self._is_url(search_query):
            search_query = f"ytsearch1:{search_query}"

        ytdl_options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "default_search": "ytsearch",
            "extract_flat": "in_playlist",
            "noplaylist": False,
        }

        def run_extract():
            with YoutubeDL(ytdl_options) as ydl:
                return ydl.extract_info(search_query, download=False)

        info = await asyncio.wait_for(
            self.bot.loop.run_in_executor(None, run_extract),
            timeout=YTDLP_SEARCH_TIMEOUT,
        )
        if not info:
            return []

        entries = info.get("entries") if isinstance(info, dict) else None
        if entries:
            items = [
                self._build_music_item(entry, requester, query)
                for entry in list(entries)[:MAX_QUEUE_ITEMS]
                if entry
            ]
            return [item for item in items if item]

        item = self._build_music_item(info, requester, query)
        return [item] if item else []

    async def _resolve_stream_url(self, item: AudioItem) -> AudioItem:
        from yt_dlp import YoutubeDL

        ytdl_options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "default_search": "ytsearch",
            "noplaylist": True,
        }

        def run_extract():
            with YoutubeDL(ytdl_options) as ydl:
                return ydl.extract_info(item.webpage_url or item.query, download=False)

        info = await asyncio.wait_for(
            self.bot.loop.run_in_executor(None, run_extract),
            timeout=YTDLP_STREAM_TIMEOUT,
        )
        if isinstance(info, dict) and info.get("entries"):
            info = next((entry for entry in info["entries"] if entry), None)
        if not info:
            raise ValueError("Không lấy được nguồn phát.")

        stream_url = info.get("url")
        if not stream_url:
            formats = [fmt for fmt in info.get("formats", []) if fmt.get("url")]
            if formats:
                stream_url = formats[-1]["url"]
        if not stream_url:
            raise ValueError("Không tìm thấy audio stream.")

        item.stream_url = stream_url
        item.title = info.get("title") or item.title
        item.webpage_url = info.get("webpage_url") or item.webpage_url
        item.duration = info.get("duration") or item.duration
        item.thumbnail = info.get("thumbnail") or item.thumbnail
        item.video_id = str(info.get("id")) if info.get("id") else item.video_id
        item.artist = info.get("artist") or info.get("creator") or item.artist
        item.uploader = info.get("uploader") or info.get("channel") or item.uploader
        item.album = info.get("album") or item.album
        return item

    async def _create_tts_item(self, ctx, text: str) -> AudioItem:
        from gtts import gTTS

        safe_id = f"{ctx.guild.id}-{ctx.message.id}-{random.randint(1000, 9999)}"
        output_path = self.tts_dir / f"tts-{safe_id}.mp3"

        def save_tts():
            gTTS(text=text, lang="vi").save(str(output_path))

        try:
            await asyncio.wait_for(
                self.bot.loop.run_in_executor(None, save_tts),
                timeout=TTS_CREATE_TIMEOUT,
            )
        except Exception:
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            raise
        return AudioItem(
            title=self._short_text(text, 120),
            query=str(output_path),
            requester_id=ctx.author.id,
            requester_name=ctx.author.display_name,
            item_type="tts",
            local_file=str(output_path),
        )

    async def _create_tone_item(self, ctx, duration: float = 2.0) -> AudioItem:
        safe_id = f"{ctx.guild.id}-{ctx.message.id}-{random.randint(1000, 9999)}"
        output_path = self.tts_dir / f"tone-{safe_id}.wav"
        sample_rate = 48_000
        frequency = 660.0
        amplitude = 14_000
        frame_count = int(sample_rate * duration)

        def write_tone():
            frames = bytearray()
            for index in range(frame_count):
                sample = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
                frames.extend(struct.pack("<h", sample))

            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(bytes(frames))

        try:
            await self.bot.loop.run_in_executor(None, write_tone)
        except Exception:
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            raise

        return AudioItem(
            title="Voice test tone",
            query=str(output_path),
            requester_id=ctx.author.id,
            requester_name=ctx.author.display_name,
            item_type="tts",
            local_file=str(output_path),
        )

    async def _run_voice_test(self, ctx):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Test voice chỉ hoạt động trong server."))
            return
        if not await self._require_ffmpeg(ctx):
            return

        voice_client = await self._ensure_voice(ctx)
        if not voice_client:
            return

        state = self._get_state(ctx.guild.id)
        state.text_channel_id = ctx.channel.id
        try:
            item = await self._create_tone_item(ctx)
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Không Tạo Được Test Tone", str(exc)))
            return

        state.queue.append(item)
        await ctx.send(
            embed=create_info_splash(
                "🔊 Voice Test",
                (
                    "Đang phát tone test nội bộ trong 2 giây.\n"
                    "Nếu không nghe tiếng beep thì lỗi nằm ở voice transport/VPS hoặc trạng thái mute/deaf, "
                    "không phải do YouTube hay Google TTS."
                ),
            )
        )
        await self._start_player_if_needed(ctx.guild.id)

    async def _start_player_if_needed(self, guild_id: int):
        state = self._get_state(guild_id)
        voice_client = state.voice_client
        if not voice_client or not voice_client.is_connected():
            guild = self.bot.get_guild(guild_id)
            if guild:
                voice_client = self._find_guild_voice_client(guild)
                if voice_client and voice_client.is_connected():
                    state.voice_client = voice_client
        if not voice_client or not voice_client.is_connected():
            return
        if voice_client.is_playing() or voice_client.is_paused():
            if state.current is None:
                try:
                    voice_client.stop()
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                if not voice_client.is_playing() and not voice_client.is_paused():
                    await self._play_next(guild_id)
                elif state.queue:
                    await self._send_playback_start_error(
                        guild_id,
                        state.queue[0],
                        "Voice client đang báo còn phát nhưng bot không có bài hiện tại. Bot đã thử dừng nguồn cũ nhưng chưa giải phóng được.",
                    )
            return
        await self._play_next(guild_id)

    async def _enqueue_autoplay(self, guild_id: int) -> bool:
        state = self._get_state(guild_id)
        previous = state.current or state.last_music_item
        if (
            not state.autoplay
            or not previous
            or previous.item_type != "music"
            or not previous.video_id
            or not any(
                host in str(previous.webpage_url or "").lower()
                for host in ("youtube.com", "youtu.be")
            )
        ):
            return False
        try:
            requester = self.bot.get_user(previous.requester_id)
            if requester is None:
                requester = type(
                    "AutoplayRequester",
                    (),
                    {
                        "id": previous.requester_id,
                        "display_name": previous.requester_name,
                    },
                )()
            seen = {
                self._autoplay_item_key(item)
                for item in [previous, *state.queue]
                if self._autoplay_item_key(item)
            }
            seen.update(state.autoplay_history)

            radio_url = (
                f"https://www.youtube.com/watch?v={previous.video_id}"
                f"&list=RD{previous.video_id}"
            )
            candidates = await self._extract_music_items(radio_url, requester)
            for candidate in candidates:
                key = self._autoplay_item_key(candidate)
                if key and key not in seen:
                    state.queue.append(candidate)
                    return True
        except Exception:
            return False
        return False

    @staticmethod
    def _autoplay_item_key(item: AudioItem) -> str:
        value = item.video_id or item.webpage_url or item.title
        return " ".join(str(value or "").strip().lower().split())

    async def _play_next(self, guild_id: int):
        state = self._get_state(guild_id)
        voice_client = state.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        self._cancel_idle(state)
        if state.stop_requested:
            state.stop_requested = False
            state.current = None
            self._schedule_idle_disconnect(guild_id)
            return

        if state.loop_current and state.current and not state.skip_requested:
            item = state.current
        else:
            if not state.queue:
                await self._enqueue_autoplay(guild_id)
            if not state.queue:
                state.current = None
                state.skip_requested = False
                self._schedule_idle_disconnect(guild_id)
                return
            item = state.queue.pop(0)
            state.current = item
            state.skip_requested = False

        try:
            ffmpeg_executable = self._find_ffmpeg() or "ffmpeg"
            if item.item_type == "music":
                item = await self._resolve_stream_url(item)
                history_key = self._autoplay_item_key(item)
                if history_key:
                    state.autoplay_history.append(history_key)
                    state.autoplay_history = state.autoplay_history[-100:]
                source = discord.FFmpegPCMAudio(
                    item.stream_url,
                    executable=ffmpeg_executable,
                    before_options=FFMPEG_BEFORE_OPTIONS,
                    options=FFMPEG_OPTIONS,
                )
            else:
                source = discord.FFmpegPCMAudio(item.local_file, executable=ffmpeg_executable, options=FFMPEG_OPTIONS)

            source = discord.PCMVolumeTransformer(source, volume=state.volume)

            def after_play(error):
                self.bot.loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self._after_play(guild_id, error),
                )

            voice_client.play(source, after=after_play)
            state.playback_elapsed = 0.0
            state.playback_started_at = time.monotonic()
            if item.item_type == "music":
                self._schedule_now_playing_card(guild_id, item)
                self._schedule_player_sync(guild_id)
            self.bot.loop.create_task(self._verify_playback_started(guild_id, item))
        except Exception as exc:
            print(f"[voice] Play failed in guild {guild_id}: {repr(exc)}", file=sys.stderr)
            error_text = str(exc) or repr(exc)
            if isinstance(exc, asyncio.TimeoutError):
                error_text = "Quá thời gian lấy nguồn phát. YouTube/Spotify đang phản hồi chậm, thử lại hoặc gửi link khác."
            await self._send_to_state_channel(
                guild_id,
                create_error_splash("❌ Phát Thất Bại", f"`{item.title}`\n{error_text}"),
            )
            await self._cleanup_item(item)
            state.current = None
            await self._play_next(guild_id)

    async def _after_play(self, guild_id: int, error):
        state = self._get_state(guild_id)
        self._cancel_player_card(state)
        self._cancel_player_sync(state)
        finished_item = state.current
        state.playback_started_at = None
        state.playback_elapsed = 0.0

        if error:
            print(f"[voice] Playback callback error in guild {guild_id}: {repr(error)}", file=sys.stderr)
            await self._send_to_state_channel(guild_id, create_error_splash("❌ Voice Lỗi", str(error)))

        if finished_item and finished_item.item_type == "tts":
            await self._cleanup_item(finished_item)
        if finished_item and finished_item.item_type == "music":
            state.last_music_item = finished_item

        if state.stop_requested:
            state.current = None
            state.stop_requested = False
            self._schedule_idle_disconnect(guild_id)
            return

        if state.loop_current and finished_item and finished_item.item_type == "music" and not state.skip_requested:
            state.current = finished_item
        elif state.skip_requested:
            state.current = None
        else:
            state.current = None

        await self._play_next(guild_id)

    async def _cleanup_item(self, item: AudioItem):
        if item.local_file and os.path.exists(item.local_file):
            try:
                os.remove(item.local_file)
            except OSError:
                pass

    async def _send_now_playing(
        self,
        guild_id: int,
        item: AudioItem,
    ):
        if item.item_type == "tts":
            return
        state = self._get_state(guild_id)
        if state.current is not item:
            return
        try:
            await self._refresh_player_message(guild_id, move_to_bottom=True)
        except asyncio.CancelledError:
            return
        except Exception as card_error:
            print(
                f"[voice] Could not send player card in guild {guild_id}: {card_error!r}",
                file=sys.stderr,
            )

    async def _delete_player_message_unlocked(self, state: GuildAudioState):
        if not state.player_message_id or not state.player_channel_id:
            return
        channel = self.bot.get_channel(state.player_channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            try:
                message = await channel.fetch_message(state.player_message_id)
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        state.player_message_id = None
        state.player_channel_id = None

    async def _delete_player_message(self, guild_id: int):
        async with self._player_message_lock(guild_id):
            await self._delete_player_message_unlocked(self._get_state(guild_id))

    async def _build_player_card_file(
        self,
        guild_id: int,
        item: AudioItem,
        *,
        elapsed: int,
        paused: bool,
    ) -> discord.File:
        state = self._get_state(guild_id)
        theme = self.player_service.get_theme(guild_id)
        data = PlayerCardData(
            title=item.title,
            requester=item.requester_name,
            duration=item.duration,
            elapsed=elapsed,
            thumbnail=item.thumbnail,
            volume=int(state.volume * 100),
            paused=paused,
            loop=state.loop_current,
            autoplay=state.autoplay,
            queue_count=len(state.queue),
            accent_color=theme.get("accent_color", "#7f314d"),
            background_url=theme.get("background_url") or None,
            header_text=theme.get("title_text", "BLACK LOUS MUSIC"),
            requester_text=theme.get("card_requester"),
            status_playing_text=theme.get("card_status_playing"),
            status_paused_text=theme.get("card_status_paused"),
            duration_label=theme.get("card_duration"),
            volume_text=theme.get("card_volume"),
            loop_text=theme.get("card_loop"),
            autoplay_text=theme.get("card_autoplay"),
            queue_text=theme.get("card_queue"),
        )
        return await build_player_file(data)

    async def _refresh_player_message(
        self,
        guild_id: int,
        preview_item: AudioItem | None = None,
        *,
        move_to_bottom: bool = False,
    ):
        state = self._get_state(guild_id)
        if preview_item and (not state.current or state.current.item_type != "music"):
            item = preview_item
        else:
            item = state.current
        if not item or item.item_type != "music" or not state.text_channel_id:
            return
        channel = self.bot.get_channel(state.text_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return

        theme = self.player_service.get_theme(guild_id)
        voice_client = state.voice_client
        async with self._player_message_lock(guild_id):
            try:
                player_file = await self._build_player_card_file(
                    guild_id,
                    item,
                    elapsed=(
                        self._playback_seconds(state)
                        + (
                            PLAYER_RENDER_LEAD_SECONDS
                            if voice_client and voice_client.is_playing()
                            else 0
                        )
                    )
                    if state.current
                    else 0,
                    paused=bool(voice_client and voice_client.is_paused()),
                )
                view = MusicPlayerView(self, guild_id, theme)
                message = None
                if (
                    not move_to_bottom
                    and state.player_message_id
                    and state.player_channel_id == channel.id
                ):
                    try:
                        message = await channel.fetch_message(state.player_message_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        message = None
                if message:
                    await message.edit(
                        content=None,
                        embeds=[],
                        attachments=[player_file],
                        view=view,
                    )
                else:
                    await self._delete_player_message_unlocked(state)
                    message = await channel.send(file=player_file, view=view)
                    state.player_message_id = message.id
                    state.player_channel_id = channel.id
            except (discord.Forbidden, discord.HTTPException, OSError, ValueError):
                link_text = f"[{item.title}]({item.webpage_url})" if item.webpage_url else item.title
                fallback = (
                    f"🎧 **Đang phát:** {link_text}\n"
                    f"👤 Yêu cầu bởi: <@{item.requester_id}>"
                )
                await self._delete_player_message_unlocked(state)
                message = await channel.send(content=fallback, view=MusicPlayerView(self, guild_id, theme))
                state.player_message_id = message.id
                state.player_channel_id = channel.id

    @staticmethod
    def _active_tts_requester(state: GuildAudioState) -> int | None:
        voice_client = state.voice_client
        current = state.current
        if (
            current
            and current.item_type == "tts"
            and voice_client
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            return current.requester_id
        return None

    async def _notify_tts_busy(self, ctx, requester_id: int):
        await ctx.reply(
            f"🔊 Bot hiện đang được <@{requester_id}> sử dụng, vui lòng đợi đọc xong.",
            mention_author=False,
        )

    def _can_manage_player_settings(self, member: discord.Member) -> bool:
        if self.admins.is_admin(member.id, member.guild.id):
            return True
        role_ids = [role.id for role in member.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(member.guild.id, role_ids, "play settings")

    async def check_player_settings_interaction(self, interaction: discord.Interaction, guild_id: int) -> bool:
        allowed = (
            interaction.guild_id == guild_id
            and isinstance(interaction.user, discord.Member)
            and self._can_manage_player_settings(interaction.user)
        )
        if allowed:
            return True
        await interaction.response.send_message(
            "❌ Chỉ bot admin hoặc role có quyền `play settings` trong DB mới chỉnh được giao diện.",
            ephemeral=True,
        )
        return False

    async def check_player_interaction(self, interaction: discord.Interaction, guild_id: int) -> bool:
        if interaction.guild_id != guild_id or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Nút này không thuộc server hiện tại.", ephemeral=True)
            return False
        state = self._get_state(guild_id)
        voice_client = self._find_guild_voice_client(interaction.guild) if interaction.guild else None
        voice_client = voice_client or state.voice_client
        if voice_client and voice_client.is_connected():
            state.voice_client = voice_client
        member_channel = getattr(getattr(interaction.user, "voice", None), "channel", None)
        if not voice_client or not voice_client.is_connected() or member_channel != voice_client.channel:
            await interaction.response.send_message(
                "❌ Bạn cần ở cùng voice channel với bot để điều khiển.",
                ephemeral=True,
            )
            return False
        return True

    def _player_settings_embed(self, guild_id: int) -> discord.Embed:
        theme = self.player_service.get_theme(guild_id)
        return build_play_config_embed(theme)

    def player_theme_modal(self, guild_id: int, theme: dict) -> PlayerThemeModal:
        return PlayerThemeModal(self, guild_id, theme)

    async def _show_player_settings(self, ctx, raw: str):
        if not isinstance(ctx.author, discord.Member) or not self._can_manage_player_settings(ctx.author):
            await ctx.send(
                embed=create_error_splash(
                    "❌ Quyền Bị Từ Chối",
                    "Chỉ bot admin hoặc role có quyền `play settings` trong DB mới chỉnh được giao diện.",
                )
            )
            return

        raw = (raw or "").strip()
        if not raw:
            await ctx.send(
                embed=self._player_settings_embed(ctx.guild.id),
                view=PlayConfigMenu(self, ctx.guild.id),
            )
            return

        key, _, value = raw.partition(" ")
        key = key.lower()
        value = value.strip()
        if key in {"reset", "default", "macdinh", "mặcđịnh"}:
            self.player_service.reset_theme(ctx.guild.id)
            await ctx.send(embed=create_success_splash("✅ Đã Reset Player", "Giao diện đã trở về mặc định."))
        elif key in {"accent", "color", "mau", "màu"}:
            normalized = normalize_accent_color(value)
            if normalized != value.lower():
                await ctx.send(embed=create_error_splash("❌ Màu Không Hợp Lệ", "Dùng mã HEX dạng `#7f314d`."))
                return
            self.player_service.set_theme(ctx.guild.id, accent_color=normalized)
            await ctx.send(embed=create_success_splash("✅ Đã Đổi Màu Player", f"Màu chính: `{normalized}`."))
        elif key in {"title", "header", "tieude", "tiêuđề"}:
            if not value:
                await ctx.send(embed=create_error_splash("❌ Thiếu Tiêu Đề", "Nhập nội dung tiêu đề sau `play settings title`."))
                return
            self.player_service.set_theme(ctx.guild.id, title_text=value[:40])
            await ctx.send(embed=create_success_splash("✅ Đã Đổi Tiêu Đề", value[:40]))
        elif key in {"background", "bg", "nen", "nền"}:
            attachment_url = ctx.message.attachments[0].url if ctx.message.attachments else ""
            background_url = attachment_url or value
            if background_url.lower() in {"off", "none", "default", "macdinh", "mặcđịnh"}:
                background_url = ""
            if background_url and not self._is_url(background_url):
                await ctx.send(embed=create_error_splash("❌ Ảnh Nền Không Hợp Lệ", "Hãy gửi URL ảnh hoặc đính kèm ảnh cùng lệnh."))
                return
            self.player_service.set_theme(ctx.guild.id, background_url=background_url)
            text = background_url or "Dùng ảnh trong `ui/bot/assets` hoặc thumbnail bài hát."
            await ctx.send(embed=create_success_splash("✅ Đã Đổi Ảnh Nền", text))
        else:
            await ctx.send(embed=self._player_settings_embed(ctx.guild.id), view=PlayConfigMenu(self, ctx.guild.id))
            return

    async def handle_player_theme_submit(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        *,
        accent: str,
        title_text: str,
        background_url: str,
    ):
        normalized = normalize_accent_color(accent)
        if accent.strip() and normalized != accent.strip().lower():
            await interaction.response.send_message("❌ Màu phải có dạng HEX, ví dụ `#7f314d`.", ephemeral=True)
            return
        background_url = background_url.strip()
        if background_url and not self._is_url(background_url):
            await interaction.response.send_message("❌ URL ảnh nền không hợp lệ.", ephemeral=True)
            return
        self.player_service.set_theme(
            guild_id,
            accent_color=normalized,
            title_text=(title_text.strip() or "BLACK LOUS MUSIC")[:40],
            background_url=background_url,
        )
        await interaction.response.send_message("✅ Đã lưu giao diện player.", ephemeral=True)
        await self._refresh_player_message(guild_id, move_to_bottom=True)

    async def handle_play_theme_submit(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        key: str,
        value: str,
    ):
        if key not in self.player_service.get_theme(guild_id):
            await interaction.response.send_message("❌ Mục config không hợp lệ.", ephemeral=True)
            return
        value = value.strip().replace("\\n", "\n")
        if value.lower() in {"reset", "default"}:
            default = self.player_service.reset_theme_value(guild_id, key)
            message = f"✅ Đã reset `{key}` về `{default}`."
        else:
            if key.startswith(("icon_", "reaction_")) and not value:
                await interaction.response.send_message("❌ Icon/reaction không được để trống.", ephemeral=True)
                return
            self.player_service.set_theme(guild_id, **{key: value})
            message = f"✅ Đã lưu `{key}`."
        await interaction.response.send_message(message, ephemeral=True)
        await self._refresh_player_message(guild_id, move_to_bottom=True)

    async def handle_player_settings_button(self, interaction: discord.Interaction, guild_id: int):
        if not isinstance(interaction.user, discord.Member) or not self._can_manage_player_settings(interaction.user):
            await interaction.response.send_message(
                "❌ Chỉ bot admin hoặc role có quyền `play settings` trong DB mới chỉnh được giao diện.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=self._player_settings_embed(guild_id),
            view=PlayConfigMenu(self, guild_id),
            ephemeral=True,
        )

    async def reset_player_theme(self, interaction: discord.Interaction, guild_id: int):
        self.player_service.reset_theme(guild_id)
        await interaction.response.send_message("✅ Player đã trở về giao diện mặc định.", ephemeral=True)
        await self._refresh_player_message(guild_id, move_to_bottom=True)

    async def send_player_preview(self, interaction: discord.Interaction, guild_id: int):
        state = self._get_state(guild_id)
        current = state.current if state.current and state.current.item_type == "music" else None
        theme = self.player_service.get_theme(guild_id)
        data = PlayerCardData(
            title=current.title if current else "Tên bài hát đang phát",
            requester=interaction.user.display_name,
            duration=current.duration if current else 245,
            elapsed=self._playback_seconds(state) if current else 72,
            thumbnail=current.thumbnail if current else None,
            volume=int(state.volume * 100),
            paused=bool(state.voice_client and state.voice_client.is_paused()),
            loop=state.loop_current,
            autoplay=state.autoplay,
            queue_count=len(state.queue),
            accent_color=theme.get("accent_color", "#7f314d"),
            background_url=theme.get("background_url") or None,
            header_text=theme.get("title_text", "BLACK LOUS MUSIC"),
            requester_text=theme.get("card_requester"),
            status_playing_text=theme.get("card_status_playing"),
            status_paused_text=theme.get("card_status_paused"),
            duration_label=theme.get("card_duration"),
            volume_text=theme.get("card_volume"),
            loop_text=theme.get("card_loop"),
            autoplay_text=theme.get("card_autoplay"),
            queue_text=theme.get("card_queue"),
        )
        player_file = await build_player_file(data)
        await interaction.response.send_message(
            file=player_file,
            ephemeral=True,
        )

    async def handle_player_volume(self, interaction: discord.Interaction, guild_id: int, raw_volume: str):
        try:
            volume = int(raw_volume)
        except ValueError:
            await interaction.response.send_message("❌ Âm lượng phải là số từ 0 đến 200.", ephemeral=True)
            return
        if volume < 0 or volume > 200:
            await interaction.response.send_message("❌ Âm lượng phải nằm trong khoảng 0-200.", ephemeral=True)
            return
        state = self._get_state(guild_id)
        state.volume = volume / 100
        self._save_user_preferences(state, interaction.user.id, volume=volume)
        voice_client = state.voice_client
        if voice_client and isinstance(voice_client.source, discord.PCMVolumeTransformer):
            voice_client.source.volume = state.volume
        await interaction.response.send_message(f"🔊 Âm lượng: `{volume}%`.", ephemeral=True)
        await self._refresh_player_message(guild_id, move_to_bottom=True)

    async def handle_player_button(self, interaction: discord.Interaction, guild_id: int, action: str):
        state = self._get_state(guild_id)
        voice_client = state.voice_client
        if action == "pause_resume":
            if voice_client and voice_client.is_playing():
                self._pause_playback_clock(state)
                voice_client.pause()
                message = "⏸️ Đã tạm dừng."
            elif voice_client and voice_client.is_paused():
                voice_client.resume()
                self._resume_playback_clock(state)
                message = "▶️ Đã tiếp tục."
            else:
                await interaction.response.send_message("❌ Hiện không có bài đang phát.", ephemeral=True)
                return
            await interaction.response.send_message(message, ephemeral=True)
            await self._refresh_player_message(guild_id, move_to_bottom=True)
            return
        if action == "skip":
            if not voice_client or not voice_client.is_playing():
                await interaction.response.send_message("❌ Hiện không có bài đang phát.", ephemeral=True)
                return
            state.skip_requested = True
            self._cancel_player_card(state)
            await interaction.response.send_message("⏭️ Đã bỏ qua bài hiện tại.", ephemeral=True)
            voice_client.stop()
            return
        if action == "stop":
            state.queue.clear()
            state.loop_current = False
            state.stop_requested = True
            self._cancel_player_card(state)
            self._cancel_player_sync(state)
            await interaction.response.send_message("⏹️ Đã dừng và xóa queue.", ephemeral=True)
            if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
            await self._delete_player_message(guild_id)
            return
        if action == "loop":
            state.loop_current = not state.loop_current
            await interaction.response.send_message(
                f"🔁 Loop: `{'Bật' if state.loop_current else 'Tắt'}`.",
                ephemeral=True,
            )
            await self._refresh_player_message(guild_id, move_to_bottom=True)
            return
        if action == "autoplay":
            state.autoplay = not state.autoplay
            await interaction.response.send_message(
                f"♾️ Autoplay: `{'Bật' if state.autoplay else 'Tắt'}`.",
                ephemeral=True,
            )
            await self._refresh_player_message(guild_id, move_to_bottom=True)
            return
        if action == "shuffle":
            if len(state.queue) < 2:
                await interaction.response.send_message("❌ Queue cần ít nhất 2 bài để trộn.", ephemeral=True)
                return
            random.shuffle(state.queue)
            await interaction.response.send_message(f"🔀 Đã trộn `{len(state.queue)}` bài.", ephemeral=True)
            await self._refresh_player_message(guild_id, move_to_bottom=True)
            return
        if action == "queue":
            lines = []
            if state.current:
                lines.append(f"**Đang phát:** `{self._short_text(state.current.title, 70)}`")
            for index, queued in enumerate(state.queue[:QUEUE_PAGE_SIZE], 1):
                lines.append(f"`{index}.` {self._short_text(queued.title, 80)}")
            if len(state.queue) > QUEUE_PAGE_SIZE:
                lines.append(f"... và `{len(state.queue) - QUEUE_PAGE_SIZE}` bài nữa")
            await interaction.response.send_message(
                embed=create_info_splash("🎶 Queue", "\n".join(lines) if lines else "Queue đang trống."),
                ephemeral=True,
            )
            await self._refresh_player_message(guild_id, move_to_bottom=True)
            return
        if action == "leave":
            if state.voice_owner_id and state.voice_owner_id != interaction.user.id:
                await interaction.response.send_message(
                    f"❌ Chỉ {self._voice_owner_text(state)} mới được cho bot rời voice.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message("🚪 Bot đã rời voice.", ephemeral=True)
            state.queue.clear()
            state.current = None
            state.loop_current = False
            state.stop_requested = True
            self._cancel_idle(state)
            self._cancel_player_card(state)
            self._cancel_player_sync(state)
            if voice_client and voice_client.is_connected():
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                await voice_client.disconnect(force=True)
            state.voice_client = None
            state.stop_requested = False
            state.playback_started_at = None
            state.playback_elapsed = 0.0
            self._clear_voice_owner(state)
            await self._delete_player_message(guild_id)

    async def _show_play_help(self, ctx):
        prefix = ctx.clean_prefix
        embed = create_info_splash(
            "🎧 Music Bot",
            (
                f"`{prefix}join` - bot vào voice của bạn\n"
                f"`{prefix}say <nội dung>` - đọc nội dung bằng giọng Google\n"
                f"`{prefix}play <url|từ khóa|playlist>` - phát nhạc\n"
                f"`{prefix}a <url|từ khóa|playlist>` - viết tắt của play\n\n"
                "**Điều khiển trong play**\n"
                "`play q/queue`, `play sh/shuffle`, `play a/autoplay`, `play s/skip`, `play p/pause`, `play r/resume`, `play st/stop`, `play l/leave`, `play n/now`, `play lo/loop`, `play v/vol <0-200>`, `play rm <số>`, `play c/clear`\n"
                "`play settings` - mở menu chỉnh canvas player"
            ),
        )
        await ctx.send(embed=embed)

    async def _show_queue(self, ctx):
        state = self._get_state(ctx.guild.id)
        lines = []
        if state.current:
            lines.append(f"**Đang phát:** `{self._short_text(state.current.title, 70)}`")
        else:
            lines.append("**Đang phát:** chưa có")

        if state.queue:
            for index, item in enumerate(state.queue[:QUEUE_PAGE_SIZE], 1):
                lines.append(f"`{index}.` {self._short_text(item.title, 80)}")
            if len(state.queue) > QUEUE_PAGE_SIZE:
                lines.append(f"... và `{len(state.queue) - QUEUE_PAGE_SIZE}` bài nữa")
        else:
            lines.append("Queue đang trống.")

        await ctx.send(embed=create_info_splash("🎶 Queue", "\n".join(lines)))

    async def _toggle_autoplay(self, ctx, raw_value: str | None):
        state = self._get_state(ctx.guild.id)
        if raw_value:
            lowered = raw_value.strip().lower()
            if lowered in {"on", "bat", "bật", "true", "1"}:
                state.autoplay = True
            elif lowered in {"off", "tat", "tắt", "false", "0"}:
                state.autoplay = False
            else:
                await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `play autoplay on/off` hoặc `play a`."))
                return
        else:
            state.autoplay = not state.autoplay
        status = "bật" if state.autoplay else "tắt"
        await ctx.send(embed=create_success_splash("✅ Autoplay", f"Autoplay hiện đang **{status}**."))

    async def _handle_play_action(self, ctx, action: str, rest: str):
        state = self._get_state(ctx.guild.id)
        voice_client = self._find_guild_voice_client(ctx.guild) or ctx.voice_client or state.voice_client
        if voice_client and voice_client.is_connected():
            state.voice_client = voice_client

        if action == "debug":
            await self._show_voice_debug(ctx, try_connect=True)
            return
        if action == "voice_test":
            await self._run_voice_test(ctx)
            return
        if action == "settings":
            await self._show_player_settings(ctx, rest)
            return
        if action == "queue":
            await self._show_queue(ctx)
            return
        if action == "shuffle":
            if len(state.queue) < 2:
                await ctx.send(embed=create_error_splash("❌ Queue Ngắn", "Cần ít nhất 2 bài trong queue để shuffle."))
                return
            random.shuffle(state.queue)
            await ctx.send(embed=create_success_splash("✅ Shuffle", f"Đã trộn `{len(state.queue)}` bài trong queue."))
            return
        if action == "autoplay":
            await self._toggle_autoplay(ctx, rest or None)
            return
        if action == "skip":
            if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
                await ctx.send(embed=create_error_splash("❌ Không Có Bài", "Hiện không có bài nào đang phát."))
                return
            state.skip_requested = True
            voice_client.stop()
            await ctx.send(embed=create_success_splash("✅ Skip", "Đã bỏ qua bài hiện tại."))
            return
        if action == "pause":
            if voice_client and voice_client.is_playing():
                self._pause_playback_clock(state)
                voice_client.pause()
                await ctx.send(embed=create_success_splash("✅ Pause", "Đã tạm dừng phát nhạc."))
            else:
                await ctx.send(embed=create_error_splash("❌ Không Phát", "Hiện không có bài nào đang phát."))
            return
        if action == "resume":
            if voice_client and voice_client.is_paused():
                voice_client.resume()
                self._resume_playback_clock(state)
                await ctx.send(embed=create_success_splash("✅ Resume", "Đã tiếp tục phát nhạc."))
            else:
                await ctx.send(embed=create_error_splash("❌ Không Pause", "Bot không đang tạm dừng."))
            return
        if action == "stop":
            state.queue.clear()
            state.loop_current = False
            state.stop_requested = True
            self._cancel_player_card(state)
            self._cancel_player_sync(state)
            if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
            else:
                self._schedule_idle_disconnect(ctx.guild.id)
                state.playback_started_at = None
                state.playback_elapsed = 0.0
            await ctx.send(embed=create_success_splash("✅ Stop", "Đã dừng phát và xóa queue. Bot sẽ tự out sau 5 phút nếu không dùng."))
            await self._delete_player_message(ctx.guild.id)
            return
        if action == "clear":
            count = len(state.queue)
            state.queue.clear()
            await ctx.send(embed=create_success_splash("✅ Clear Queue", f"Đã xóa `{count}` bài khỏi queue."))
            return
        if action == "leave":
            if state.voice_owner_id and state.voice_owner_id != ctx.author.id:
                await ctx.send(
                    embed=create_error_splash(
                        "❌ Không Được Leave",
                        f"Chỉ {self._voice_owner_text(state)} mới được cho bot rời voice.",
                    )
                )
                return
            state.queue.clear()
            state.current = None
            state.loop_current = False
            state.stop_requested = True
            self._cancel_idle(state)
            self._cancel_player_card(state)
            self._cancel_player_sync(state)
            if voice_client and voice_client.is_connected():
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                await voice_client.disconnect(force=True)
            state.voice_client = None
            state.stop_requested = False
            state.playback_started_at = None
            state.playback_elapsed = 0.0
            self._clear_voice_owner(state)
            await ctx.send(embed=create_success_splash("✅ Đã Rời Voice", "Bot đã rời voice channel."))
            await self._delete_player_message(ctx.guild.id)
            return
        if action == "now":
            if not state.current:
                await ctx.send(embed=create_error_splash("❌ Không Có Bài", "Hiện chưa có bài nào đang phát."))
                return
            return
        if action == "volume":
            if not rest:
                await ctx.send(embed=create_info_splash("🔊 Volume", f"Volume hiện tại: `{int(state.volume * 100)}%`."))
                return
            try:
                volume = int(rest.strip())
            except ValueError:
                await ctx.send(embed=create_error_splash("❌ Sai Volume", "Volume phải là số từ 0 đến 200."))
                return
            if volume < 0 or volume > 200:
                await ctx.send(embed=create_error_splash("❌ Sai Volume", "Volume phải nằm trong khoảng 0-200."))
                return
            state.volume = volume / 100
            self._save_user_preferences(state, ctx.author.id, volume=volume)
            if voice_client and voice_client.source and isinstance(voice_client.source, discord.PCMVolumeTransformer):
                voice_client.source.volume = state.volume
            await ctx.send(embed=create_success_splash("✅ Volume", f"Đã set volume thành `{volume}%`."))
            return
        if action == "loop":
            if rest:
                lowered = rest.strip().lower()
                if lowered in {"on", "bat", "bật", "true", "1"}:
                    state.loop_current = True
                elif lowered in {"off", "tat", "tắt", "false", "0"}:
                    state.loop_current = False
                else:
                    await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `play loop on/off` hoặc `play loop`."))
                    return
            else:
                state.loop_current = not state.loop_current
            status = "bật" if state.loop_current else "tắt"
            await ctx.send(embed=create_success_splash("✅ Loop", f"Loop bài hiện tại đang **{status}**."))
            return
        if action == "remove":
            if not rest:
                await ctx.send(embed=create_error_splash("❌ Thiếu Số Thứ Tự", "Dùng: `play rm <số trong queue>`."))
                return
            try:
                index = int(rest.strip())
            except ValueError:
                await ctx.send(embed=create_error_splash("❌ Sai Số", "Số thứ tự phải là số nguyên."))
                return
            if index < 1 or index > len(state.queue):
                await ctx.send(embed=create_error_splash("❌ Ngoài Queue", f"Queue hiện có `{len(state.queue)}` bài."))
                return
            removed = state.queue.pop(index - 1)
            await ctx.send(embed=create_success_splash("✅ Đã Xóa Khỏi Queue", f"Đã xóa `{removed.title}`."))

    async def _add_music(self, ctx, query: str):
        if not await self._require_ffmpeg(ctx):
            return
        if not await self._require_package(ctx, "yt_dlp", "yt-dlp"):
            return

        voice_client = await self._ensure_voice(ctx)
        if not voice_client:
            return

        state = self._get_state(ctx.guild.id)
        state.text_channel_id = ctx.channel.id
        has_music_session = bool(
            (state.current and state.current.item_type == "music")
            or any(item.item_type == "music" for item in state.queue)
        )
        starting_new_session = not has_music_session
        if starting_new_session:
            self._apply_user_preferences(state, ctx.author.id)

        try:
            async with ctx.typing():
                items = await self._extract_music_items(query, ctx.author)
        except asyncio.TimeoutError:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Tìm Nhạc Timeout",
                    "Nguồn nhạc phản hồi quá lâu. Thử gửi link YouTube trực tiếp hoặc tìm lại bằng tên ngắn hơn.",
                )
            )
            await self._try_react(ctx.message, self._play_reaction(ctx.guild.id, "reaction_error"))
            return
        except Exception as exc:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Không Tìm Được Nhạc",
                    f"{exc}\nNếu Spotify URL không chạy, hãy gửi tên bài hoặc link YouTube/YT Music tương ứng.",
                )
            )
            await self._try_react(ctx.message, self._play_reaction(ctx.guild.id, "reaction_error"))
            return

        if not items:
            await ctx.send(embed=create_error_splash("❌ Không Có Kết Quả", "Không tìm thấy bài/playlist phù hợp."))
            await self._try_react(ctx.message, self._play_reaction(ctx.guild.id, "reaction_error"))
            return

        queue_position = len(state.queue) + 1
        state.queue.extend(items)
        await self._start_player_if_needed(ctx.guild.id)
        await self._try_react(ctx.message, self._play_reaction(ctx.guild.id, "reaction_success"))
        if not starting_new_session:
            await ctx.send(
                embed=self._queue_added_embed(
                    ctx.guild.id,
                    items,
                    queue_position,
                )
            )
            await self._refresh_player_message(ctx.guild.id, move_to_bottom=True)

    @commands.command(name="join", aliases=["j"])
    async def join(self, ctx):
        voice_client = await self._ensure_voice(ctx)
        if not voice_client:
            return
        state = self._get_state(ctx.guild.id)
        await ctx.send(embed=create_success_splash("✅ Đã Vào Voice", f"Bot đã vào `{voice_client.channel.name}`.\nNgười giữ quyền leave: {self._voice_owner_text(state)}."))

    @commands.command(name="say", aliases=["s"])
    async def say(self, ctx, *, text: str = None):
        if not text or not text.strip():
            await ctx.send(embed=create_error_splash("❌ Thiếu Nội Dung", "Dùng: `say <nội dung>` để bot đọc bằng giọng Google."))
            return
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh `say` chỉ hoạt động trong server."))
            return

        state = self._get_state(ctx.guild.id)
        active_requester = self._active_tts_requester(state)
        if active_requester and active_requester != ctx.author.id:
            await self._notify_tts_busy(ctx, active_requester)
            return

        await self._try_react(ctx.message, "✅")
        if not await self._require_ffmpeg(ctx):
            await self._try_react(ctx.message, "❌")
            return
        if not await self._require_package(ctx, "gtts", "gTTS"):
            await self._try_react(ctx.message, "❌")
            return

        voice_client = await self._ensure_voice(ctx)
        if not voice_client:
            await self._try_react(ctx.message, "❌")
            return

        text = text.strip()
        if len(text) > 500:
            await ctx.send(embed=create_error_splash("❌ Nội Dung Quá Dài", "Tạm giới hạn 500 ký tự mỗi lần đọc để tránh kẹt queue."))
            await self._try_react(ctx.message, "❌")
            return

        try:
            async with ctx.typing():
                item = await self._create_tts_item(ctx, text)
        except asyncio.TimeoutError:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Tạo Giọng Đọc Timeout",
                    "Google TTS phản hồi quá lâu. Thử lại sau vài giây hoặc rút ngắn nội dung cần đọc.",
                )
            )
            await self._try_react(ctx.message, "❌")
            return
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Tạo Giọng Đọc Thất Bại", str(exc)))
            await self._try_react(ctx.message, "❌")
            return

        active_requester = self._active_tts_requester(state)
        if active_requester and active_requester != ctx.author.id:
            await self._cleanup_item(item)
            await self._notify_tts_busy(ctx, active_requester)
            return

        state.text_channel_id = ctx.channel.id
        state.queue.append(item)
        await self._start_player_if_needed(ctx.guild.id)

    @commands.command(name="leave", aliases=["l", "disconnect", "dc"])
    async def leave(self, ctx):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh `leave` chỉ hoạt động trong server."))
            return
        await self._handle_play_action(ctx, "leave", "")

    @commands.command(name="play", aliases=["a", "p"])
    async def play(self, ctx, *, content: str = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh `play` chỉ hoạt động trong server."))
            return
        if not content or not content.strip():
            await self._show_play_help(ctx)
            return

        content = content.strip()
        first, _, rest = content.partition(" ")
        action = self.PLAY_ACTIONS.get(first.lower())
        if action:
            await self._handle_play_action(ctx, action, rest.strip())
            state = self._get_state(ctx.guild.id)
            if (
                action not in {"skip", "stop", "leave"}
                and state.current
                and state.current.item_type == "music"
            ):
                await self._refresh_player_message(ctx.guild.id, move_to_bottom=True)
            return

        await self._add_music(ctx, content)


async def setup(bot):
    await bot.add_cog(BotVoiceCog(bot))
