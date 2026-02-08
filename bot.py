import discord
from discord.ext import commands, tasks
import aiohttp
from datetime import datetime, timezone
import logging
import os
import csv
import json
from dataclasses import dataclass
from typing import Optional
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- CONFIG ----
TOKEN = os.getenv("DISCORD_TOKEN", "REPLACE_ME_REGEN_TOKEN_NOW")
BLUEPRINTS_CSV_PATH = os.getenv("BLUEPRINTS_CSV_PATH", "./arc_raiders_blueprints_final.csv")
CONFIG_PATH = os.getenv("GUILD_CONFIG_PATH", "./guild_config.json")

intents = discord.Intents.default()
intents.message_content = True

API_BASE = "https://metaforge.app/api/arc-raiders"

# ---- Event-specific blueprint mapping (only these display on active-events embed)
EVENT_BLUEPRINTS = {
    "Locked Gate": [
        "Bobcat",
        "Combat Mk. 3 (Aggressive)",
        "Combat Mk. 3 (Flanking)",
        "Compensator III",
        "Extended Barrel",
        "Extended Light Magazine III",
        "Extended Medium Magazine III",
        "Extended Shotgun Magazine III",
        "Lightweight Stock",
        "Muzzle Brake III",
        "Padded Stock",
        "Shotgun Choke III",
        "Shotgun Silencer",
        "Stable Stock III",
        "Vertical Grip III",
    ],
    "Night Raid": [
        "Tempest",
        "Wolfpack",
        "Extended Medium Magazine II",
        "Angled Grip III",
        "Compensator III",
        "Extended Light Magazine III",
        "Extended Medium Magazine III",
        "Extended Shotgun Magazine III",
        "Lightweight Stock",
        "Muzzle Brake III",
        "Padded Stock",
        "Shotgun Choke III",
        "Shotgun Silencer",
        "Stable Stock III",
        "Vertical Grip III",
    ],
    "Electromagnetic Storm": [
        "Snap Hook",
        "Angled Grip III",
        "Compensator III",
        "Extended Barrel",
        "Extended Light Magazine III",
        "Extended Medium Magazine III",
        "Extended Shotgun Magazine III",
        "Lightweight Stock",
        "Muzzle Brake III",
        "Padded Stock",
        "Shotgun Choke III",
        "Shotgun Silencer",
        "Stable Stock III",
        "Vertical Grip III",
    ],
    "Harvester": ["Equalizer", "Jupiter"],
    "Hidden Bunker": ["Vulcano", "Shotgun Silencer"],
    "Matriarch": ["Aphelion"],
}

# ---- CACHES ----
ITEMS_RAW: list[dict] = []
ITEMS_BY_NAME: dict[str, dict] = {}

BP_DB: dict[str, "BlueprintInfo"] = {}

# ---- Per-guild panel config ----
# { "guild_id": { "channel_id": 111, "message_id": 222 } }
GUILD_CFG: dict[str, dict] = {}


def load_guild_cfg() -> dict[str, dict]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.error(f"Failed to read {CONFIG_PATH}: {e}")
    return {}


def save_guild_cfg(cfg: dict[str, dict]):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
    os.replace(tmp, CONFIG_PATH)


# ---- HTTP ----
async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict | None = None):
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"HTTP {resp.status} from {resp.url} body={text[:200]}")
        return await resp.json()


# ---- ITEMS CACHE (PAGINATED) ----
async def load_items_all_pages(limit: int = 50) -> list[dict]:
    all_items: list[dict] = []
    async with aiohttp.ClientSession() as session:
        first = await fetch_json(session, f"{API_BASE}/items", params={"page": 1, "limit": limit})
        first_data = first.get("data", first)
        if not isinstance(first_data, list):
            raise RuntimeError("Unexpected /items shape (expected data:list)")
        all_items.extend(first_data)

        pagination = first.get("pagination") or {}
        total_pages = int(pagination.get("totalPages") or 1)

        for page in range(2, total_pages + 1):
            payload = await fetch_json(session, f"{API_BASE}/items", params={"page": page, "limit": limit})
            page_data = payload.get("data", payload)
            if not isinstance(page_data, list):
                raise RuntimeError(f"Unexpected /items page {page} shape")
            all_items.extend(page_data)

    return all_items


