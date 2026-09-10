from utils import CogDatabase


def get_single_configured_guild_id() -> int | None:
    """Trả về guild duy nhất đã cấu hình; không đoán khi DB có 0 hoặc nhiều guild."""
    db = CogDatabase("guild_settings")
    try:
        tables = {
            row["name"]
            for row in db.fetch("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        guild_ids = set()
        if "guild_settings" in tables:
            guild_ids.update(int(row["guild_id"]) for row in db.fetch("SELECT guild_id FROM guild_settings"))
        if "guild_system_roles" in tables:
            guild_ids.update(int(row["guild_id"]) for row in db.fetch("SELECT DISTINCT guild_id FROM guild_system_roles"))
        return next(iter(guild_ids)) if len(guild_ids) == 1 else None
    finally:
        db.close()
