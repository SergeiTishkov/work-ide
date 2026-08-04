"""
Ярусы рынков труда: какие страны обходить при поиске.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ
----------------------
Список локаций нужен фетчерам, которые умеют искать по стране (в первую
очередь LinkedIn). Собирать его в каждом фетчере заново — гарантированное
расхождение: один обновят, другой забудут.

Таблица стран (`config/derivation/market_tiers.yaml`) общая для всех
идентичностей — она описывает объективное положение дел на рынке. Выбор
ярусов принадлежит идентичности (`profile.target_markets`), потому что это
уже предпочтение конкретного поиска.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TIERS_FILE = "market_tiers.yaml"


def load_tiers() -> dict:
    path = common.SHARED_CONFIG_DIR / "derivation" / TIERS_FILE
    return (common.load_yaml(path) or {}).get("tiers", {})


def tier_countries(tier_name: str) -> List[str]:
    tier = load_tiers().get(tier_name) or {}
    return [c.get("name") for c in (tier.get("countries") or []) if c.get("name")]


def target_locations(profile: dict) -> List[str]:
    """Страны для поиска по профилю идентичности.

    Пустой результат — это не ошибка конфигурации, а осознанный выбор: если
    идентичность не назвала ни одного яруса, фетчеры по странам просто
    ничего не делают, и их выход виден в state.json как ноль.
    """
    cfg = (profile or {}).get("target_markets") or {}
    names: List[str] = []

    for tier in cfg.get("tiers") or []:
        for country in tier_countries(tier):
            if country not in names:
                names.append(country)

    for extra in cfg.get("extra_locations") or []:
        if extra not in names:
            names.append(extra)

    return names


def avoided_countries(profile: dict) -> List[str]:
    """Страны, которые поиск обходит: нетто-экспортёры разработки плюс
    исключённые по практическим причинам.

    Нужны не фетчерам, а скорингу и отчёту — чтобы объяснить человеку, почему
    вакансия из такой страны не попала в выдачу.
    """
    del profile  # список одинаков для всех: он про рынок, а не про человека
    return tier_countries("exporter_avoid") + tier_countries("excluded_practical")
