from __future__ import annotations

import asyncio
import random
import re
import shlex
import time
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    format_duration_seconds,
    parse_duration,
)
from services.giveaway_service import GiveawayService
from utils import append_discord_timestamp
from ui.administrator.giveaway_emoji import (
    GIVEAWAY_CUSTOM_EMOJI_RE,
    GIVEAWAY_DEFAULT_ENTRY_EMOJI,
    GIVEAWAY_THEME_DEFAULTS,
    giveaway_icon,
    giveaway_theme_key,
    giveaway_theme_value,
)
from ui.administrator.giveaway_ui import (
    GiveawayConfigView,
    GiveawayManualSetView,
    build_giveaway_config_embed,
)


MAX_GIVEAWAY_QUANTITY = 20


@dataclass
class GiveawayCreatePayload:
    reward: str
    duration_seconds: int
    winners_count: int
    quantity: int = 1
    template: str = ""


class AdministratorGiveawayCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.service = GiveawayService()
        self._end_tasks: dict[int, asyncio.Task] = {}
        self._restored = False

    def cog_unload(self):
        for task in self._end_tasks.values():
            task.cancel()
        self._end_tasks.clear()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.restore_active_giveaways()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        giveaway = self.service.get_giveaway_by_message_id(int(payload.message_id))
        if not giveaway:
            return
        if not self._emoji_matches(payload.emoji, self.giveaway_entry_emoji(giveaway)):
            return
        giveaway_id = int(giveaway["giveaway_id"])
        if giveaway["status"] != "active":
            return

        username = None
        if payload.member:
            username = payload.member.display_name
        if not username:
            try:
                user = self.bot.get_user(payload.user_id) or await self.bot.fetch_user(payload.user_id)
                username = getattr(user, "display_name", user.name)
            except (discord.NotFound, discord.HTTPException):
                username = str(payload.user_id)

        self.service.add_participant(giveaway_id, payload.user_id, username)
        await self.refresh_giveaway_message(giveaway_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        giveaway = self.service.get_giveaway_by_message_id(int(payload.message_id))
        if not giveaway or giveaway["status"] != "active":
            return
        if not self._emoji_matches(payload.emoji, self.giveaway_entry_emoji(giveaway)):
            return
        self.service.remove_participant(int(giveaway["giveaway_id"]), payload.user_id)
        await self.refresh_giveaway_message(int(giveaway["giveaway_id"]))

    async def restore_active_giveaways(self):
        if self._restored:
            return
        self._restored = True
        for giveaway in self.service.get_active_giveaways():
            giveaway_id = int(giveaway["giveaway_id"])
            await self.refresh_giveaway_message(giveaway_id, schedule_end=True)

    @staticmethod
    async def _delete_invocation_message(ctx):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    @staticmethod
    def _is_duration_token(token: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:\.\d+)?[smhd]", token.strip().lower()))

    @staticmethod
    def _is_positive_int_token(token: str) -> bool:
        return bool(re.fullmatch(r"\d+", token.strip()))

    def _parse_prefix_payload(self, content: str) -> GiveawayCreatePayload:
        raw = (content or "").strip()
        if not raw:
            raise ValueError("Dùng: `ga 1d 1 100k 10`.")

        tokens = shlex.split(raw)
        if tokens and tokens[0].lower() in {"create", "c", "tao", "tạo"}:
            tokens = tokens[1:]
        if len(tokens) < 3:
            raise ValueError("Thiếu dữ liệu. Dùng: `ga <thời gian> <số người win> <nội dung> [số lượng ga]`.")

        duration_index = None
        duration_seconds = None
        for index, token in enumerate(tokens):
            if not self._is_duration_token(token):
                continue
            duration_seconds = parse_duration(token)
            duration_index = index
            break
        if duration_index is None or not duration_seconds:
            raise ValueError("Thiếu thời gian. Ví dụ: `10m`, `1h`, `1d`.")

        remaining = [(index, token) for index, token in enumerate(tokens) if index != duration_index]
        int_positions = [
            (position, token)
            for position, token in remaining
            if self._is_positive_int_token(token)
        ]
        if not int_positions:
            raise ValueError("Thiếu số lượng người win. Ví dụ: `ga 1d 1 100k`.")

        winners_position, winners_token = int_positions[0]
        quantity = 1
        quantity_position = None
        if len(int_positions) >= 2 and int_positions[-1][0] == remaining[-1][0]:
            quantity_position, quantity_token = int_positions[-1]
            quantity = int(quantity_token)

        winners_count = int(winners_token)
        reward_tokens = [
            token
            for position, token in remaining
            if position not in {winners_position, quantity_position}
        ]
        reward = " ".join(reward_tokens).strip()

        return self._validate_payload(
            GiveawayCreatePayload(
                reward=reward,
                duration_seconds=int(duration_seconds),
                winners_count=winners_count,
                quantity=quantity,
            )
        )

    def _validate_payload(self, payload: GiveawayCreatePayload) -> GiveawayCreatePayload:
        payload.reward = payload.reward.strip()
        payload.template = (payload.template or "").strip()
        if not payload.reward:
            raise ValueError("Nội dung phần thưởng không được để trống.")
        if payload.duration_seconds <= 0:
            raise ValueError("Thời gian giveaway phải lớn hơn 0.")
        if payload.winners_count <= 0:
            raise ValueError("Số người win phải lớn hơn 0.")
        if payload.quantity <= 0:
            raise ValueError("Số lượng giveaway phải lớn hơn 0.")
        if payload.quantity > MAX_GIVEAWAY_QUANTITY:
            raise ValueError(f"Tối đa chỉ tạo `{MAX_GIVEAWAY_QUANTITY}` giveaway một lần để tránh spam.")
        if len(payload.reward) > 250:
            raise ValueError("Nội dung phần thưởng tối đa 250 ký tự.")
        if len(payload.template) > 500:
            raise ValueError("Template tối đa 500 ký tự.")
        return payload

    @staticmethod
    def _custom_emoji_id(raw: str) -> int | None:
        match = GIVEAWAY_CUSTOM_EMOJI_RE.fullmatch(str(raw or "").strip())
        return int(match.group("id")) if match else None

    @staticmethod
    def _custom_emoji_name(raw: str) -> str | None:
        match = GIVEAWAY_CUSTOM_EMOJI_RE.fullmatch(str(raw or "").strip())
        return match.group("name") if match else None

    def normalize_entry_emoji(self, guild: discord.Guild | None, raw_emoji: str) -> str:
        raw = str(raw_emoji or "").strip()
        if not raw:
            return GIVEAWAY_DEFAULT_ENTRY_EMOJI
        if GIVEAWAY_CUSTOM_EMOJI_RE.fullmatch(raw):
            return raw
        if raw.startswith(":") and raw.endswith(":") and raw.count(":") == 2:
            raw = raw.strip(":")
        if guild and raw.isdigit():
            emoji = guild.get_emoji(int(raw))
            if emoji:
                return str(emoji)
        if guild:
            lowered = raw.strip(":").lower()
            for emoji in guild.emojis:
                if emoji.name.lower() == lowered:
                    return str(emoji)
        return raw

    @staticmethod
    def _emoji_name_candidate(raw_emoji: str) -> str | None:
        raw = str(raw_emoji or "").strip()
        if raw.startswith(":") and raw.endswith(":") and raw.count(":") == 2:
            raw = raw.strip(":")
        if re.fullmatch(r"[A-Za-z0-9_~]{2,32}", raw):
            return raw.lower()
        return None

    async def resolve_entry_emoji_input(self, guild: discord.Guild | None, raw_emoji: str) -> str:
        raw = str(raw_emoji or "").strip()
        if not raw:
            return GIVEAWAY_DEFAULT_ENTRY_EMOJI
        if GIVEAWAY_CUSTOM_EMOJI_RE.fullmatch(raw):
            return raw

        if raw.isdigit():
            emoji = (guild.get_emoji(int(raw)) if guild else None) or self.bot.get_emoji(int(raw))
            if emoji:
                return str(emoji)
            raise ValueError("Không tìm thấy emoji theo ID đó. Hãy dùng emoji trực tiếp hoặc emoji trong server bot đang thấy.")

        name = self._emoji_name_candidate(raw)
        if name and guild:
            for emoji in guild.emojis:
                if emoji.name.lower() == name:
                    return str(emoji)
            for emoji in self.bot.emojis:
                if emoji.name.lower() == name:
                    return str(emoji)
            try:
                fetched_emojis = await guild.fetch_emojis()
            except discord.HTTPException:
                fetched_emojis = []
            for emoji in fetched_emojis:
                if emoji.name.lower() == name:
                    return str(emoji)
            raise ValueError("Không tìm thấy emoji trong server. Hãy gửi emoji trực tiếp dạng `<:tên:id>` hoặc `<a:tên:id>`.")

        return self.normalize_entry_emoji(guild, raw)

    def get_entry_emoji(self, guild_id: int) -> str:
        return self.service.get_entry_emoji(guild_id)

    def giveaway_entry_emoji(self, giveaway: dict) -> str:
        return str(giveaway.get("entry_emoji") or self.get_entry_emoji(int(giveaway["guild_id"])) or GIVEAWAY_DEFAULT_ENTRY_EMOJI)

    def giveaway_entry_emoji_for_ui(self, giveaway: dict) -> str | discord.PartialEmoji:
        emoji = self.giveaway_entry_emoji(giveaway)
        if GIVEAWAY_CUSTOM_EMOJI_RE.fullmatch(emoji):
            return discord.PartialEmoji.from_str(emoji)
        return emoji

    def giveaway_entry_emoji_for_reaction(self, giveaway: dict) -> str | discord.PartialEmoji:
        return self.giveaway_entry_emoji_for_ui(giveaway)

    def _emoji_matches(self, payload_emoji: discord.PartialEmoji, expected_emoji: str) -> bool:
        expected = str(expected_emoji or GIVEAWAY_DEFAULT_ENTRY_EMOJI)
        expected_id = self._custom_emoji_id(expected)
        if expected_id is not None:
            return int(payload_emoji.id or 0) == expected_id
        expected_name = self._custom_emoji_name(expected)
        if expected_name:
            return str(payload_emoji.name or "") == expected_name
        return str(payload_emoji) == expected

    async def _add_entry_reaction(self, message: discord.Message, giveaway: dict) -> bool:
        try:
            await message.add_reaction(self.giveaway_entry_emoji_for_reaction(giveaway))
            return True
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"❌ Không thêm được emoji giveaway {giveaway.get('giveaway_id')}: {exc}")
            return False

    async def _send_interaction_splash(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        ephemeral: bool = True,
        view: discord.ui.View | None = None,
    ):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

    def _giveaway_theme(self, giveaway: dict | None) -> dict[str, str]:
        if not giveaway:
            return {}
        return self.service.get_theme(int(giveaway["guild_id"]))

    @staticmethod
    def _format_theme_template(template: str, **values) -> str:
        try:
            return str(template).format(**values)
        except (KeyError, ValueError):
            return str(template)

    def _theme_value(self, giveaway: dict | None, key: str, **values) -> str:
        template = giveaway_theme_value(self._giveaway_theme(giveaway), key)
        return self._format_theme_template(template, **values) if values else template

    def _theme_icon(self, giveaway: dict | None, key: str) -> str:
        return self._theme_value(giveaway, f"icon_{key}")

    @staticmethod
    def _clean_theme_label(value: str) -> str:
        return re.sub(r"\*+", "", value).strip().rstrip(":").strip()

    def _theme_label(self, giveaway: dict | None, key: str) -> str:
        return self._clean_theme_label(self._theme_value(giveaway, key))

    def _giveaway_host_avatar_url(self, giveaway: dict) -> str | None:
        creator_id = int(giveaway["creator_id"])
        guild = self.bot.get_guild(int(giveaway["guild_id"]))
        host = guild.get_member(creator_id) if guild else None
        host = host or self.bot.get_user(creator_id)
        return str(host.display_avatar.url) if host else None

    def _winner_mentions(self, giveaway: dict) -> str:
        winner_ids = self.service.decode_winner_ids(giveaway)
        return ", ".join(f"<@{user_id}>" for user_id in winner_ids) if winner_ids else "`Không có`"

    def _giveaway_content(self, giveaway: dict, ended: bool = False) -> str:
        status_ended = ended or giveaway["status"] == "ended"
        title_key = "title_ended" if status_ended else "title_start"
        reward = str(giveaway["reward"])
        return self._theme_value(
            giveaway,
            title_key,
            start=self._theme_icon(giveaway, "start"),
            ended=self._theme_icon(giveaway, "ended"),
            reward=reward,
            emoji=self.giveaway_entry_emoji(giveaway),
            host=f"<@{int(giveaway['creator_id'])}>",
            winners=self._winner_mentions(giveaway),
            time=f"<t:{int(giveaway['ends_at'])}:R>",
        )

    def _build_giveaway_embed(self, giveaway: dict, ended: bool = False) -> discord.Embed:
        selected_winner_ids = self.service.decode_selected_winner_ids(giveaway)
        entry_emoji = self.giveaway_entry_emoji(giveaway)
        status_text = "Đã kết thúc" if ended or giveaway["status"] == "ended" else "Đang mở"
        color = discord.Color.from_rgb(255, 136, 190) if status_text == "Đang mở" else discord.Color.from_rgb(89, 96, 110)
        reward = str(giveaway["reward"])
        description_key = "text_join" if status_text == "Đang mở" else "text_ended"
        host_mention = f"<@{int(giveaway['creator_id'])}>"
        description_lines = [f"## {reward}", ""]
        status_description = self._theme_value(
            giveaway,
            description_key,
            emoji=entry_emoji,
            reward=reward,
            host=host_mention,
            winners=self._winner_mentions(giveaway),
        ).strip()
        if status_description:
            description_lines.append(status_description)

        if status_text == "Đã kết thúc":
            description_lines.extend(
                [
                    f"{self._theme_icon(giveaway, 'winner')} **{self._theme_label(giveaway, 'label_winner')}:** {self._winner_mentions(giveaway)}",
                    f"{self._theme_icon(giveaway, 'host')} **{self._theme_label(giveaway, 'label_host')}:** {host_mention}",
                ]
            )
        else:
            ends_at = int(giveaway["ends_at"])
            description_lines.extend(
                [
                    f"{self._theme_icon(giveaway, 'time')} **{self._theme_label(giveaway, 'label_time')}:** <t:{ends_at}:R>",
                    f"{self._theme_icon(giveaway, 'host')} **{self._theme_label(giveaway, 'label_host')}:** {host_mention}",
                ]
            )
            if selected_winner_ids:
                selected_text = ", ".join(f"<@{user_id}>" for user_id in selected_winner_ids)
                description_lines.append(
                    f"{self._theme_icon(giveaway, 'selected')} "
                    f"**{self._theme_label(giveaway, 'label_selected')}:** {selected_text}"
                )

        embed = discord.Embed(
            description="\n".join(description_lines),
            color=color,
        )

        guild = self.bot.get_guild(int(giveaway["guild_id"]))
        if guild:
            embed.set_author(
                name=guild.name,
                icon_url=str(guild.icon.url) if guild.icon else None,
            )

        if int(giveaway.get("quantity_total") or 1) > 1:
            embed.add_field(
                name=f"{self._theme_icon(giveaway, 'package')} {self._theme_label(giveaway, 'label_package')}",
                value=f"`{int(giveaway['quantity_index'])}/{int(giveaway['quantity_total'])}`",
                inline=False,
            )
        if giveaway.get("template"):
            embed.add_field(
                name=f"{self._theme_icon(giveaway, 'template')} {self._theme_label(giveaway, 'label_template')}",
                value=str(giveaway["template"])[:1024],
                inline=False,
            )

        host_avatar_url = self._giveaway_host_avatar_url(giveaway)
        if host_avatar_url:
            embed.set_thumbnail(url=host_avatar_url)
        append_discord_timestamp(embed)
        return embed

    def _build_result_embed(self, giveaway: dict, winner_ids: list[int], title: str) -> discord.Embed:
        if winner_ids:
            winners_text = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
            description = f"{winners_text}\nBạn đã thắng **{giveaway['reward']}**."
            color = discord.Color.green()
        else:
            description = "Không có người tham gia nên giveaway không có winner."
            color = discord.Color.red()
        embed = discord.Embed(title=title, description=description, color=color)
        embed.add_field(name="Phần thưởng", value=str(giveaway["reward"])[:1024], inline=False)
        return embed

    async def _send_winner_dms(self, giveaway: dict, winner_ids: list[int], reroll: bool = False, reroll_round: int | None = None):
        if not winner_ids:
            return

        guild = self.bot.get_guild(int(giveaway["guild_id"]))
        guild_name = guild.name if guild else "server"
        action_text = f"trúng thưởng reroll lần {reroll_round}" if reroll and reroll_round else "trúng thưởng"
        content_template = self._theme_value(giveaway, "dm_winner")
        for user_id in winner_ids:
            try:
                user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                await user.send(
                    self._format_theme_template(
                        content_template,
                        dm=self._theme_icon(giveaway, "dm"),
                        action=action_text,
                        reward=giveaway["reward"],
                        guild=guild_name,
                        user=user.mention,
                        host=f"<@{int(giveaway['creator_id'])}>",
                    )
                )
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                continue

    async def _send_result_message(self, channel, giveaway: dict, winner_ids: list[int], reroll: bool = False, reroll_round: int | None = None):
        if winner_ids:
            winners_text = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
            if reroll and reroll_round:
                content = self._theme_value(
                    giveaway,
                    "result_reroll",
                    icon=self._theme_icon(giveaway, "reroll"),
                    winners=winners_text,
                    reward=giveaway["reward"],
                    host=f"<@{int(giveaway['creator_id'])}>",
                    round=reroll_round,
                )
            else:
                content = self._theme_value(
                    giveaway,
                    "result_winner",
                    icon=self._theme_icon(giveaway, "result"),
                    winners=winners_text,
                    reward=giveaway["reward"],
                    host=f"<@{int(giveaway['creator_id'])}>",
                )
        else:
            content = self._theme_value(
                giveaway,
                "result_no_winner",
                icon=self._theme_icon(giveaway, "result"),
                reward=giveaway["reward"],
                host=f"<@{int(giveaway['creator_id'])}>",
            )
        try:
            await channel.send(content)
        except discord.HTTPException:
            pass

    async def _finish_giveaway_with_winners(self, giveaway_id: int, winner_ids: list[int], reroll: bool = False) -> tuple[bool, str]:
        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            return False, "Giveaway không tồn tại."

        if giveaway["status"] == "active":
            self.service.mark_ended(giveaway_id, winner_ids)
            task = self._end_tasks.pop(giveaway_id, None)
            current_task = asyncio.current_task()
            if task and task is not current_task and not task.done():
                task.cancel()
        else:
            self.service.update_winners(giveaway_id, winner_ids)
            reroll = True

        updated = self.service.get_giveaway(giveaway_id)
        message = await self._fetch_giveaway_message(updated)
        if message:
            await message.edit(
                content=self._giveaway_content(updated, ended=True),
                embed=self._build_giveaway_embed(updated, ended=True),
                view=None,
            )
            await self._send_result_message(message.channel, updated, winner_ids, reroll=reroll)
        await self._send_winner_dms(updated, winner_ids, reroll=reroll)
        return True, "Đã chọn winner và kết thúc giveaway."

    def _build_manual_set_embed(self, giveaway: dict, participants: list[dict]) -> discord.Embed:
        winners_count = int(giveaway["winners_count"])
        selected_winner_ids = self.service.decode_selected_winner_ids(giveaway)
        embed = create_info_splash(
            f"{self._theme_icon(giveaway, 'set')} Set Giveaway",
            (
                f"**Phần thưởng:** {giveaway['reward']}\n"
                f"**Số winner cần chọn:** `{winners_count}`\n"
                "Chọn winner trong menu hoặc bấm **Random winner**.\n"
                "Winner chỉ được lưu lại, giveaway vẫn chạy tới hết giờ mới trả thưởng."
            ),
        )
        if selected_winner_ids:
            embed.add_field(
                name="Winner đã lưu",
                value=", ".join(f"<@{user_id}>" for user_id in selected_winner_ids),
                inline=False,
            )
        if not participants:
            embed.add_field(name="Người tham gia", value="Chưa có ai tham gia.", inline=False)
            return embed

        lines = [
            f"`{index}.` <@{int(row['user_id'])}> - `{row['username']}`"
            for index, row in enumerate(participants[:40], 1)
        ]
        if len(participants) > 40:
            lines.append(f"... và `{len(participants) - 40}` người nữa")
        embed.add_field(name=f"Người tham gia ({len(participants)})", value="\n".join(lines), inline=False)
        if len(participants) > 25:
            embed.add_field(
                name="Lưu ý",
                value="Discord chỉ cho menu chọn tối đa 25 người đầu. Nếu cần chọn người ngoài danh sách này, dùng random hoặc reroll sau.",
                inline=False,
            )
        return embed

    async def _show_manual_set_panel(self, interaction: discord.Interaction, giveaway_id: int):
        if not self.admins.is_hard_admin(interaction.user.id):
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng lệnh này."),
            )
            return

        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Giveaway Không Tồn Tại", f"Không tìm thấy giveaway `{giveaway_id}`."),
            )
            return
        if giveaway["status"] != "active":
            await self._send_interaction_splash(
                interaction,
                create_error_splash(
                    "❌ Giveaway Đã Kết Thúc",
                    "Chỉ có thể set winner trước khi giveaway kết thúc. Hãy dùng reroll cho giveaway đã kết thúc.",
                ),
            )
            return

        await interaction.response.defer(ephemeral=interaction.guild is not None, thinking=True)
        participants = await self._sync_reaction_participants(giveaway)
        embed = self._build_manual_set_embed(giveaway, participants)
        view = GiveawayManualSetView(self, giveaway, participants)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _save_selected_winners_interaction(self, interaction: discord.Interaction, giveaway_id: int, winner_ids: list[int]):
        if not self.admins.is_hard_admin(interaction.user.id):
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng thao tác này."),
            )
            return
        if not interaction.response.is_done():
            await interaction.response.defer()

        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Giveaway Không Tồn Tại", f"Không tìm thấy giveaway `{giveaway_id}`."),
                view=None,
            )
            return
        if giveaway["status"] != "active":
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Giveaway Đã Kết Thúc", "Giveaway đã kết thúc. Hãy dùng reroll nếu muốn quay lại winner."),
                view=None,
            )
            return

        participants = await self._sync_reaction_participants(giveaway)
        participant_ids = {int(row["user_id"]) for row in participants}
        winner_ids = list(dict.fromkeys(int(user_id) for user_id in winner_ids))
        if not winner_ids or any(user_id not in participant_ids for user_id in winner_ids):
            await interaction.edit_original_response(
                embed=create_error_splash(
                    "❌ Winner Không Hợp Lệ",
                    "Winner phải nằm trong danh sách người đã react tham gia giveaway.",
                ),
                view=None,
            )
            return
        if len(winner_ids) > int(giveaway["winners_count"]):
            await interaction.edit_original_response(
                embed=create_error_splash(
                    "❌ Quá Số Winner",
                    f"Giveaway này chỉ cho chọn tối đa `{int(giveaway['winners_count'])}` winner.",
                ),
                view=None,
            )
            return

        self.service.set_selected_winners(giveaway_id, winner_ids)
        await self.refresh_giveaway_message(giveaway_id)
        winners_text = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
        await interaction.edit_original_response(
            embed=create_success_splash(
                "✅ Đã Lưu Winner",
                f"Winner đã chọn: {winners_text}\nGiveaway vẫn chạy tới hết giờ rồi mới trả thưởng.",
            ),
            view=None,
        )

    async def _random_winners_interaction(self, interaction: discord.Interaction, giveaway_id: int):
        if not self.admins.is_hard_admin(interaction.user.id):
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng thao tác này."),
            )
            return
        if not interaction.response.is_done():
            await interaction.response.defer()

        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Giveaway Không Tồn Tại", f"Không tìm thấy giveaway `{giveaway_id}`."),
                view=None,
            )
            return

        if giveaway["status"] != "active":
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Giveaway Đã Kết Thúc", "Giveaway đã kết thúc. Hãy dùng reroll nếu muốn quay lại winner."),
                view=None,
            )
            return

        participants = await self._sync_reaction_participants(giveaway)
        winner_ids = self._pick_winners(participants, int(giveaway["winners_count"]))
        if not winner_ids:
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Chưa Có Người Tham Gia", "Không có ai trong danh sách tham gia để random."),
                view=None,
            )
            return
        await self._save_selected_winners_interaction(interaction, giveaway_id, winner_ids)

    async def _fetch_giveaway_message(self, giveaway: dict) -> discord.Message | None:
        channel = self.bot.get_channel(int(giveaway["channel_id"]))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(giveaway["channel_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        try:
            return await channel.fetch_message(int(giveaway["message_id"]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _sync_reaction_participants(
        self,
        giveaway: dict,
        message: discord.Message | None = None,
    ) -> list[dict]:
        message = message or await self._fetch_giveaway_message(giveaway)
        if not message:
            return self.service.get_participants(int(giveaway["giveaway_id"]))

        expected_emoji = self.giveaway_entry_emoji(giveaway)
        expected_id = self._custom_emoji_id(expected_emoji)
        for reaction in message.reactions:
            reaction_id = getattr(reaction.emoji, "id", None)
            if expected_id is not None:
                matched = int(reaction_id or 0) == expected_id
            else:
                matched = str(reaction.emoji) == expected_emoji
            if not matched:
                continue
            try:
                async for user in reaction.users(limit=None):
                    if user.bot:
                        continue
                    username = getattr(user, "display_name", None) or user.name
                    self.service.sync_participant(
                        int(giveaway["giveaway_id"]),
                        int(user.id),
                        username,
                    )
            except (discord.Forbidden, discord.HTTPException):
                pass
            break
        return self.service.get_participants(int(giveaway["giveaway_id"]))

    async def refresh_giveaway_message(self, giveaway_id: int, schedule_end: bool = False):
        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            return
        message = await self._fetch_giveaway_message(giveaway)
        if message:
            ended = giveaway["status"] == "ended"
            if not ended:
                discord_ends_at = int(message.created_at.timestamp()) + int(giveaway["duration_seconds"])
                if int(giveaway["ends_at"]) != discord_ends_at:
                    self.service.update_ends_at(giveaway_id, discord_ends_at)
                    giveaway["ends_at"] = discord_ends_at
            edited_message = await message.edit(
                content=self._giveaway_content(giveaway, ended),
                embed=self._build_giveaway_embed(giveaway, ended),
                view=None,
            )
            remaining_seconds = self._giveaway_delay_seconds(giveaway)
            if not ended and remaining_seconds <= 0:
                await self._end_giveaway(giveaway_id, automatic=True)
                return
            if not ended:
                await self._add_entry_reaction(message, giveaway)
                if schedule_end:
                    self._schedule_end(giveaway)

    async def _create_one_giveaway(
        self,
        channel: discord.abc.Messageable,
        guild_id: int,
        creator_id: int,
        payload: GiveawayCreatePayload,
        quantity_index: int,
    ) -> int:
        theme = self.service.get_theme(guild_id)
        start_icon = giveaway_theme_value(theme, "icon_start")
        placeholder = discord.Embed(
            title=f"{start_icon} GIVEAWAY",
            description="Đang khởi tạo giveaway...",
            color=discord.Color.from_rgb(255, 136, 190),
        )
        message = await channel.send(embed=placeholder)
        ends_at = int(message.created_at.timestamp()) + int(payload.duration_seconds)
        giveaway_id = int(message.id)
        self.service.create_giveaway(
            giveaway_id=giveaway_id,
            guild_id=guild_id,
            channel_id=message.channel.id,
            message_id=message.id,
            creator_id=creator_id,
            reward=payload.reward,
            duration_seconds=payload.duration_seconds,
            winners_count=payload.winners_count,
            ends_at=ends_at,
            quantity_total=payload.quantity,
            quantity_index=quantity_index,
            template=payload.template,
            entry_emoji=self.get_entry_emoji(guild_id),
        )
        giveaway = self.service.get_giveaway(giveaway_id)
        await message.edit(
            content=self._giveaway_content(giveaway),
            embed=self._build_giveaway_embed(giveaway),
            view=None,
        )
        await self._add_entry_reaction(message, giveaway)
        self._schedule_end(giveaway)
        return giveaway_id

    async def _create_giveaways(self, channel, guild_id: int, creator_id: int, payload: GiveawayCreatePayload) -> list[int]:
        giveaway_ids = []
        for index in range(1, payload.quantity + 1):
            giveaway_ids.append(
                await self._create_one_giveaway(
                    channel=channel,
                    guild_id=guild_id,
                    creator_id=creator_id,
                    payload=payload,
                    quantity_index=index,
                )
            )
        return giveaway_ids

    @staticmethod
    def _giveaway_delay_seconds(giveaway: dict, now: float | None = None) -> float:
        return max(0.0, float(giveaway["ends_at"]) - float(now if now is not None else time.time()))

    def _schedule_end(self, giveaway: dict):
        giveaway_id = int(giveaway["giveaway_id"])
        existing = self._end_tasks.pop(giveaway_id, None)
        if existing:
            existing.cancel()

        async def runner():
            try:
                delay = self._giveaway_delay_seconds(giveaway)
                await asyncio.sleep(delay)
                await self._end_giveaway(giveaway_id, automatic=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"❌ Lỗi auto end giveaway {giveaway_id}: {exc}")

        self._end_tasks[giveaway_id] = self.bot.loop.create_task(runner())

    def _pick_winners(self, participants: list[dict], winners_count: int, exclude_ids: set[int] | None = None) -> list[int]:
        exclude_ids = exclude_ids or set()
        pool = [row for row in participants if int(row["user_id"]) not in exclude_ids]
        if not pool:
            pool = participants
        if not pool:
            return []
        selected = random.sample(pool, min(winners_count, len(pool)))
        return [int(row["user_id"]) for row in selected]

    async def _end_giveaway(self, giveaway_id: int, automatic: bool = False) -> tuple[bool, str]:
        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            return False, "Giveaway không tồn tại."
        if giveaway["status"] == "ending":
            return False, "Giveaway đang xử lý kết thúc."
        if giveaway["status"] == "ended":
            existing_winner_ids = self.service.decode_winner_ids(giveaway)
            if existing_winner_ids:
                return False, "Giveaway đã kết thúc."

            giveaway_message = await self._fetch_giveaway_message(giveaway)
            participants = await self._sync_reaction_participants(giveaway, giveaway_message)
            selected_winner_ids = self.service.decode_selected_winner_ids(giveaway)
            winner_ids = selected_winner_ids or self._pick_winners(
                participants,
                int(giveaway["winners_count"]),
            )
            if not winner_ids:
                return False, "Giveaway đã kết thúc và không tìm thấy người tham gia."

            self.service.update_winners(giveaway_id, winner_ids)
            updated = self.service.get_giveaway(giveaway_id)
            if giveaway_message:
                await giveaway_message.edit(
                    content=self._giveaway_content(updated, ended=True),
                    embed=self._build_giveaway_embed(updated, ended=True),
                    view=None,
                )
                await self._send_result_message(
                    giveaway_message.channel,
                    updated,
                    winner_ids,
                )
            await self._send_winner_dms(updated, winner_ids)
            return True, "Đã cập nhật người thắng cho giveaway đã kết thúc."

        giveaway_message = await self._fetch_giveaway_message(giveaway)
        participants = (
            self.service.get_participants(giveaway_id)
            if automatic
            else await self._sync_reaction_participants(giveaway, giveaway_message)
        )
        selected_winner_ids = self.service.decode_selected_winner_ids(giveaway)
        winner_ids = selected_winner_ids or self._pick_winners(participants, int(giveaway["winners_count"]))
        if not self.service.claim_ending(giveaway_id):
            return False, "Giveaway đang xử lý hoặc đã kết thúc."
        self.service.mark_ended(giveaway_id, winner_ids)
        updated = self.service.get_giveaway(giveaway_id)

        task = self._end_tasks.pop(giveaway_id, None)
        current_task = asyncio.current_task()
        if task and task is not current_task and not task.done():
            task.cancel()

        message = giveaway_message or await self._fetch_giveaway_message(updated)
        if message:
            await message.edit(
                content=self._giveaway_content(updated, ended=True),
                embed=self._build_giveaway_embed(updated, ended=True),
                view=None,
            )
            await self._send_result_message(message.channel, updated, winner_ids)
        await self._send_winner_dms(updated, winner_ids)
        return True, "Giveaway đã kết thúc." if automatic else "Đã end giveaway."

    async def _reroll_giveaway(self, giveaway_id: int) -> tuple[bool, str, list[int]]:
        giveaway = self.service.get_giveaway(giveaway_id)
        if not giveaway:
            return False, "Giveaway không tồn tại.", []
        if giveaway["status"] != "ended":
            return False, "Giveaway chưa kết thúc, không thể reroll.", []

        giveaway_message = await self._fetch_giveaway_message(giveaway)
        participants = await self._sync_reaction_participants(giveaway, giveaway_message)
        previous_winners = set(self.service.decode_winner_ids(giveaway))
        winner_ids = self._pick_winners(participants, int(giveaway["winners_count"]), exclude_ids=previous_winners)
        reroll_round = int(giveaway.get("reroll_count") or 0) + 1
        self.service.update_winners(giveaway_id, winner_ids, reroll_count=reroll_round)
        updated = self.service.get_giveaway(giveaway_id)

        message = giveaway_message or await self._fetch_giveaway_message(updated)
        if message:
            await message.edit(
                content=self._giveaway_content(updated, ended=True),
                embed=self._build_giveaway_embed(updated, ended=True),
                view=None,
            )
            await self._send_result_message(message.channel, updated, winner_ids, reroll=True, reroll_round=reroll_round)
        await self._send_winner_dms(updated, winner_ids, reroll=True, reroll_round=reroll_round)
        return True, f"Đã reroll giveaway lần {reroll_round}.", winner_ids

    @commands.command(name="giveaway", aliases=["ga"])
    async def giveaway(self, ctx, *, content: str = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Giveaway chỉ hoạt động trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "giveaway"):
            return

        content = (content or "").strip()
        first, _, rest = content.partition(" ")
        lowered = first.lower()
        if lowered in {"end", "stop", "gastop"}:
            await self._handle_end_command(ctx, rest.strip())
            return
        if lowered in {"reroll", "gareroll"}:
            await self._handle_reroll_command(ctx, rest.strip())
            return
        if lowered in {"config", "cfg", "emoji", "icon", "reaction"}:
            await self._handle_config_command(ctx, rest.strip(), lowered)
            return

        try:
            payload = self._parse_prefix_payload(content)
            giveaway_ids = await self._create_giveaways(ctx.channel, ctx.guild.id, ctx.author.id, payload)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", str(exc)))
            return
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Tạo Giveaway Thất Bại", str(exc)))
            return

        await self._delete_invocation_message(ctx)
        if payload.quantity > 1:
            await ctx.send(
                embed=create_info_splash(
                    f"{giveaway_icon('created')} Đã Tạo Giveaway",
                    f"Đã tạo `{len(giveaway_ids)}` giveaway.\nMuốn end/reroll/set thì chuột phải tin giveaway rồi chọn **Sao chép ID Tin Nhắn**.",
                )
            )

    async def _handle_end_command(self, ctx, giveaway_id_text: str):
        if not giveaway_id_text or not giveaway_id_text.strip().isdigit():
            await ctx.send(embed=create_error_splash("❌ Thiếu ID", "Dùng: `end <id giveaway>` hoặc `gastop <id giveaway>`."))
            return
        ok, message = await self._end_giveaway(int(giveaway_id_text.strip()))
        embed_factory = create_success_splash if ok else create_error_splash
        await ctx.send(embed=embed_factory(f"{giveaway_icon('result')} End Giveaway", message))

    async def _handle_reroll_command(self, ctx, giveaway_id_text: str):
        if not giveaway_id_text or not giveaway_id_text.strip().isdigit():
            await ctx.send(embed=create_error_splash("❌ Thiếu ID", "Dùng: `reroll <id giveaway>` hoặc `gareroll <id giveaway>`."))
            return
        ok, message, _ = await self._reroll_giveaway(int(giveaway_id_text.strip()))
        embed_factory = create_success_splash if ok else create_error_splash
        await ctx.send(embed=embed_factory(f"{giveaway_icon('reroll')} Reroll Giveaway", message))

    @staticmethod
    def _is_entry_emoji_key(raw_key: str) -> bool:
        return str(raw_key or "").strip().lower() in {"emoji", "icon", "reaction", "entry", "entry_emoji", "thamgia", "tham_gia"}

    def _build_config_help_embed(self, guild_id: int) -> discord.Embed:
        theme = self.service.get_theme(guild_id)
        return build_giveaway_config_embed(self.get_entry_emoji(guild_id), theme)

    async def handle_giveaway_config_submit(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        key: str,
        value: str,
    ):
        try:
            if key == "entry_emoji":
                if value.strip().lower() in {"reset", "default"}:
                    value = GIVEAWAY_DEFAULT_ENTRY_EMOJI
                ok, message = await self._set_entry_emoji_config(interaction.guild, value)
            else:
                ok, message = await self._set_theme_config(interaction.guild, key, value)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            message if ok else f"❌ {message}",
            ephemeral=True,
        )

    async def _set_entry_emoji_config(self, guild: discord.Guild, raw_emoji: str) -> tuple[bool, str]:
        if not str(raw_emoji or "").strip():
            return False, "Thiếu emoji. Dùng: `ga config emoji <emoji>`."
        normalized = await self.resolve_entry_emoji_input(guild, raw_emoji)
        self.service.set_entry_emoji(guild.id, normalized)
        return True, f"Giveaway mới sẽ dùng {normalized} để tham gia.\nCác giveaway đang chạy vẫn giữ emoji cũ."

    async def _set_theme_config(self, guild: discord.Guild, raw_key: str, raw_value: str) -> tuple[bool, str]:
        key = giveaway_theme_key(raw_key)
        if not key:
            return False, f"Key config `{raw_key}` không tồn tại. Dùng `ga config` để xem mẫu."
        raw_value = str(raw_value or "").strip()
        if not raw_value:
            current = giveaway_theme_value(self.service.get_theme(guild.id), key)
            return False, f"`{key}` hiện tại: {current}\nDùng: `ga config {raw_key} <giá trị>`."
        if raw_value.lower() in {"reset", "default", "macdinh", "mặcđịnh", "mac_dinh", "mặc_định"}:
            self.service.reset_theme_value(guild.id, key)
            return True, f"Đã reset `{key}` về mặc định: {GIVEAWAY_THEME_DEFAULTS.get(key, '')}"
        value = (
            await self.resolve_entry_emoji_input(guild, raw_value)
            if key.startswith("icon_")
            else raw_value.replace("\\n", "\n")
        )
        self.service.set_theme_value(guild.id, key, value)
        return True, f"`{key}` đã đổi thành: {value}"

    async def _handle_config_command(self, ctx, content: str, action: str = "config"):
        raw = (content or "").strip()
        if not raw:
            await ctx.send(
                embed=self._build_config_help_embed(ctx.guild.id),
                view=GiveawayConfigView(self, ctx.guild.id),
            )
            return

        first, _, rest = raw.partition(" ")
        try:
            if action in {"emoji", "reaction"}:
                ok, message = await self._set_entry_emoji_config(ctx.guild, raw)
            elif action == "icon" and first and rest:
                ok, message = await self._set_theme_config(ctx.guild, first, rest)
            elif action == "icon":
                ok, message = await self._set_entry_emoji_config(ctx.guild, raw)
            elif self._is_entry_emoji_key(first):
                ok, message = await self._set_entry_emoji_config(ctx.guild, rest)
            else:
                ok, message = await self._set_theme_config(ctx.guild, first, rest)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Emoji Không Hợp Lệ", str(exc)))
            return
        embed_factory = create_success_splash if ok else create_error_splash
        await ctx.send(embed=embed_factory(f"{giveaway_icon('config')} Giveaway Config", message))

    @commands.command(name="end")
    async def end(self, ctx, giveaway_id: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "giveaway"):
            return
        await self._handle_end_command(ctx, giveaway_id or "")

    @commands.command(name="gastop")
    async def gastop(self, ctx, giveaway_id: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "giveaway"):
            return
        await self._handle_end_command(ctx, giveaway_id or "")

    @commands.command(name="reroll")
    async def reroll(self, ctx, giveaway_id: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "giveaway"):
            return
        await self._handle_reroll_command(ctx, giveaway_id or "")

    @commands.command(name="gareroll")
    async def gareroll(self, ctx, giveaway_id: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "giveaway"):
            return
        await self._handle_reroll_command(ctx, giveaway_id or "")

    @app_commands.command(name="giveaway", description="Tạo, kết thúc, reroll hoặc cấu hình giveaway")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="create", value="create"),
            app_commands.Choice(name="set", value="set"),
            app_commands.Choice(name="end", value="end"),
            app_commands.Choice(name="reroll", value="reroll"),
            app_commands.Choice(name="config", value="config"),
        ]
    )
    @app_commands.describe(
        action="Chọn thao tác giveaway",
        reward="Nội dung/phần thưởng giveaway",
        duration="Thời gian: 10m, 1h, 1d",
        winners="Số lượng người thắng",
        quantity="Số lượng giveaway cần tạo",
        template="Template riêng nếu có",
        giveaway_id="ID giveaway/message ID khi set/end/reroll",
        emoji="Emoji tham gia khi action là config",
        config_key="Key config: emoji, title_start, title_ended, join_text, host_text...",
        config_value="Giá trị config mới; nhập reset để về mặc định",
    )
    async def slash_giveaway(
        self,
        interaction: discord.Interaction,
        action: str,
        reward: str = "",
        duration: str = "",
        winners: int = 1,
        quantity: int = 1,
        template: str = "",
        giveaway_id: str = "",
        emoji: str = "",
        config_key: str = "",
        config_value: str = "",
    ):
        action = (action or "").strip().lower()
        if action == "config":
            if interaction.guild is None:
                await self._send_interaction_splash(
                    interaction,
                    create_error_splash("❌ Chỉ Dùng Trong Server", "Config emoji giveaway chỉ dùng trong server."),
                )
                return
            if not await self.require_role_or_admin_interaction(interaction, "giveaway"):
                return
            raw_key = str(config_key or "").strip()
            raw_value = str(config_value or "").strip() or str(emoji or "").strip()
            if not raw_key and not raw_value:
                await self._send_interaction_splash(
                    interaction,
                    self._build_config_help_embed(interaction.guild.id),
                    view=GiveawayConfigView(self, interaction.guild.id),
                )
                return
            try:
                if not raw_key or self._is_entry_emoji_key(raw_key):
                    ok, message = await self._set_entry_emoji_config(interaction.guild, raw_value)
                else:
                    ok, message = await self._set_theme_config(interaction.guild, raw_key, raw_value)
            except ValueError as exc:
                await self._send_interaction_splash(
                    interaction,
                    create_error_splash("❌ Emoji Không Hợp Lệ", str(exc)),
                )
                return
            embed_factory = create_success_splash if ok else create_error_splash
            await self._send_interaction_splash(
                interaction,
                embed_factory(f"{giveaway_icon('config')} Giveaway Config", message),
            )
            return
        if action in {"set", "end", "reroll"}:
            if not str(giveaway_id).strip().isdigit():
                await self._send_interaction_splash(
                    interaction,
                    create_error_splash("❌ ID Không Hợp Lệ", "ID giveaway phải là số."),
                )
                return
            parsed_id = int(str(giveaway_id).strip())
            if action == "set":
                await self._show_manual_set_panel(interaction, parsed_id)
                return
            if interaction.guild is None:
                await self._send_interaction_splash(
                    interaction,
                    create_error_splash("❌ Chỉ Dùng Trong Server", "End/reroll giveaway bằng slash chỉ dùng trong server."),
                )
                return
            if not await self.require_role_or_admin_interaction(interaction, "giveaway"):
                return
            if action == "end":
                ok, message = await self._end_giveaway(parsed_id)
                embed_factory = create_success_splash if ok else create_error_splash
                await self._send_interaction_splash(interaction, embed_factory(f"{giveaway_icon('result')} End Giveaway", message))
                return
            ok, message, _ = await self._reroll_giveaway(parsed_id)
            embed_factory = create_success_splash if ok else create_error_splash
            await self._send_interaction_splash(interaction, embed_factory(f"{giveaway_icon('reroll')} Reroll Giveaway", message))
            return

        if interaction.guild is None or interaction.channel is None:
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Chỉ Dùng Trong Server", "Giveaway chỉ hoạt động trong server."),
            )
            return
        if not await self.require_role_or_admin_interaction(interaction, "giveaway"):
            return

        duration_seconds = parse_duration(duration) if self._is_duration_token(duration) else None
        if not duration_seconds:
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Thời Gian Không Hợp Lệ", "Ví dụ hợp lệ: `10m`, `1h`, `1d`."),
            )
            return

        try:
            payload = self._validate_payload(
                GiveawayCreatePayload(
                    reward=reward,
                    duration_seconds=int(duration_seconds),
                    winners_count=int(winners),
                    quantity=int(quantity),
                    template=template or "",
                )
            )
        except ValueError as exc:
            await self._send_interaction_splash(
                interaction,
                create_error_splash("❌ Sai Dữ Liệu Giveaway", str(exc)),
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            giveaway_ids = await self._create_giveaways(interaction.channel, interaction.guild.id, interaction.user.id, payload)
        except Exception as exc:
            await interaction.followup.send(
                embed=create_error_splash("❌ Tạo Giveaway Thất Bại", str(exc)),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=create_success_splash(
                "✅ Đã Tạo Giveaway",
                f"Đã tạo `{len(giveaway_ids)}` giveaway.\nMuốn end/reroll/set thì chuột phải tin giveaway rồi chọn **Sao chép ID Tin Nhắn**.",
            ),
                ephemeral=True,
            )


async def setup(bot):
    cog = AdministratorGiveawayCog(bot)
    await bot.add_cog(cog)
    if bot.is_ready():
        await cog.restore_active_giveaways()