def build_items_index(raw_items: list[dict]) -> dict[str, dict]:
    by_name: dict[str, dict] = {}
    for it in raw_items:
        nm = it.get("name")
        if isinstance(nm, str) and nm.strip():
            by_name[nm.strip().lower()] = it
    return by_name


async def refresh_item_cache():
    global ITEMS_RAW, ITEMS_BY_NAME
    ITEMS_RAW = await load_items_all_pages(limit=50)
    ITEMS_BY_NAME = build_items_index(ITEMS_RAW)
    logger.info(f"Items cached: {len(ITEMS_BY_NAME)}")


@tasks.loop(hours=168)
async def refresh_cache_weekly():
    try:
        await refresh_item_cache()
    except Exception as e:
        logger.error(f"Weekly item cache refresh failed: {e}")


# ---- BLUEPRINT DATASET (CSV) ----
def _clean(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _to_float(s: str) -> Optional[float]:
    s = _clean(s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class BlueprintInfo:
    name: str
    map: str
    map_condition: str
    scavengable: str
    containers: str
    quest_reward: str
    trials_reward: str
    container_type_assumed: str
    drop_rate_per_container: Optional[float]
    avg_raids_6: Optional[float]
    avg_raids_9: Optional[float]
    notes: str
    location_notes: str
    best_known_route: str
    crafting_materials: str
    workshop_level: str


def load_blueprints_csv(path: str) -> dict[str, BlueprintInfo]:
    db: dict[str, BlueprintInfo] = {}
    if not os.path.exists(path):
        logger.error(f"Blueprint CSV not found at {path}")
        return db

    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = _clean(row.get("BlueprintName"))
            if not name:
                continue

            info = BlueprintInfo(
                name=name,
                map=_clean(row.get("Map")),
                map_condition=_clean(row.get("MapCondition")),
                scavengable=_clean(row.get("Scavengable")),
                containers=_clean(row.get("Containers")),
                quest_reward=_clean(row.get("QuestReward")),
                trials_reward=_clean(row.get("TrialsReward")),
                container_type_assumed=_clean(row.get("ContainerTypeAssumed")),
                drop_rate_per_container=_to_float(row.get("DropRateEstimate_PerContainer") or ""),
                avg_raids_6=_to_float(row.get("AvgRaidsEstimate_6Containers") or ""),
                avg_raids_9=_to_float(row.get("AvgRaidsEstimate_9Containers") or ""),
                notes=_clean(row.get("Notes")),
                location_notes=_clean(row.get("LocationNotes")),
                best_known_route=_clean(row.get("BestKnownRoute")),
                crafting_materials=_clean(row.get("CraftingMaterials")),
                workshop_level=_clean(row.get("WorkshopLevel")),
            )
            db[name.lower()] = info

    logger.info(f"Blueprint dataset loaded: {len(db)} entries")
    return db


def reload_blueprints():
    global BP_DB
    BP_DB = load_blueprints_csv(BLUEPRINTS_CSV_PATH)


# ---- Formatting helpers ----
def clamp(s: str, n: int) -> str:
    s = str(s) if s is not None else "—"
    return s if len(s) <= n else (s[: n - 1] + "…")


def is_meaningful(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    low = v.lower()
    return low not in {"unknown", "n/a", "na", "-", "—"}


def add_field_if(embed: discord.Embed, name: str, value: str, inline: bool = False):
    if is_meaningful(value):
        embed.add_field(name=name, value=clamp(value, 1024), inline=inline)


def format_found(info: BlueprintInfo) -> str:
    bits = []
    if info.map:
        bits.append(f"Map: {info.map}")
    if info.map_condition:
        bits.append(f"Condition: {info.map_condition}")
    if info.scavengable:
        bits.append(f"Scavengable: {info.scavengable}")
    if info.containers:
        bits.append(f"Containers: {info.containers}")
    if info.quest_reward:
        bits.append(f"Quest reward: {info.quest_reward}")
    if info.trials_reward:
        bits.append(f"Trials reward: {info.trials_reward}")
    if info.container_type_assumed:
        bits.append(f"Container pool: {info.container_type_assumed}")
    if info.notes:
        bits.append(f"Notes: {info.notes}")
    return "\n".join(bits)


def format_routes(info: BlueprintInfo) -> str:
    bits = []
    if info.location_notes:
        bits.append(info.location_notes)
    if info.best_known_route:
        bits.append(f"Route: {info.best_known_route}")
    return "\n".join(bits)


def find_item_for_blueprint(bp_name: str) -> Optional[dict]:
    candidates = [
        f"{bp_name} Blueprint",
        bp_name,
        f"{bp_name} blueprint",
    ]
    for c in candidates:
        it = ITEMS_BY_NAME.get(c.lower())
        if it:
            return it
    return None


class BlueprintView(discord.ui.View):
    def __init__(self, blueprint_names: list[str], author_id: int):
        super().__init__(timeout=300)
        self.blueprint_names = blueprint_names
        self.author_id = author_id
        self.idx = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def embed(self) -> discord.Embed:
        bp_name = self.blueprint_names[self.idx]
        info = BP_DB.get(bp_name.lower())

        embed = discord.Embed(title=f"{bp_name} Blueprint", color=0x2B6CB0)

        it = find_item_for_blueprint(bp_name)
        if it:
            desc = str(it.get("description") or "").strip()
            rarity = str(it.get("rarity") or "").strip()
            icon = it.get("icon")

            if is_meaningful(desc):
                embed.description = clamp(desc, 4096)

            add_field_if(embed, "Rarity", rarity, inline=True)

            if isinstance(icon, str) and icon.startswith("http"):
                embed.set_thumbnail(url=icon)

        if info:
            add_field_if(embed, "Found / how", format_found(info), inline=False)
            add_field_if(embed, "Where to farm", format_routes(info), inline=False)
            add_field_if(embed, "Craft materials", info.crafting_materials, inline=False)
            add_field_if(embed, "Workshop level", info.workshop_level, inline=True)

        if not embed.description and not embed.fields:
            embed.description = "No intel available for this blueprint."

        embed.set_footer(
            text=f"{self.idx+1}/{len(self.blueprint_names)} • Community-maintained data; verify in-game"
        )
        return embed

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.idx = (self.idx - 1) % len(self.blueprint_names)
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.idx = (self.idx + 1) % len(self.blueprint_names)
        await interaction.response.edit_message(embed=self.embed(), view=self)


def owner_only_appcmd():
    async def predicate(interaction: discord.Interaction) -> bool:
        return await interaction.client.is_owner(interaction.user)  # type: ignore
    return discord.app_commands.check(predicate)


class ArcSpyBot(commands.Bot):
    async def setup_hook(self) -> None:
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d global commands: %s", len(synced), [c.name for c in synced])
        except Exception as e:
            logger.error(f"Global command sync failed: {e}")

        reload_blueprints()

        try:
            await refresh_item_cache()
        except Exception as e:
            logger.error(f"Item cache warmup failed (continuing anyway): {e}")


bot = ArcSpyBot(
    command_prefix="A$",
    intents=intents,
    case_insensitive=True,
    activity=discord.Game("Use A$"),
    help_command=None,
)


@bot.event
async def on_ready():
    global GUILD_CFG
    GUILD_CFG = load_guild_cfg()
    logger.info(f"{bot.user} connected! Guilds={len(bot.guilds)}")
    logger.info(f"message_content intent runtime={bot.intents.message_content}")

    if not update_event_panels.is_running():
        update_event_panels.start()
    if not refresh_cache_weekly.is_running():
        refresh_cache_weekly.start()


# ---- PREFIX COMMAND ERROR LOGGING ----
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    err = error
    if isinstance(error, commands.CommandInvokeError) and getattr(error, "original", None):
        err = error.original

    logger.error(
        "Prefix command error: cmd=%s author=%s guild=%s channel=%s error=%s",
        getattr(ctx.command, "qualified_name", None),
        getattr(ctx.author, "id", None),
        getattr(getattr(ctx, "guild", None), "id", None),
        getattr(getattr(ctx, "channel", None), "id", None),
        repr(err),
    )
    logger.error("".join(traceback.format_exception(type(err), err, err.__traceback__)))


# ---- SLASH COMMAND ERROR LOGGING ----
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logger.error(
        "Slash command error: user=%s guild=%s channel=%s error=%s",
        getattr(interaction.user, "id", None),
        getattr(getattr(interaction, "guild", None), "id", None),
        getattr(getattr(interaction, "channel", None), "id", None),
        repr(error),
    )
    logger.error("".join(traceback.format_exception(type(error), error, error.__traceback__)))


def item_display(name: str) -> str:
    it = ITEMS_BY_NAME.get(name.lower())
    return it.get("name", name) if it else name


async def build_active_events_embed() -> discord.Embed:
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, f"{API_BASE}/events-schedule")

    now_utc = datetime.now(timezone.utc)
    now_unix = int(now_utc.timestamp())
    now_ms = now_unix * 1000

    raw = data.get("data", data)
    if not isinstance(raw, list):
        raw = []

    active_by_map: dict[str, list[str]] = {}
    for e in raw:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "Unknown"))
        mp = str(e.get("map", "Unknown"))
        st = e.get("startTime")
        et = e.get("endTime")

        if isinstance(st, (int, float)) and isinstance(et, (int, float)):
            if now_ms >= int(st) and now_ms < int(et):
                active_by_map.setdefault(mp, []).append(name)

    embed = discord.Embed(title="ACTIVE Events", color=0xFF0000)
    if active_by_map:
        embed.description = f"Updated <t:{now_unix}:F> (<t:{now_unix}:R>)"
        for mp, evs in sorted(active_by_map.items()):
            lines: list[str] = []
            for ev in evs[:6]:
                lines.append(f"• {ev}")

                bps = EVENT_BLUEPRINTS.get(ev, [])
                if bps:
                    shown = [item_display(b) for b in bps[:10]]
                    suffix = "…" if len(bps) > 10 else ""
                    lines.append(f"↳ Event blueprints: {', '.join(shown)}{suffix}")
                else:
                    lines.append("↳ Event blueprints: None")

                lines.append("")

            if lines and lines[-1] == "":
                lines.pop()

            embed.add_field(name=mp, value="\n".join(lines), inline=False)
    else:
        embed.description = f"No events active • Updated <t:{now_unix}:F> (<t:{now_unix}:R>)"

    embed.set_footer(text="Event blueprint list is curated; verify drops in-game")
    return embed


