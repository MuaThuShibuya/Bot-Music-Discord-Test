import asyncio
import unittest
from unittest.mock import AsyncMock

from cogs.administrator.giveaway_cog import AdministratorGiveawayCog


class GiveawayDisplayTest(unittest.TestCase):
    def test_custom_label_markdown_is_removed_before_default_bold(self):
        self.assertEqual(
            AdministratorGiveawayCog._clean_theme_label("**Tổ chức bởi:**"),
            "Tổ chức bởi",
        )
        self.assertEqual(
            AdministratorGiveawayCog._clean_theme_label("Người thắng:"),
            "Người thắng",
        )

    def test_end_delay_uses_absolute_timestamp(self):
        giveaway = {"ends_at": 103.0}

        self.assertEqual(
            AdministratorGiveawayCog._giveaway_delay_seconds(giveaway, now=100.5),
            2.5,
        )
        self.assertEqual(
            AdministratorGiveawayCog._giveaway_delay_seconds(giveaway, now=105),
            0.0,
        )


class GiveawayEndRaceTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_end_only_pays_once(self):
        class FakeGiveawayService:
            def __init__(self):
                self.claimed = False
                self.marked = 0
                self.giveaway = {
                    "giveaway_id": 123,
                    "guild_id": 777,
                    "channel_id": 888,
                    "message_id": 999,
                    "creator_id": 111,
                    "reward": "10k",
                    "duration_seconds": 10,
                    "winners_count": 1,
                    "quantity_total": 1,
                    "quantity_index": 1,
                    "template": "",
                    "status": "active",
                    "ends_at": 100,
                    "winner_ids": "[]",
                    "selected_winner_ids": "[]",
                    "entry_emoji": "🎉",
                }

            def get_giveaway(self, giveaway_id):
                return dict(self.giveaway)

            def decode_winner_ids(self, giveaway):
                return []

            def decode_selected_winner_ids(self, giveaway):
                return []

            def get_participants(self, giveaway_id):
                return [{"user_id": 42, "username": "Winner"}]

            def claim_ending(self, giveaway_id):
                if self.claimed:
                    return False
                self.claimed = True
                self.giveaway["status"] = "ending"
                return True

            def mark_ended(self, giveaway_id, winner_ids):
                self.marked += 1
                self.giveaway["status"] = "ended"
                self.giveaway["winner_ids"] = "[42]"

        cog = AdministratorGiveawayCog.__new__(AdministratorGiveawayCog)
        cog.service = FakeGiveawayService()
        cog._end_tasks = {}
        fetch_started = asyncio.Event()
        release_fetch = asyncio.Event()
        fetch_count = 0

        async def fetch_message(giveaway):
            nonlocal fetch_count
            fetch_count += 1
            if fetch_count >= 2:
                fetch_started.set()
            await release_fetch.wait()
            return None

        cog._fetch_giveaway_message = fetch_message
        cog._sync_reaction_participants = AsyncMock(return_value=[{"user_id": 42, "username": "Winner"}])
        cog._send_winner_dms = AsyncMock()

        first = asyncio.create_task(cog._end_giveaway(123, automatic=True))
        second = asyncio.create_task(cog._end_giveaway(123, automatic=True))
        await fetch_started.wait()
        release_fetch.set()
        results = await asyncio.gather(first, second)

        self.assertEqual(sum(1 for ok, _ in results if ok), 1)
        self.assertEqual(cog.service.marked, 1)
        cog._send_winner_dms.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
