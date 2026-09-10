# Discord Music Bot

This repository has been narrowed to the music playback runtime only. The legacy bot-wide economy and management features remain in the original codebase, but the independent music deployment uses the dedicated entrypoint in `music_bot.py` and loads only the voice/music cog.

## What is included

- Discord music bot client
- voice join / leave handling
- queue management
- autoplay and loop state
- playback controls such as play, skip, pause, resume, stop, volume, and now-playing
- yt-dlp integration for search and stream resolution
- FFmpeg audio playback via `discord.FFmpegPCMAudio`
- minimal runtime configuration required for a music-only deployment

## What is excluded

- economy / cash / bank / donate / profile / user business logic
- admin management or role management unrelated to the music runtime
- legacy SQLite database setup that was only needed by non-music features
- startup loading of the full bot-wide cog set

## Local run

```bash
python -m pip install -r requirements.txt
python music_bot.py
```

## Environment

Create a `.env` file with only the variables this music bot actually uses:

```env
DISCORD_TOKEN=your_discord_bot_token
BOT_PREFIX=b
APP_NAME=Discord Music Bot
SUPPORT_SERVER_URL=https://discord.com
```

The repository also provides a minimal example in `.env.example`.

## Render deployment

Use the included `render.yaml` and start command:

```bash
python music_bot.py
```

The Blueprint uses a Free Web Service for testing. The bot starts a small HTTP health server on `0.0.0.0:$PORT` because Render Web Services require an open port. Render must provide FFmpeg in the environment; the build command installs it before starting the app.

After deployment, configure a free uptime monitor such as UptimeRobot or cron-job.org to request the Render URL every 5-10 minutes. This can wake a sleeping Free Web Service, but it does not guarantee continuous Discord voice playback: Render can still restart the service, and local SQLite/files are ephemeral on the Free plan. Use a paid Background Worker for reliable 24/7 operation.

If YouTube shows `Sign in to confirm you're not a bot`, export the YouTube cookies in Netscape format, Base64-encode the file, and add the result as the Render secret `YOUTUBE_COOKIES_B64`. The bot uses this secret for both YouTube search and stream extraction. Never commit the cookie file or put it in a public repository; cookies grant access to the associated browser session.

## Music commands

- `bplay <url|query>`
- `bskip`
- `bpause`
- `bresume`
- `bstop`
- `bleave`
- `bqueue`
- `bnow` / `bnp`
- `bvolume <0-200>`
- `bloop`
- `bautoplay`
- `bjoin`

## Notes

- This bot keeps the existing music playback flow and does not replace the current `yt-dlp` + FFmpeg-based stream behavior.
- No MongoDB or SQLite layer is required for the music runtime unless a future requirement adds persistent per-guild music settings.
- The legacy `main.py` entrypoint remains as part of the original project, but the music-only deploy path is `music_bot.py`.
