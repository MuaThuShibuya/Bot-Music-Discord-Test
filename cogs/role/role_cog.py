import discord
from discord.ext import commands

from cogs.role_command_utils import RoleCommandBase
from services.booking_service import BookingService
from services.role_permission_service import normalize_permission_key
from utils import create_error_splash, create_success_splash, create_warning_splash


SYSTEM_ROLE_OPTIONS = {
    "admin": {
        "label": "Admin",
        "emoji": "🛡️",
        "description": "Role quản trị bot/server",
    },
    "booking": {
        "label": "Booking",
        "emoji": "📘",
        "description": "Role booking dùng cho lương/booking",
    },
    "user": {
        "label": "User",
        "emoji": "👤",
        "description": "Role người dùng cơ bản",
    },
    "staff": {
        "label": "Staff",
        "emoji": "🧑‍💼",
        "description": "Role staff/hỗ trợ vận hành",
    },
}

ROLE_PERMISSION_COMMANDS = {
    "role",
    "addrole",
    "addadmin",
    "addcashadmin",
    "removerole",
    "rmadmin",
    "rmcashadmin",
    "setrole",
    "perms",
    "myroles",
    "rolescommands",
}

COMMAND_PATH_ALIASES = {
    "level": {
        "setup": "setup",
        "config": "setup",
        "setting": "setup",
        "settings": "setup",
        "role": "role",
        "roles": "role",
        "reward": "role",
        "rewards": "role",
        "all": "all",
        "top": "all",
        "leaderboard": "all",
        "lb": "all",
        "count": "count",
        "c": "count",
        "totalcount": "count",
        "set": "set",
        "a": "edit",
        "add": "edit",
        "d": "edit",
        "r": "edit",
        "rm": "edit",
        "remove": "edit",
        "e": "edit",
        "edit": "edit",
    },
    "note": {
        "public": "public",
        "pb": "public",
        "private": "private",
        "prv": "private",
    },
}


