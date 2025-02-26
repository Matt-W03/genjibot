from __future__ import annotations

import dataclasses
import re
import typing

import discord
from discord import app_commands

import database
import utils

if typing.TYPE_CHECKING:
    import core


class MapNameTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        if value not in itx.client.cache.map_names:
            value = utils.fuzz_(value, itx.client.cache.map_names.list)
        return value


class MapTypeTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        if value not in itx.client.cache.map_types:
            value = utils.fuzz_(value, itx.client.cache.map_types.list)
        return value


class MapMechanicsTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        if value not in itx.client.cache.map_mechanics.list:
            value = utils.fuzz_(value, itx.client.cache.map_mechanics.list)
        return value


class MapRestrictionsTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        if value not in itx.client.cache.map_restrictions.list:
            value = utils.fuzz_(value, itx.client.cache.map_restrictions.list)
        return value


@dataclasses.dataclass
class MapSubmission:
    creator: discord.Member | utils.FakeUser
    map_code: str
    map_name: str
    checkpoint_count: int
    description: str | None
    medals: tuple[float, float, float] | None

    guides: list[str] | None = None
    map_types: list[str] | None = None
    mechanics: list[str] | None = None
    restrictions: list[str] | None = None
    difficulty: str | None = None  # base difficulty

    def __str__(self):
        return utils.Formatter(self.to_dict()).format_map()

    def to_dict(self) -> dict[str, str]:
        return {
            "Code": self.map_code,
            "Map": self.map_name,
            "Type": self.map_types_str,
            "Checkpoints": str(self.checkpoint_count),
            "Difficulty": self.difficulty,
            "Mechanics": self.mechanics_str,
            "Restrictions": self.restrictions_str,
            "Guide": self.guide_str,
            "Medals": self.medals_str,
            "Desc": self.description,
        }

    @staticmethod
    def _remove_nulls(sequence):
        return [x for x in sequence if x is not None]

    @property
    def mechanics_str(self):
        self.mechanics = self._remove_nulls(self.mechanics)
        if self.mechanics:
            return ", ".join(self.mechanics)
        return None

    @property
    def restrictions_str(self):
        self.restrictions = self._remove_nulls(self.restrictions)
        if self.restrictions:
            return ", ".join(self.restrictions)
        return None

    @property
    def map_types_str(self):
        self.map_types = self._remove_nulls(self.map_types)
        if self.map_types:
            return ", ".join(self.map_types)
        return None

    @property
    def gold(self):
        if self.medals and self.medals[0]:
            return self.medals[0]
        return None

    @property
    def silver(self):
        if self.medals and self.medals[1]:
            return self.medals[1]
        return None

    @property
    def bronze(self):
        if self.medals and self.medals[2]:
            return self.medals[2]
        return None

    @property
    def guide_str(self):
        all_guides = []
        for count, link in enumerate(self.guides, start=1):
            if link:
                all_guides.append(f"[Link {count}]({link})")
        return ", ".join(all_guides)

    @property
    def medals_str(self):
        formatted_medals = []

        if self.gold:
            formatted_medals.append(f"{utils.FULLY_VERIFIED_GOLD} {self.gold}")

        if self.silver:
            formatted_medals.append(f"{utils.FULLY_VERIFIED_SILVER} {self.silver}")

        if self.bronze:
            formatted_medals.append(f"{utils.FULLY_VERIFIED_BRONZE} {self.bronze}")

        if not formatted_medals:
            return ""
        return " | ".join(formatted_medals)

    def set_extras(self, **args):
        for k, v in args.items():
            setattr(self, k, v)

    async def insert_playtest(
        self,
        itx: discord.Interaction[core.Genji],
        thread_id: int,
        thread_msg_id: int,
        new_map_id: int,
    ):
        await itx.client.database.set(
            """
            INSERT INTO playtest (thread_id, message_id, map_code, user_id, value, is_author, original_msg)
            VALUES ($1, $2, $3, $4, $5, $6, $7) 
            """,
            thread_id,
            thread_msg_id,
            self.map_code,
            itx.user.id,
            utils.DIFFICULTIES_RANGES[self.difficulty][0],
            True,
            new_map_id,
        )

    async def insert_maps(self, itx: discord.Interaction[core.Genji], mod: bool):
        await itx.client.database.set(
            """
            INSERT INTO 
            maps (map_name, map_type, map_code, "desc", official, checkpoints) 
            VALUES ($1, $2, $3, $4, $5, $6);
            """,
            self.map_name,
            self.map_types,
            self.map_code,
            self.description,
            mod,
            self.checkpoint_count,
        )

    async def insert_mechanics(self, itx: discord.Interaction[core.Genji]):
        mechanics = [(self.map_code, x) for x in self.mechanics]
        await itx.client.database.set_many(
            """
            INSERT INTO map_mechanics (map_code, mechanic) 
            VALUES ($1, $2);
            """,
            mechanics,
        )

    async def insert_restrictions(self, itx: discord.Interaction[core.Genji]):
        restrictions = [(self.map_code, x) for x in self.restrictions]
        await itx.client.database.set_many(
            """
            INSERT INTO map_restrictions (map_code, restriction) 
            VALUES ($1, $2);
            """,
            restrictions,
        )

    async def insert_map_creators(self, itx: discord.Interaction[core.Genji]):
        await itx.client.database.set(
            """
            INSERT INTO map_creators (map_code, user_id) 
            VALUES ($1, $2);
            """,
            self.map_code,
            self.creator.id,
        )

    async def insert_map_ratings(self, itx: discord.Interaction[core.Genji]):
        await itx.client.database.set(
            """
            INSERT INTO map_ratings (map_code, user_id, difficulty) 
            VALUES ($1, $2, $3);
            """,
            self.map_code,
            self.creator.id,
            utils.DIFFICULTIES_RANGES[self.difficulty][0],
        )

    async def insert_guide(self, itx: discord.Interaction[core.Genji]):
        _guides = [(self.map_code, guide) for guide in self.guides if guide]
        if _guides:
            await itx.client.database.set_many(
                """INSERT INTO guides (map_code, url) VALUES ($1, $2);""",
                _guides,
            )

    async def insert_medals(self, itx: discord.Interaction[core.Genji]):
        if self.medals:
            await itx.client.database.set(
                """
                INSERT INTO map_medals (gold, silver, bronze, map_code)
                VALUES ($1, $2, $3, $4);
                """,
                self.gold,
                self.silver,
                self.bronze,
                self.map_code,
            )

    async def insert_timestamp(self, itx: discord.Interaction[core.Genji], mod: bool):
        if not mod:
            await itx.client.database.set(
                """
                INSERT INTO map_submission_dates (user_id, map_code)
                VALUES ($1, $2);
                """,
                self.creator.id,
                self.map_code,
            )

    async def insert_all(self, itx: discord.Interaction[core.Genji], mod: bool):
        await self.insert_maps(itx, mod)
        await self.insert_mechanics(itx)
        await self.insert_restrictions(itx)
        await self.insert_map_creators(itx)
        await self.insert_map_ratings(itx)
        await self.insert_guide(itx)
        await self.insert_medals(itx)
        await self.insert_timestamp(itx, mod)


