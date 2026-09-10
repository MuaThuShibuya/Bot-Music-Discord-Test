import os

from config import COGS_DIR


def module_name_from_path(file_path: str) -> str:
    rel_path = os.path.relpath(file_path, COGS_DIR)
    return rel_path[:-3].replace(os.sep, ".")


def iter_cog_modules(base_dir: str | None = None) -> list[str]:
    base_dir = base_dir or COGS_DIR
    modules = []
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        files.sort()
        for filename in files:
            if filename.endswith("_cog.py"):
                modules.append(module_name_from_path(os.path.join(root, filename)))
    return modules


def resolve_cog_modules(target: str | None = None) -> list[str]:
    if not target:
        return iter_cog_modules()

    normalized = target.strip().removesuffix(".py").replace("/", ".").replace("\\", ".")
    if normalized.lower() in {"admin", "mod", "moderator", "operator"}:
        normalized = "administrator"

    folder_path = os.path.join(COGS_DIR, *normalized.split("."))
    file_path = folder_path + ".py"

    if os.path.isdir(folder_path):
        return iter_cog_modules(folder_path)
    if os.path.isfile(file_path):
        return [normalized]

    short_name = normalized.rsplit(".", 1)[-1].removesuffix("_cog").lower()
    matches = [
        module_name
        for module_name in iter_cog_modules()
        if module_name.rsplit(".", 1)[-1].removesuffix("_cog").lower() == short_name
    ]
    if matches:
        return matches
    return [normalized]