@tasks.loop(minutes=5)
async def update_event_panels():
    if not GUILD_CFG:
        return

    try:
        embed = await build_active_events_embed()
    except Exception as e:
        logger.error(f"Failed to build events embed: {e}")
        return

    dead_guilds: list[str] = []

    for guild_id, panel in list(GUILD_CFG.items()):
        try:
            ch_id = int(panel.get("channel_id", 0))
            msg_id = int(panel.get("message_id", 0))
            if not ch_id or not msg_id:
                continue

            channel = bot.get_channel(ch_id)
            if channel is None:
                dead_guilds.append(guild_id)
                continue

            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
            except discord.NotFound:
                dead_guilds.append(guild_id)
            except discord.Forbidden:
                logger.warning(f"No permission to edit panel in guild {guild_id}")
            except discord.HTTPException as he:
                logger.warning(f"HTTP error updating panel in guild {guild_id}: {he}")

        except Exception as e:
            logger.warning(f"Panel update failure guild={guild_id}: {e}")

    if dead_guilds:
        for gid in dead_guilds:
            GUILD_CFG.pop(gid, None)
        save_guild_cfg(GUILD_CFG)
        logger.info(f"Cleaned up {len(dead_guilds)} stale guild panels")


# -----------------------
# Prefix commands (A$...)
# -----------------------
@bot.command(name="set_event_panel")
@commands.has_guild_permissions(manage_guild=True)
async def prefix_set_event_panel(ctx: commands.Context):
    if not ctx.guild or not ctx.channel:
        return

    embed = await build_active_events_embed()
    msg = await ctx.channel.send(embed=embed)

    gid = str(ctx.guild.id)
    GUILD_CFG[gid] = {"channel_id": ctx.channel.id, "message_id": msg.id}
    save_guild_cfg(GUILD_CFG)

    await ctx.reply("Live events panel configured for this server.", mention_author=False)