async def get_map_info(
    client: core.Genji, message_id: int | None = None
) -> list[database.DotRecord | None]:
    return [
        x
        async for x in client.database.get(
            """
            SELECT map_name,
                   map_type,
                   m.map_code,
                   "desc",
                   official,
                   archived,
                   AVG(value) as value,
                   array_agg(DISTINCT url)              AS guide,
                   array_agg(DISTINCT mech.mechanic)    AS mechanics,
                   array_agg(DISTINCT rest.restriction) AS restrictions,
                   checkpoints,
                   array_agg(DISTINCT mc.user_id)       AS creator_ids,
                   gold,
                   silver,
                   bronze,
                   p.message_id
            FROM playtest p
                     LEFT JOIN maps m on m.map_code = p.map_code
                     LEFT JOIN map_mechanics mech on mech.map_code = m.map_code
                     LEFT JOIN map_restrictions rest on rest.map_code = m.map_code
                     LEFT JOIN map_creators mc on m.map_code = mc.map_code
                     LEFT JOIN users u on mc.user_id = u.user_id
                     LEFT JOIN guides g on m.map_code = g.map_code
                     LEFT JOIN map_medals mm on m.map_code = mm.map_code
            WHERE is_author = TRUE AND ($1::bigint IS NULL OR $1::bigint = p.message_id)
            GROUP BY checkpoints, map_name,
                     m.map_code, "desc", official, map_type, gold, silver, bronze, archived, p.message_id
            """,
            message_id,
        )
    ]


