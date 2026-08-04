"""
Тесты парсера LinkedIn.

Это единственный HTML-источник проекта: гостевая страница не документирована и
может измениться в любой день. Поэтому проверяется не только «разбирает
правильную вёрстку», но и — что важнее — «при изменившейся вёрстке возвращает
НОЛЬ и ошибку, а не поток мусора». Молча отравленная база хуже пустой.
"""
import fetch_linkedin


# Слепок реальной вёрстки, снятый 2026-08-04 (сокращён до двух карточек).
SNAPSHOT = """
<li>
  <div class="base-card relative job-search-card">
    <a class="base-card__full-link" href="https://il.linkedin.com/jobs/view/dotnet-developer-at-ravendb-4123456789?trk=guest">
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
        Dotnet Developer
      </h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://il.linkedin.com/company/ravendb">RavenDB</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Hadera, Haifa District, Israel</span>
        <time class="job-search-card__listdate" datetime="2026-08-01">2 days ago</time>
      </div>
    </div>
  </div>
</li>
<li>
  <div class="base-card relative job-search-card">
    <a class="base-card__full-link" href="https://ch.linkedin.com/jobs/view/net-engineer-at-acme-9876543210?trk=guest">
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">.NET Engineer</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://ch.linkedin.com/company/acme">Acme AG</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Z&uuml;rich, Switzerland</span>
      </div>
    </div>
  </div>
</li>
"""

# Что придёт, если LinkedIn поменяет вёрстку: карточки на месте, классы другие.
CHANGED_LAYOUT = """
<li><div class="jobCard"><span class="jobCard__heading">Dotnet Developer</span>
<span class="jobCard__org">RavenDB</span></div></li>
<li><div class="jobCard"><span class="jobCard__heading">.NET Engineer</span>
<span class="jobCard__org">Acme AG</span></div></li>
"""


def _parse(page_html, location="Israel"):
    return [rec for card in fetch_linkedin._CARD_RE.findall(page_html)
            for rec in [fetch_linkedin._card_to_common_schema(card, location)]
            if rec is not None]


def test_snapshot_parses_into_complete_records():
    records = _parse(SNAPSHOT)
    assert len(records) == 2

    first = records[0]
    assert first["title"] == "Dotnet Developer"
    assert first["company"] == "RavenDB"
    assert first["url"].startswith("https://il.linkedin.com/jobs/view/")
    assert "?" not in first["url"], "трекинговые параметры не должны попадать в id"
    assert first["location_raw"] == "Hadera, Haifa District, Israel"
    assert first["posted_at"] == "2026-08-01"
    assert first["remote"] is True, "запрос всегда идёт с фильтром remote"


def test_html_entities_are_decoded():
    """Иначе в отчёт поедут «Z&uuml;rich» и «&amp;» вместо нормального текста."""
    records = _parse(SNAPSHOT, location="Switzerland")
    assert records[1]["location_raw"] == "Zürich, Switzerland"


def test_market_is_recorded_as_a_tag():
    """Страна запроса надёжнее вольного текста в карточке и нужна отчёту,
    чтобы показать, по какому рынку нашли вакансию."""
    records = _parse(SNAPSHOT, location="Israel")
    assert "market:Israel" in records[0]["tags"]


def test_changed_layout_yields_nothing_rather_than_garbage():
    """Главная страховка источника: лучше ноль записей и явная ошибка, чем
    мусор, который тихо отравит базу и всплывёт в отчёте как вакансия."""
    assert _parse(CHANGED_LAYOUT) == []


def test_card_without_mandatory_fields_is_skipped():
    """Реклама и блоки «похожие компании» приходят теми же <li>."""
    promo = '<li><div class="base-card"><h3 class="base-search-card__title">Реклама</h3></div></li>'
    assert _parse(promo) == []


def test_fetch_reports_format_change_as_an_error(monkeypatch):
    """Когда карточки есть, а разобрать нельзя ни одной — это сбой формата,
    и он обязан попасть в state.json, а не выглядеть как «на рынке пусто»."""
    monkeypatch.setattr(fetch_linkedin, "_fetch_page",
                        lambda *a, **k: CHANGED_LAYOUT)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)

    records, note = fetch_linkedin.fetch(keywords=["C#"], locations=["Israel"], max_pages=1)
    assert records == []
    assert "формат страницы изменился" in note


def test_fetch_deduplicates_across_keywords(monkeypatch):
    """Одна вакансия находится по нескольким ключевым словам — в базу она
    должна попасть один раз, иначе дубли размножатся по числу слов."""
    monkeypatch.setattr(fetch_linkedin, "_fetch_page", lambda *a, **k: SNAPSHOT)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)

    records, _ = fetch_linkedin.fetch(
        keywords=["C#", ".NET"], locations=["Israel"], max_pages=1
    )
    assert len(records) == 2