class SystemRoleSelect(discord.ui.Select):
    def __init__(self, cog: "RoleCog", role: discord.Role, author_id: int):
        self.cog = cog
        self.role = role
        self.author_id = author_id
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                description=data["description"],
                emoji=data["emoji"],
            )
            for key, data in SYSTEM_ROLE_OPTIONS.items()
        ]
        super().__init__(
            placeholder="Chọn loại vai trò cho role này...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"setrole:{role.id}:{author_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Chỉ người gọi `setrole` mới được chọn menu này.", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message("❌ Menu này chỉ dùng trong server.", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role.id)
        if role is None:
            await interaction.response.send_message("❌ Role này không còn tồn tại trong server.", ephemeral=True)
            return

        await self.cog._save_system_role_interaction(interaction, role, self.values[0])


class SystemRoleSelectView(discord.ui.View):
    def __init__(self, cog: "RoleCog", role: discord.Role, author_id: int):
        super().__init__(timeout=120)
        self.add_item(SystemRoleSelect(cog, role, author_id))


class RoleCog(RoleCommandBase):
    async def _get_members_with_role(self, guild: discord.Guild, role: discord.Role) -> tuple[list[discord.Member], bool]:
        cached_members = [member for member in role.members if not member.bot]
        if cached_members:
            return cached_members, True

        fetched_members: list[discord.Member] = []
        try:
            async for member in guild.fetch_members(limit=None):
                if not member.bot and any(member_role.id == role.id for member_role in member.roles):
                    fetched_members.append(member)
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            return [], False

        return fetched_members, True

    async def _sync_booking_members_for_role(self, guild: discord.Guild, role: discord.Role) -> tuple[int, bool]:
        members, attempted = await self._get_members_with_role(guild, role)
        if not members:
            return 0, attempted

        booking_service = BookingService(guild.id)
        created_count = 0
        for member in members:
            existed = booking_service.get_booking(member.id) is not None
            booking_service.get_or_create_booking(member.id, member.display_name)
            if not existed:
                created_count += 1
        return created_count, attempted

    def _is_booking_system_role(self, guild_id: int, role_id: int) -> bool:
        system_role = self.guild_settings.get_system_role(guild_id, "booking")
        return bool(system_role and int(system_role["role_id"]) == int(role_id))

    async def _sync_member_if_booking_role(self, member: discord.Member, role: discord.Role) -> bool:
        if member.bot or not self._is_booking_system_role(member.guild.id, role.id):
            return False
        BookingService(member.guild.id).get_or_create_booking(member.id, member.display_name)
        return True

    async def _resolve_role(self, ctx, raw_role: str | None) -> discord.Role | None:
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh role chỉ hoạt động trong server."))
            return None
        if not raw_role:
            await ctx.send(embed=create_error_splash("❌ Thiếu Role", "Hãy nhập role mention, tên role hoặc role ID."))
            return None
        try:
            return await commands.RoleConverter().convert(ctx, raw_role)
        except Exception:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Role", "Hãy nhập role mention, tên role hoặc role ID hợp lệ."))
            return None

    async def _probe_role(self, ctx, raw_role: str | None) -> discord.Role | None:
        if ctx.guild is None or not raw_role:
            return None
        try:
            return await commands.RoleConverter().convert(ctx, raw_role)
        except Exception:
            return None

    def _resolve_command_name(self, raw_command_name: str | None) -> str | None:
        if raw_command_name is None:
            return None
        command_name = normalize_permission_key(raw_command_name)
        if not command_name:
            return None

        parts = command_name.split()
        root_raw = parts[0]
        command = self.bot.get_command(root_raw)
        if not command:
            return None
        resolved_name = command.name.lower()
        if resolved_name in ROLE_PERMISSION_COMMANDS:
            return "role"
        if len(parts) > 1:
            subcommand = parts[1].lower()
            mapped_subcommand = COMMAND_PATH_ALIASES.get(resolved_name, {}).get(subcommand)
            if not mapped_subcommand:
                return None
            return f"{resolved_name} {mapped_subcommand}"
        return resolved_name

    @staticmethod
    def _split_role_targets(raw_roles: str) -> list[str]:
        return [part.strip() for part in raw_roles.split(",") if part.strip()]

    @staticmethod
    def _split_command_targets(raw_commands: str) -> list[str]:
        return [part.strip() for part in raw_commands.split(",") if part.strip()]

    async def _resolve_role_targets(self, ctx, raw_roles: str) -> list[discord.Role] | None:
        role_targets = self._split_role_targets(raw_roles)
        if not role_targets:
            await ctx.send(embed=create_error_splash("❌ Thiếu Role", "Hãy nhập ít nhất 1 role mention, tên role hoặc role ID."))
            return None

        resolved_roles: list[discord.Role] = []
        seen_role_ids: set[int] = set()
        for raw_role in role_targets:
            role = await self._resolve_role(ctx, raw_role)
            if not role:
                return None
            if role.id not in seen_role_ids:
                resolved_roles.append(role)
                seen_role_ids.add(role.id)

        return resolved_roles

    @staticmethod
    def _build_role_mentions(roles: list[discord.Role]) -> str:
        return ", ".join(role.mention for role in roles)

    async def _parse_permission_payload(self, ctx, content: str, command_label: str) -> tuple[list[discord.Role], list[str], list[str], str | None]:
        content = (content or "").strip()
        if not content:
            return [], [], [], f"Dùng: `{command_label} @role1, @role2 command1, command2` hoặc `{command_label} @role command`."

        tokens = content.split()
        if len(tokens) < 2:
            return [], [], [], f"Dùng: `{command_label} @role1, @role2 command1, command2` hoặc `{command_label} @role command`."

        candidates: list[tuple[str, str]] = []
        for split_index in range(len(tokens) - 1, 0, -1):
            roles_text = " ".join(tokens[:split_index]).strip()
            commands_text = " ".join(tokens[split_index:]).strip()
            if roles_text and commands_text:
                candidates.append((roles_text, commands_text))

        first_invalid_commands: list[str] | None = None
        for roles_text, commands_text in candidates:
            role_targets = self._split_role_targets(roles_text)
            command_targets = self._split_command_targets(commands_text)
            if not role_targets or not command_targets:
                continue

            command_names: list[str] = []
            invalid_commands: list[str] = []
            for raw_command_name in command_targets:
                command_name = self._resolve_command_name(raw_command_name)
                if not command_name:
                    invalid_commands.append(raw_command_name)
                elif command_name not in command_names:
                    command_names.append(command_name)

            resolved_roles: list[discord.Role] = []
            seen_role_ids: set[int] = set()
            role_invalid = False
            for raw_role in role_targets:
                role = await self._probe_role(ctx, raw_role)
                if not role:
                    role_invalid = True
                    break
                if role.id not in seen_role_ids:
                    resolved_roles.append(role)
                    seen_role_ids.add(role.id)

            if not role_invalid and (command_names or invalid_commands):
                return resolved_roles, command_names, invalid_commands, None

            if not role_invalid and invalid_commands and first_invalid_commands is None:
                first_invalid_commands = invalid_commands

        if first_invalid_commands:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in first_invalid_commands)
            return [], [], first_invalid_commands, f"{invalid_text} không tồn tại hoặc chưa được load trong bot/cog."

        return [], [], [], f"Dùng: `{command_label} @role1, @role2 command1, command2` hoặc `{command_label} @role command`."

    @commands.command(name="addrole", aliases=["themrole"])
    async def add_role(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        roles, command_names, invalid_commands, error_text = await self._parse_permission_payload(ctx, content, "addrole")
        if error_text:
            if "không tồn tại" in error_text and not command_names:
                await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", error_text))
            else:
                await ctx.send(embed=create_error_splash("❌ Thiếu Thông Tin", error_text))
            return
        if not command_names:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in invalid_commands)
            await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", f"{invalid_text} không tồn tại hoặc chưa được load trong bot/cog."))
            return
        if "cash" in command_names and not self.admins.is_hard_admin(ctx.author.id):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin trong env mới được cấp role quyền `cash`."))
            return

        failed_roles: list[str] = []
        failed_commands: list[str] = []
        success_count = 0
        failure_count = 0
        for role in roles:
            role_saved = self.service.save_role(ctx.guild.id, role.id, role.name, role.position)
            if not role_saved:
                failed_roles.append(role.mention)
                failure_count += len(command_names)
                continue

            for command_name in command_names:
                permission_saved = self.service.add_command_role(ctx.guild.id, role.id, command_name, ctx.author.id, role.name)
                if not permission_saved:
                    failed_roles.append(f"{role.mention} → `{command_name}`")
                    failed_commands.append(command_name)
                    failure_count += 1
                else:
                    success_count += 1

        if success_count == 0 and failure_count > 0:
            await ctx.send(embed=create_error_splash("❌ Thêm Quyền Thất Bại", "Database chưa lưu được quyền role. Hãy thử lại hoặc kiểm tra log."))
            return

        role_mentions = self._build_role_mentions(roles)
        command_mentions = ", ".join(f"`{cmd}`" for cmd in command_names)
        success_message = f"Role {role_mentions} được dùng các lệnh {command_mentions}"
        invalid_line = ""
        if invalid_commands:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in dict.fromkeys(invalid_commands))
            invalid_line = f"\nLệnh không tồn tại: {invalid_text}"

        if failed_roles or invalid_line:
            failed_text = ", ".join(dict.fromkeys(failed_roles))
            failed_command_text = ", ".join(f"`{cmd}`" for cmd in dict.fromkeys(failed_commands))
            extra_line = f"\nKhông lưu được cho: {failed_text}" if failed_text else ""
            if failed_command_text:
                extra_line += f"\nCommand lỗi: {failed_command_text}"
            extra_line += invalid_line
            await ctx.send(embed=create_warning_splash("⚠️ Thêm Quyền Một Phần Thành Công", f"{success_message}.{extra_line}"))
            return

        await ctx.send(embed=create_success_splash("✅ Thêm Quyền Thành Công", success_message))

    @commands.command(name="removerole", aliases=["rmrole", "xoarole"])
    async def remove_role(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        roles, command_names, invalid_commands, error_text = await self._parse_permission_payload(ctx, content, "removerole")
        if error_text:
            if "không tồn tại" in error_text and not command_names:
                await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", error_text))
            else:
                await ctx.send(embed=create_error_splash("❌ Thiếu Thông Tin", error_text))
            return
        if not command_names:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in invalid_commands)
            await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", f"{invalid_text} không tồn tại hoặc chưa được load trong bot/cog."))
            return
        if "cash" in command_names and not self.admins.is_hard_admin(ctx.author.id):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin trong env mới được xoá role quyền `cash`."))
            return

        for role in roles:
            for command_name in command_names:
                self.service.remove_command_role(ctx.guild.id, role.id, command_name)

        command_mentions = ", ".join(f"`{cmd}`" for cmd in command_names)
        description = f"Role {self._build_role_mentions(roles)} không được dùng các lệnh {command_mentions} nữa"
        if invalid_commands:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in dict.fromkeys(invalid_commands))
            description += f"\nLệnh không tồn tại: {invalid_text}"
            await ctx.send(embed=create_warning_splash("⚠️ Xóa Quyền Một Phần Thành Công", description))
            return
        await ctx.send(embed=create_success_splash("✅ Xóa Quyền Thành Công", description))

    @commands.command(name="setrole")
    async def set_role(self, ctx, raw_role: str = None, role_key: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        role = await self._resolve_role(ctx, raw_role)
        if not role:
            return
        if not role_key:
            embed = discord.Embed(
                title="⚙️ Chọn Vai Trò Hệ Thống",
                description=(
                    f"Role đang chọn: {role.mention}\n"
                    "Chọn loại vai trò bên dưới: `admin`, `booking`, `user`, `staff`."
                ),
                color=discord.Color.blurple(),
            )
            await ctx.send(embed=embed, view=SystemRoleSelectView(self, role, ctx.author.id))
            return

        if role_key.strip().lower() not in SYSTEM_ROLE_OPTIONS:
            valid_keys = ", ".join(f"`{key}`" for key in SYSTEM_ROLE_OPTIONS)
            await ctx.send(embed=create_error_splash("❌ Key Không Hợp Lệ", f"Chọn một trong các key: {valid_keys}.\nHoặc chỉ dùng `setrole @role` để mở menu chọn."))
            return

        await self._save_system_role_ctx(ctx, role, role_key)

    async def _save_system_role_ctx(self, ctx, role: discord.Role, role_key: str):
        try:
            normalized_key = self.guild_settings.normalize_role_key(role_key)
            saved = self.guild_settings.set_system_role(ctx.guild.id, normalized_key, role.id, role.name, ctx.author.id)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Set Role Thất Bại", str(exc)))
            return

        role_saved = self.service.save_role(ctx.guild.id, role.id, role.name, role.position)
        if not saved or not role_saved:
            await ctx.send(embed=create_error_splash("❌ Set Role Thất Bại", "Database chưa lưu được role hệ thống. Hãy thử lại hoặc kiểm tra log."))
            return

        sync_text = ""
        if normalized_key == "booking":
            created_count, attempted = await self._sync_booking_members_for_role(ctx.guild, role)
            if created_count:
                sync_text = f"\nĐã sync `{created_count}` user vào `booking.db`."
            elif not attempted:
                sync_text = "\nChưa sync được member đang có role này vì bot chưa nhận được danh sách member từ Discord."
        await ctx.send(embed=create_success_splash("✅ Set Role Thành Công", f"Đã set role {role.mention} làm `{normalized_key}`.{sync_text}"))

    async def _save_system_role_interaction(self, interaction: discord.Interaction, role: discord.Role, role_key: str):
        try:
            normalized_key = self.guild_settings.normalize_role_key(role_key)
            saved = self.guild_settings.set_system_role(interaction.guild.id, normalized_key, role.id, role.name, interaction.user.id)
        except ValueError as exc:
            await interaction.response.send_message(embed=create_error_splash("❌ Set Role Thất Bại", str(exc)), ephemeral=True)
            return

        role_saved = self.service.save_role(interaction.guild.id, role.id, role.name, role.position)
        if not saved or not role_saved:
            await interaction.response.send_message(embed=create_error_splash("❌ Set Role Thất Bại", "Database chưa lưu được role hệ thống. Hãy thử lại hoặc kiểm tra log."), ephemeral=True)
            return

        sync_text = ""
        if normalized_key == "booking":
            created_count, attempted = await self._sync_booking_members_for_role(interaction.guild, role)
            if created_count:
                sync_text = f"\nĐã sync `{created_count}` user vào `booking.db`."
            elif not attempted:
                sync_text = "\nChưa sync được member đang có role này vì bot chưa nhận được danh sách member từ Discord."
        embed = create_success_splash("✅ Set Role Thành Công", f"Đã set role {role.mention} làm `{normalized_key}`.{sync_text}")
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=embed, view=None)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_role_ids = {role.id for role in before.roles}
        for role in after.roles:
            if role.id not in before_role_ids:
                await self._sync_member_if_booking_role(after, role)

    @commands.command(name="perms")
    async def show_permissions(self, ctx, *, command_names: str = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh perms chỉ hoạt động trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        if not command_names or not command_names.strip():
            await ctx.send(embed=create_error_splash("❌ Lỗi", "Vui lòng nhập tên command! Ví dụ: `perms ban, mute`"))
            return

        valid_commands: list[str] = []
        invalid_commands: list[str] = []
        for raw_command_name in self._split_command_targets(command_names):
            command_name = self._resolve_command_name(raw_command_name)
            if not command_name:
                invalid_commands.append(raw_command_name)
            elif command_name not in valid_commands:
                valid_commands.append(command_name)

        if not valid_commands:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in invalid_commands)
            await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", f"{invalid_text} không tồn tại hoặc chưa được load trong bot/cog."))
            return

        embed = discord.Embed(title="📋 Quyền Command", color=discord.Color.blue())
        for command_name in valid_commands:
            roles = self.service.get_roles_for_command(ctx.guild.id, command_name)
            if roles:
                role_list = "\n".join([f"• {r['role_name']}" for r in roles])
                value = f"{role_list}\nTổng số: `{len(roles)}` role(s)"
            else:
                value = "❌ Chưa có role nào được phép dùng lệnh này"
            embed.add_field(name=command_name, value=value, inline=False)
        if invalid_commands:
            invalid_text = ", ".join(f"`{cmd}`" for cmd in invalid_commands)
            embed.add_field(name="Lệnh không tồn tại", value=invalid_text, inline=False)
        embed.set_footer(text=f"Server: {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(name="myroles")
    async def my_roles(self, ctx, member: discord.Member = None):
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        if not member:
            member = ctx.author
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if not roles:
            embed = discord.Embed(title=f"👤 Roles của {member.name}", description="❌ Không có role nào", color=discord.Color.orange())
        else:
            embed = discord.Embed(title=f"👤 Roles của {member.name}", description="\n".join(roles), color=discord.Color.blue())
            embed.add_field(name="Tổng số", value=f"{len(roles)} role(s)", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Server: {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command(name="rolescommands")
    async def roles_commands(self, ctx, raw_role: str = None):
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return
        role = await self._resolve_role(ctx, raw_role)
        if not role:
            return
        self.service.save_role(ctx.guild.id, role.id, role.name, role.position)
        commands_list = self.service.get_commands_for_role(ctx.guild.id, role.id)
        if commands_list:
            command_text = "\n".join([f"• `{cmd}`" for cmd in commands_list])
            embed = discord.Embed(title=f"📋 Commands của role {role.name}", description=command_text, color=discord.Color.blue())
            embed.add_field(name="Tổng số", value=f"{len(commands_list)} command(s)", inline=False)
        else:
            embed = discord.Embed(title=f"📋 Commands của role {role.name}", description="❌ Role này không có quyền dùng command nào", color=discord.Color.orange())
        embed.set_footer(text=f"Server: {ctx.guild.name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RoleCog(bot))
