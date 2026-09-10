from __future__ import annotations

import discord
from discord.ext import commands


class ImagePagesView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], requester_id: int):
        super().__init__(timeout=180)
        self.pages = pages
        self.requester_id = requester_id
        self.page = 0
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Menu này không phải của bạn.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        last_index = len(self.pages) - 1
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= last_index

    @discord.ui.button(label="Lùi", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="Tiếp", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(len(self.pages) - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)


class AvatarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_user(self, ctx: commands.Context, raw_target: str | None) -> tuple[discord.User, discord.Member | None]:
        if not raw_target:
            member = ctx.author if isinstance(ctx.author, discord.Member) else None
            user = await self.bot.fetch_user(ctx.author.id)
            return user, member

        target = raw_target.strip()
        member = None
        if ctx.guild is not None:
            try:
                member = await commands.MemberConverter().convert(ctx, target)
            except commands.BadArgument:
                member = None
        if member is not None:
            user = await self.bot.fetch_user(member.id)
            return user, member

        try:
            user = await commands.UserConverter().convert(ctx, target)
            return await self.bot.fetch_user(user.id), None
        except commands.BadArgument:
            pass

        cleaned_id = target.strip("<@!>")
        if cleaned_id.isdigit():
            return await self.bot.fetch_user(int(cleaned_id)), None

        raise commands.UserNotFound(target)

    @staticmethod
    def _image_embed(
        title: str,
        target_name: str,
        image_url: str,
        color: discord.Color,
        author_icon_url: str | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(title=title, color=color)
        if author_icon_url:
            embed.set_author(name=target_name, icon_url=author_icon_url)
        else:
            embed.set_author(name=target_name)
        embed.set_image(url=image_url)
        embed.add_field(name="Link", value=f"[Mở ảnh gốc]({image_url})", inline=False)
        return embed

    async def _get_mutual_members(self, user_id: int) -> list[discord.Member]:
        members: list[discord.Member] = []
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None
            if member is not None:
                members.append(member)
        return members

    @commands.command(name="avatar", aliases=["av", "ava", "avata"])
    async def avatar(self, ctx: commands.Context, *, target: str = None):
        try:
            user, member = await self._resolve_user(ctx, target)
        except (commands.UserNotFound, discord.NotFound):
            await ctx.send("❌ Không tìm thấy user.")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"❌ Không lấy được ảnh user: {exc}")
            return

        display_asset = member.display_avatar if member else user.display_avatar
        global_asset = user.avatar or user.default_avatar
        target_name = member.display_name if member else str(user.id)
        author_icon_url = display_asset.with_size(128).url
        pages = [
            self._image_embed(
                "Server Avatar" if member else "Avatar",
                target_name,
                display_asset.with_size(1024).url,
                discord.Color.from_rgb(120, 170, 255),
                author_icon_url,
            )
        ]

        if member and member.guild_avatar and member.guild_avatar.key != getattr(global_asset, "key", None):
            pages.append(
                self._image_embed(
                    "Avatar",
                    str(user.id),
                    global_asset.with_size(1024).url,
                    discord.Color.from_rgb(120, 170, 255),
                    global_asset.with_size(128).url,
                )
            )

        view = ImagePagesView(pages, ctx.author.id)
        if len(pages) <= 1:
            view.clear_items()
        await ctx.send(embed=pages[0], view=view)

    @commands.command(name="banner", aliases=["bn", "bia", "bìa"])
    async def banner(self, ctx: commands.Context, *, target: str = None):
        try:
            user, member = await self._resolve_user(ctx, target)
        except (commands.UserNotFound, discord.NotFound):
            await ctx.send("❌ Không tìm thấy user.")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"❌ Không lấy được banner: {exc}")
            return

        pages: list[discord.Embed] = []
        target_name = member.display_name if member else user.name
        author_icon_url = (member.display_avatar if member else user.display_avatar).with_size(128).url
        seen_urls: set[str] = set()

        if user.banner:
            image_url = user.banner.with_size(1024).url
            seen_urls.add(image_url)
            pages.append(
                self._image_embed(
                    "User Banner",
                    target_name,
                    image_url,
                    discord.Color.from_rgb(255, 136, 190),
                    author_icon_url,
                )
            )

        for mutual_member in await self._get_mutual_members(user.id):
            guild_banner = getattr(mutual_member, "guild_banner", None)
            if guild_banner is None:
                continue

            image_url = guild_banner.with_size(1024).url
            if image_url in seen_urls:
                continue
            seen_urls.add(image_url)

            embed = self._image_embed(
                "Server Banner",
                mutual_member.display_name or target_name,
                image_url,
                discord.Color.from_rgb(255, 136, 190),
                mutual_member.display_avatar.with_size(128).url,
            )
            embed.add_field(name="Server", value=mutual_member.guild.name, inline=False)
            pages.append(embed)

        if not pages:
            await ctx.send("❌ User này không có banner/server banner nào bot có thể đọc.")
            return

        for index, embed in enumerate(pages, 1):
            embed.set_footer(text=f"Banner {index}/{len(pages)}")

        view = ImagePagesView(pages, ctx.author.id)
        if len(pages) <= 1:
            view.clear_items()
        await ctx.send(embed=pages[0], view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(AvatarCog(bot))
