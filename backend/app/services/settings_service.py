from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting
from app.models.prompt_template import PromptTemplate
from app.bootstrap.seed import DEFAULT_SETTINGS, DEFAULT_PROMPTS
from sqlalchemy.dialects.postgresql import insert as pg_insert


class SettingsService:
    async def get_all(self, db: AsyncSession) -> list[Setting]:
        result = await db.execute(select(Setting).order_by(Setting.category, Setting.key))
        return list(result.scalars().all())

    async def get_by_category(self, db: AsyncSession, category: str) -> list[Setting]:
        result = await db.execute(
            select(Setting).where(Setting.category == category).order_by(Setting.key)
        )
        return list(result.scalars().all())

    async def get_value(self, db: AsyncSession, category: str, key: str):
        result = await db.execute(
            select(Setting).where(Setting.category == category, Setting.key == key)
        )
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def get_all_as_dict(self, db: AsyncSession) -> dict[str, dict[str, object]]:
        rows = await self.get_all(db)
        out: dict[str, dict] = {}
        for row in rows:
            out.setdefault(row.category, {})[row.key] = row.value
        return out

    async def update(self, db: AsyncSession, category: str, key: str, value, description: str | None = None) -> Setting:
        result = await db.execute(
            select(Setting).where(Setting.category == category, Setting.key == key)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = Setting(category=category, key=key, value=value, description=description)
            db.add(row)
        else:
            row.value = value
            if description is not None:
                row.description = description
        await db.commit()
        await db.refresh(row)
        return row

    async def reset_defaults(self, db: AsyncSession) -> None:
        for category, key, value, description in DEFAULT_SETTINGS:
            stmt = (
                pg_insert(Setting)
                .values(category=category, key=key, value=value, description=description)
                .on_conflict_do_update(
                    constraint="uq_settings_category_key",
                    set_={"value": value, "description": description},
                )
            )
            await db.execute(stmt)
        await db.commit()

    # --- Prompts ---
    async def get_all_prompts(self, db: AsyncSession) -> list[PromptTemplate]:
        result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.name))
        return list(result.scalars().all())

    async def get_prompt(self, db: AsyncSession, name: str) -> PromptTemplate | None:
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        return result.scalar_one_or_none()

    async def get_all_prompts_as_dict(self, db: AsyncSession) -> dict[str, str]:
        rows = await self.get_all_prompts(db)
        return {row.name: row.template for row in rows}

    async def update_prompt(self, db: AsyncSession, name: str, template: str, description: str | None = None) -> PromptTemplate:
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        row = result.scalar_one_or_none()
        if row is None:
            row = PromptTemplate(name=name, template=template, description=description)
            db.add(row)
        else:
            row.template = template
            if description is not None:
                row.description = description
        await db.commit()
        await db.refresh(row)
        return row

    async def reset_prompts_defaults(self, db: AsyncSession) -> None:
        for name, template, description in DEFAULT_PROMPTS:
            stmt = (
                pg_insert(PromptTemplate)
                .values(name=name, template=template, description=description)
                .on_conflict_do_update(
                    index_elements=["name"],
                    set_={"template": template, "description": description},
                )
            )
            await db.execute(stmt)
        await db.commit()


settings_service = SettingsService()