_MAPS_BASE_URL = "http://207.244.249.145/assets/images/map_banners/"


@dataclasses.dataclass
class MapMetadata:
    NAME: str
    COLOR: discord.Color
    IMAGE_URL: str = ""

    def __post_init__(self):
        self.IMAGE_URL = _MAPS_BASE_URL + self._remove_extra_chars(self.NAME) + ".png"

    def _remove_extra_chars(self, string: str):
        return re.sub(r"[\s:()\']", "", string.lower())


all_map_constants = [
    MapMetadata("Antarctic Peninsula", discord.Color.from_str("#29A0CC")),
    MapMetadata("Ayutthaya", discord.Color.gold()),
    MapMetadata("Black Forest", discord.Color.from_str("#94511C")),
    MapMetadata("Blizzard World", discord.Color.from_str("#39AAFF")),
    MapMetadata("Busan", discord.Color.from_str("#FF9F00")),
    MapMetadata("Castillo", discord.Color.from_str("#E13C3C")),
    MapMetadata("Chateau Guillard", discord.Color.from_str("#BCBCBC")),
    MapMetadata("Circuit Royal", discord.Color.from_str("#00008B")),
    MapMetadata("Colosseo", discord.Color.from_str("#BF7F00")),
    MapMetadata("Dorado", discord.Color.from_str("#008a8a")),
    MapMetadata("Ecopoint: Antarctica", discord.Color.from_str("#29A0CC")),
    MapMetadata("Eichenwalde", discord.Color.from_str("#53E500")),
    MapMetadata("Esperanca", discord.Color.from_str("#7BD751")),
    MapMetadata("Hanamura", discord.Color.from_str("#EF72A3")),
    MapMetadata("Havana", discord.Color.from_str("#00D45B")),
    MapMetadata("Hollywood", discord.Color.from_str("#FFFFFF")),
    MapMetadata("Horizon Lunar Colony ", discord.Color.from_str("#000000")),
    MapMetadata("Ilios", discord.Color.from_str("#008FDF")),
    MapMetadata("Junkertown", discord.Color.from_str("#EC9D00")),
    MapMetadata("Kanezaka", discord.Color.from_str("#DF3A4F")),
    MapMetadata("King's Row", discord.Color.from_str("#105687")),
    MapMetadata("Lijiang Tower", discord.Color.from_str("#169900")),
    MapMetadata("Malevento", discord.Color.from_str("#DDD816")),
    MapMetadata("Midtown", discord.Color.from_str("#BCBCBC")),
    MapMetadata("Necropolis", discord.Color.from_str("#409C00")),
    MapMetadata("Nepal", discord.Color.from_str("#93C0C7")),
    MapMetadata("New Queen Street", discord.Color.from_str("#CD1010")),
    MapMetadata("Numbani", discord.Color.from_str("#3F921B")),
    MapMetadata("Oasis", discord.Color.from_str("#C98600")),
    MapMetadata("Paraiso", discord.Color.from_str("#19FF00")),
    MapMetadata("Paris", discord.Color.from_str("#6260DA")),
    MapMetadata("Petra", discord.Color.from_str("#DDD816")),
    MapMetadata("Practice Range", discord.Color.from_str("#000000")),
    MapMetadata("Rialto", discord.Color.from_str("#21E788")),
    MapMetadata("Route 66", discord.Color.from_str("#FF9E2F")),
    MapMetadata("Shambali", discord.Color.from_str("#2986CC")),
    MapMetadata("Temple of Anubis", discord.Color.from_str("#D25E00")),
    MapMetadata("Volskaya Industries", discord.Color.from_str("#8822DC")),
    MapMetadata("Watchpoint: Gibraltar", discord.Color.from_str("#BCBCBC")),
    MapMetadata("Workshop Chamber", discord.Color.from_str("#000000")),
    MapMetadata("Workshop Expanse", discord.Color.from_str("#000000")),
    MapMetadata("Workshop Green Screen", discord.Color.from_str("#3BB143")),
    MapMetadata("Workshop Island", discord.Color.from_str("#000000")),
    MapMetadata("Framework", discord.Color.from_str("#000000")),
    MapMetadata("Tools", discord.Color.from_str("#000000")),
    MapMetadata("Talantis", discord.Color.from_str("#1AA7EC")),
    MapMetadata("Chateau Guillard (Halloween)", discord.Color.from_str("#BCBCBC")),
    MapMetadata("Eichenwalde (Halloween)", discord.Color.from_str("#53E500")),
    MapMetadata("Hollywood (Halloween)", discord.Color.from_str("#FFFFFF")),
    MapMetadata("Black Forest (Winter)", discord.Color.from_str("#94511C")),
    MapMetadata("Blizzard World (Winter)", discord.Color.from_str("#39AAFF")),
    MapMetadata("Ecopoint: Antarctica (Winter)", discord.Color.from_str("#29A0CC")),
    MapMetadata("Hanamura (Winter)", discord.Color.from_str("#EF72A3")),
    MapMetadata("King's Row (Winter)", discord.Color.from_str("#105687")),
    MapMetadata("Busan (Lunar New Year)", discord.Color.from_str("#FF9F00")),
    MapMetadata("Lijiang Tower (Lunar New Year)", discord.Color.from_str("#169900")),
]

