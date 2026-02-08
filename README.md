# ARC SPY (Discord Bot)

ARC SPY is a public Discord bot that:
- Posts and **auto-updates** an "ACTIVE Events" embed panel per server (guild).
- Lets server admins create/remove that panel via slash commands or prefix commands.
- Lets users browse "blueprint intel" from a CSV dataset (paged UI).

It pulls live data from the MetaForge ARC Raiders API and formats event end-times using Discord timestamps (e.g. `<t:UNIX:t>` for time-only).

---

## Features

- **Per-server panel**: `/set_event_panel` posts a panel message in the current channel and stores the channel/message IDs in `guild_config.json`.
- **Auto updater**: background task refreshes panels every ~5 minutes.
- **Blueprint browser**: `/blueprints` (ephemeral) browses your CSV intel with Next/Prev buttons.
- **Item enrichment**: caches `/items` so blueprint pages can show icons/rarity/description.

---

## Support / Patreon

If you find ARC SPY useful and want to support development/hosting costs, you can support me here:
- **Patreon**: https://patreon.com/connorbotboi?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink

---

## Requirements

- Python 3.11+ recommended
- A Discord application + bot token
- `discord.py` 2.x

---

## Setup

### 1) Create a Discord application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an application → add a **Bot** user.
3. Copy the bot token.

### 2) Configure gateway intents
This bot uses prefix commands (`A$...`) which require reading message content. `message_content` is a **privileged intent** and must be enabled in the Developer Portal if you keep prefix commands.

In **Developer Portal → Bot → Privileged Gateway Intents**:
- Enable **Message Content Intent** (recommended if you want prefix commands)
- Members/presences are not needed

> If you only want slash commands, you can remove/disable message content usage in code and disable that intent.

### 3) Invite the bot to your server
Use an OAuth2 URL with these **scopes**:
- `bot`
- `applications.commands`

Relevant permissions (minimum practical set):
- View Channels
- Send Messages
- Embed Links
- Read Message History

Use the [Discord Permissions Calculator](https://discordapi.com/permissions.html) to generate your invite URL.

### 4) Configure environment variables
Copy `.env.example` to `.env` and fill it in, or export the variables in your host.

### 5) Install and run
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt

python public-bot.py
```

---

## Commands

### Slash commands
- `/set_event_panel` (Manage Server): post a panel in this channel and start updating it.
- `/remove_event_panel` (Manage Server): stop updating this server's panel.
- `/blueprints`: browse blueprint intel (ephemeral).
- `/help`: show help (includes Patreon link).
- `/update_events` (owner-only): force-refresh panels.
- `/reload_blueprints` (owner-only): reload the CSV.
- `/refresh_cache` (owner-only): refresh item cache.

### Prefix commands (optional)
Prefix: `A$`
- `A$set_event_panel`, `A$remove_event_panel`, `A$blueprints`, `A$help`, etc.

---

## Data files

### `guild_config.json`
Created/updated automatically.
Format:
```json
{
  "123456789012345678": {
    "channel_id": 111111111111111111,
    "message_id": 222222222222222222
  }
}
```

### Blueprint CSV
By default the bot reads: `./arc_raiders_blueprints_final.csv` (override with `BLUEPRINTS_CSV_PATH`).

Expected columns:
- `BlueprintName`, `Map`, `MapCondition`, `Scavengable`, `Containers`, `QuestReward`, `TrialsReward`, `ContainerTypeAssumed`, `DropRateEstimate_PerContainer`, `AvgRaidsEstimate_6Containers`, `AvgRaidsEstimate_9Containers`, `Notes`, `LocationNotes`, `BestKnownRoute`, `CraftingMaterials`, `WorkshopLevel`

---

## Hosting notes

### Recommended
- Linux VPS (systemd), Docker, or a platform with persistent disk (so `guild_config.json` survives restarts).
- Consider using a process manager like systemd, PM2, or supervisor for auto-restart.

### systemd example (sketch)
Create `/etc/systemd/system/arcspy.service`:
```ini
[Unit]
Description=ARC SPY Discord Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/bot
EnvironmentFile=/path/to/bot/.env
ExecStart=/path/to/bot/.venv/bin/python public-bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable arcspy
sudo systemctl start arcspy
```

### Important
- If your host is **ephemeral** (disk resets), you'll lose `guild_config.json` unless you mount persistent storage.

---

## Security / Operational notes
- **Never commit your bot token** — use `.env` or environment variables.
- Consider using slash commands only (remove message content intent) for easier approval at scale. Message Content Intent is privileged and requires manual approval for verified bots.
- Rate limiting: Discord has aggressive rate limits. The bot uses a 5-minute update cycle to stay safe.

---

## Project structure
```
arc-spy-bot/
├── public-bot.py                        # Main bot code
├── arc_raiders_blueprints_final.csv    # Blueprint intel dataset
├── guild_config.json                   # Auto-generated per-guild config
├── .env                                # Your secrets (DO NOT COMMIT)
├── .env.example                        # Template
├── requirements.txt                    # Python dependencies
├── README.md                           # This file
├── LICENSE                             # MIT or Apache-2.0
└── .github/
    └── workflows/
        └── ci.yml                      # Lint + format check
```

---

## Contributing

Contributions welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Run `ruff check` and `ruff format` before committing
4. Open a PR with a clear description

---

## License
See `LICENSE` (MIT recommended for maximum permissiveness).

---

## Credits
- Built with [discord.py](https://github.com/Rapptz/discord.py)
- Data from [MetaForge ARC Raiders API](https://metaforge.app/api/arc-raiders)
- Blueprint intel curated by the community

---

## Links
- **Patreon**: https://patreon.com/connorbotboi?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink
- **Discord Developer Portal**: https://discord.com/developers/applications
- **discord.py Docs**: https://discordpy.readthedocs.io/