@bot.command(name="remove_event_panel")
@commands.has_guild_permissions(manage_guild=True)
async def prefix_remove_event_panel(ctx: commands.Context):
    if not ctx.guild:
        return

    gid = str(ctx.guild.id)
    existed = GUILD_CFG.pop(gid, None)
    save_guild_cfg(GUILD_CFG)

    await ctx.reply(
        "Panel configuration removed." if existed else "No panel was configured for this server.",
        mention_author=False,
    )


@bot.command(name="blueprints")
async def prefix_blueprints(ctx: commands.Context):
    if not BP_DB:
        return await ctx.reply("Blueprint data is not loaded.", mention_author=False)

    blueprint_names = sorted((bp.name for bp in BP_DB.values()), key=lambda s: s.lower())
    view = BlueprintView(blueprint_names, author_id=ctx.author.id)
    await ctx.reply(embed=view.embed(), view=view, mention_author=False)


@bot.command(name="update_events")
@commands.is_owner()
async def prefix_update_events(ctx: commands.Context):
    await update_event_panels()
    await ctx.reply("Updated.", mention_author=False)


@bot.command(name="reload_blueprints")
@commands.is_owner()
async def prefix_reload_blueprints(ctx: commands.Context):
    reload_blueprints()
    await ctx.reply(f"Reloaded ({len(BP_DB)} entries).", mention_author=False)


