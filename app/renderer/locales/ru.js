// Russian texts of the interface: the only place UI text lives. Keys are
// "namespace.name"; {name} is replaced by t(key, {name: value}).
// A plain script (not a module) so it loads the same way in Electron, in a
// headless browser and in node:test.
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.LOCALE_RU = value;
}(typeof self !== 'undefined' ? self : this, () => ({
  'app.title': 'Work IDE',
  'app.loading': 'Загрузка…',
  'app.error': 'Ошибка: {message}',
  'app.no_identities': 'Идентичностей пока нет. Как создать первую — в docs/ONBOARDING.md.',
  'app.refresh': '⟳ Обновить',
  'app.refresh_hint': 'Перечитать списки и перезагрузить интерфейс (разметку, стили, код)',

  'identity.never_collected': 'По этой идентичности вакансии ещё не собирались. Нажми «Собрать вакансии».',
  'identity.no_segments': 'В последней подборке нет рынков.',

  'selection.caption': 'Подборка №{id} · прогон {run} · {date}',
  'selection.rebuild': 'пересборка без скачивания',

  'run.collect': 'Собрать вакансии',
  'run.collecting': 'Идёт сбор вакансий…',
  'run.collecting_stage': 'Идёт сбор: {stage}',
  'run.collecting_since': 'Сбор идёт с {time} (UTC)',
  'run.feedback': 'Разобрать фидбек ({n})',
  'run.stop': 'Остановить',
  'run.running': 'Идёт {kind}: {identity}…',
  'run.kind.collect': 'сбор вакансий',
  'run.kind.feedback': 'разбор фидбека',
  'run.finished': 'Запуск завершён.',
  'run.failed': 'Запуск завершился с ошибкой (код {code}).',
  'run.stopped': 'Запуск остановлен.',
  'run.claude_not_found': 'Не найдена команда claude. Установи Claude Code CLI и проверь PATH.',
  'run.busy': 'Уже идёт другой запуск.',
  'run.log_title': 'Лог запуска',

  'filter.legend': 'Показать',
  'filter.fresh_new': 'Свежие без фидбека',
  'filter.all': 'Все',
  'filter.fresh': 'Все свежие',
  'filter.applied': 'Откликнулся',
  'filter.rejected': 'Отказался',
  'filter.bugged': 'Багнутые',
  'filter.expired': 'Просроченные',
  'filter.count': '({n})',

  'class.hot_lead': '🔥 Горячие — смотреть в первую очередь',
  'class.worth_a_look': '👀 Стоит посмотреть',
  'class.long_shot': '🕰️ Дальний прицел',
  'class.national_market': '🌍 Национальные рынки',
  'class.remote_unconfirmed': '🏢 Удалёнка не подтверждена',
  'class.engagement_unconfirmed': '⏱️ Часы не подтверждены',

  'list.empty': 'Здесь пусто.',
  'list.show_more': 'Показать ещё {n}',
  'list.show_less': 'Свернуть',

  'row.details': 'Подробнее',
  'row.posted_on': '📅 Опубликована: {date}',
  'row.first_seen_on': '📥 Скачана: {date}',
  'row.date_unknown': 'не указано',
  'row.salary': '💰 ЗП',
  'row.hiring_country': '🌍 Страна найма',
  'row.to_confirm': '❓ Осталось уточнить',
  'row.technologies': '🧰 Технологии',
  'row.reputation': '⭐ Репутация',
  'row.company_age': '🏛 Компания',
  'row.company_site': '🏢 Сайт компании',
  'row.note': 'Заметка',

  'badge.fresh': 'свежая',
  'badge.manual_review': 'нужна ручная проверка',

  'action.open': '🔗 Открыть ссылку на вакансию',
  'action.applied': 'Откликнулся',
  'action.rejected': 'Не подходит',
  'action.bugged': 'Ошибка подборки',
  'action.expired': 'Вакансия просрочена',
  'action.undo': 'отменить',

  'reason.rejected': 'Почему не подходит? (необязательно)',
  'reason.bugged': 'Что не так с подборкой? (необязательно)',
  'reason.save': 'Сохранить',
  'reason.cancel': 'Отмена',

  'status.applied': 'Откликнулся',
  'status.rejected': 'Не подходит',
  'status.bugged': 'Ошибка подборки',
  'status.expired': 'Вакансия просрочена',
  'stub.marked': 'Отмечено: {status}',
})));