MAP_DATA: dict[str, MapMetadata] = {const.NAME: const for const in all_map_constants}

DIFF_TO_RANK = {
    "Beginner": "Ninja",
    "Easy": "Jumper",
    "Medium": "Skilled",
    "Hard": "Pro",
    "Very Hard": "Master",
    "Extreme": "Grandmaster",
    "Hell": "God",
}


async def new_map_newsfeed(
    client: core.Genji,
    user_id: int,
    data: utils.MapSubmission,
):
    nickname = client.cache.users[user_id].nickname
    embed = utils.GenjiEmbed(
        title=f"{nickname} has submitted a new {data.difficulty} map on {data.map_name}!\n",
        description=(
            f"Use the command `/map-search map_code:{data.map_code}` to see the details!"
        ),
        color=getattr(
            MAP_DATA.get(data.map_name, discord.Color.from_str("#000000")),
            "COLOR",
            discord.Color.from_str("#000000"),
        ),
    )
    embed.set_image(url=getattr(MAP_DATA.get(data.map_name, None), "IMAGE_URL", None))
    base_thumbnail_url = "http://207.244.249.145/assets/images/genji_ranks/"
    rank = DIFF_TO_RANK[
        data.difficulty.replace("+", "").replace("-", "").rstrip()
    ].lower()
    embed.set_thumbnail(url=f"{base_thumbnail_url}{rank}.png")
    await client.get_guild(utils.GUILD_ID).get_channel(utils.NEWSFEED).send(embed=embed)