@bot.command(name="refresh_cache")
@commands.is_owner()
async def prefix_refresh_cache(ctx: commands.Context):
    await refresh_item_cache()
    await ctx.reply(f"Refreshed ({len(ITEMS_RAW)} items).", mention_author=False)


@bot.command(name="help")
async def prefix_help(ctx: commands.Context):
    embed = discord.Embed(title="ARC SPY — Commands", color=0x00FF00)
    embed.add_field(name="A$set_event_panel", value="Create or move the live events panel to this channel.", inline=False)
    embed.add_field(name="A$remove_event_panel", value="Remove this server's live events panel configuration.", inline=False)
    embed.add_field(name="A$blueprints", value="Browse blueprint intel (one per page).", inline=False)
    embed.add_field(name="A$help-own", value="Owner-only: show owner commands.", inline=False)
    embed.add_field(
        name="Support",
        value="Patreon: https://patreon.com/connorbotboi?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink",
        inline=False,
    )
    embed.set_footer(text="Some info is community-maintained; verify in-game")
    await ctx.reply(embed=embed, mention_author=False)


@bot.command(name="help-own")
@commands.is_owner()
async def prefix_help_own(ctx: commands.Context):
    embed = discord.Embed(title="ARC SPY — Owner Commands", color=0xF6AD55)
    embed.add_field(name="A$update_events", value="Owner-only: refresh live panels now.", inline=False)
    embed.add_field(name="A$reload_blueprints", value="Owner-only: reload blueprint intel.", inline=False)
    embed.add_field(name="A$refresh_cache", value="Owner-only: refresh item metadata.", inline=False)
    await ctx.reply(embed=embed, mention_author=False)


# -----------------------
# Slash commands (/...)
# -----------------------
@bot.tree.command(name="set_event_panel", description="Create or move the live events panel to this channel")
@discord.app_commands.default_permissions(manage_guild=True)
async def slash_set_event_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild or not interaction.channel:
        return await interaction.followup.send("This command must be used in a server channel.", ephemeral=True)

    embed = await build_active_events_embed()
    try:
        msg = await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        return await interaction.followup.send("I don't have permission to post in this channel.", ephemeral=True)

    gid = str(interaction.guild.id)
    GUILD_CFG[gid] = {"channel_id": interaction.channel.id, "message_id": msg.id}
    save_guild_cfg(GUILD_CFG)

    await interaction.followup.send("Live events panel configured for this server.", ephemeral=True)


@bot.tree.command(name="remove_event_panel", description="Remove this server's live events panel configuration")
@discord.app_commands.default_permissions(manage_guild=True)
async def slash_remove_event_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild:
        return await interaction.followup.send("This command must be used in a server.", ephemeral=True)

    gid = str(interaction.guild.id)
    existed = GUILD_CFG.pop(gid, None)
    save_guild_cfg(GUILD_CFG)

    await interaction.followup.send(
        "Panel configuration removed." if existed else "No panel was configured for this server.",
        ephemeral=True,
    )


@bot.tree.command(name="blueprints", description="Browse blueprint intel")
async def slash_blueprints(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not BP_DB:
        return await interaction.followup.send("Blueprint data is not loaded.", ephemeral=True)

    blueprint_names = sorted((bp.name for bp in BP_DB.values()), key=lambda s: s.lower())
    view = BlueprintView(blueprint_names, author_id=interaction.user.id)
    await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)


@bot.tree.command(name="update_events", description="Owner-only: refresh the live events panel now")
@owner_only_appcmd()
async def slash_update_events(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await update_event_panels()
    await interaction.followup.send("Updated.", ephemeral=True)


@bot.tree.command(name="reload_blueprints", description="Owner-only: reload blueprint intel from disk")
@owner_only_appcmd()
async def slash_reload_blueprints(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    reload_blueprints()
    await interaction.followup.send(f"Reloaded ({len(BP_DB)} entries).", ephemeral=True)


@bot.tree.command(name="refresh_cache", description="Owner-only: refresh item metadata (icons/rarity)")
@owner_only_appcmd()
async def slash_refresh_cache(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        await refresh_item_cache()
        await interaction.followup.send(f"Refreshed ({len(ITEMS_RAW)} items).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Refresh failed: {e}", ephemeral=True)


@bot.tree.command(name="help", description="Show command reference")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="ARC SPY — Commands", color=0x00FF00)
    embed.add_field(name="/set_event_panel", value="Create or move the live events panel to this channel.", inline=False)
    embed.add_field(name="/remove_event_panel", value="Remove this server's live events panel configuration.", inline=False)
    embed.add_field(name="/blueprints", value="Browse blueprint intel (one per page).", inline=False)
    embed.add_field(name="/help-own", value="Owner-only: show owner commands.", inline=False)
    embed.add_field(name="Prefix", value="Also available with: A$ (case-insensitive).", inline=False)
    embed.add_field(
        name="Support",
        value="Patreon: https://patreon.com/connorbotboi?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink",
        inline=False,
    )
    embed.set_footer(text="Some info is community-maintained; verify in-game")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="help-own", description="Owner-only: show owner command reference")
@owner_only_appcmd()
async def slash_help_own(interaction: discord.Interaction):
    embed = discord.Embed(title="ARC SPY — Owner Commands", color=0xF6AD55)
    embed.add_field(name="/update_events", value="Owner-only: refresh live panels now.", inline=False)
    embed.add_field(name="/reload_blueprints", value="Owner-only: reload blueprint intel.", inline=False)
    embed.add_field(name="/refresh_cache", value="Owner-only: refresh item metadata.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN or TOKEN == "REPLACE_ME_REGEN_TOKEN_NOW":
        raise RuntimeError("DISCORD_TOKEN not set")
    bot.run(TOKEN)
