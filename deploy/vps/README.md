# Публичный стенд «Анық» на VPS

`https://anyq.an8kk.dev`: веб-сервер `python -m web` (Starlette + uvicorn) на `127.0.0.1:8520`, наружу через отдельный туннель Cloudflare. Ни адреса
сервера, ни ключей в репозитории нет.

## Что где

| Что | Где на VPS |
|---|---|
| код релиза | `/opt/anyq/<sha>/` (хозяин `anyq`), ссылка `/opt/anyq/current`; хранятся 3 последних |
| окружение Python | `/opt/anyq/<sha>/app/.venv` (`uv sync --frozen --no-dev`, Python 3.12) |
| состояние | `/var/lib/anyq/`: `city_feedback.json`, `requests.jsonl` (+ `.1`), `profiles/`, `llm_cache.json`, `uv-cache/` |
| служба приложения | `anyq.service` (пользователь `anyq`, без shell и sudo) |
| туннель | `cloudflared-anyq.service`, конфиг `/etc/cloudflared/anyq.yml`, ключи туннеля `/etc/cloudflared/<id>.json` |
| цепочка моделей и ключи | `/etc/anyq/llm.env` (необязательный файл сервера, 0640 `root:anyq`; в git его нет) |
| афиша | `anyq-events.service` + `anyq-events.timer` (раз в 6 часов, обновляет `data/events.json` релиза) |

Стенд — обычное живое приложение: ни фиксированного времени, ни записанных ответов, ни пометок о режиме в интерфейсе. В
`anyq.service` нет `WALKS_ENV`, `WALKS_DEMO_PIN`, `WALKS_CACHE_PIN` и `WALKS_AIR_DEMO`: каждый запрос отвечается по реальному времени
Астаны (или по времени, которое выбрал человек: «через час», «вечером»), с живой погодой, живыми маршрутами Valhalla и
живыми отметками людей; поэтому ночью «куда поесть» не показывает место, закрытое в это время. PM2.5 из Open-Meteo не
запрашивается (бесплатный API — только для некоммерческого использования): смог виден по дыму и дымке на станции и по
уведомлениям НМУ.

**Отметки людей** стартуют пустыми: `ExecStartPre` создаёт `/var/lib/anyq/city_feedback.json` как `[]`, если файла нет (сид
`data/city_feedback.json` с 28 демонстрационными отметками на стенд не копируется). Страница «Город» показывает только то, что
оставили посетители. Спрос на ней — только из настоящего журнала `requests.jsonl`: имитированный `data/demand_sim.jsonl`
отдаётся лишь при `WALKS_DEMAND_SIM=1` (на стенде не задан), пока в журнале меньше k запросов в группе, видно честное «пусто».
Чтобы очистить отметки на уже работающем стенде (файл с сидом остался от прошлого запуска):
`echo '[]' > /var/lib/anyq/city_feedback.json && systemctl restart anyq`.

### Спутниковый слой: `/etc/anyq/arcgis.key`

Слой «Спутник» всегда есть (плитки EOX кэшируются в `/var/lib/anyq/tiles`, `WALKS_TILE_CACHE`; прогрев — `app/scripts/seed_tiles.py`).
Более чёткий снимок Esri World Imagery включается файлом `/etc/anyq/arcgis.key` (одна строка — ключ ArcGIS Location Platform,
`root:anyq`, 0640; в git его нет), на который указывает `Environment=ARCGIS_API_KEY_FILE` в `anyq.service`. Нет файла или он пуст —
`/api/config` отдаёт `satellite_hd: false`, слой остаётся на EOX. Плитки Esri идут через сервер без диска (условия Esri запрещают
хранение), ключ браузеру не уходит.

### Модели: `/etc/anyq/llm.env`

Тексты ответов пишет живая модель по цепочке из необязательного файла `EnvironmentFile=-/etc/anyq/llm.env` (формат
`ИМЯ=значение`, режим 0640, `root:anyq`; ни секретов, ни имён провайдеров в репозитории нет); факты (расстояния, время, часы,
статус) подставляет код и проверяет ответ модели. Когда не ответило ни одно звено цепочки (или файла нет), отвечает шаблон из
данных: на странице это тот же ответ, без пометок. В файле могут быть:

| Переменная | Что |
|---|---|
| `LLM_CHAIN` | цепочка звеньев для текста ответа: `провайдер:модель[@профиль]` через запятую |
| `LLM_INTENT_CHAIN` | то же для разбора запроса |
| `GEMINI_KEY_FILE` | путь к файлу, первая строка которого — ключ Gemini (на сервере, например, `/etc/anyq/gemini.key`, 0640 `root:anyq`) |
| `LLM_PROFILE_<ИМЯ>_BASE_URL`, `LLM_PROFILE_<ИМЯ>_API_KEY_FILE` | адрес OpenAI-совместимого шлюза и файл с его ключом для звеньев `openai:модель@<имя>` |

После правки файла: `systemctl restart anyq`.

### Запасной режим: только записанные ответы (локальный инструмент)

Запись ответов (`data/demo_llm_cache.json`, `scripts/warm_cache.py`, `poe demo`) — локальный инструмент и аварийный запасной
вариант, стенд его не использует. Если модели недоступны совсем, а показывать надо: добавьте drop-in (`systemctl edit anyq`)

```ini
[Service]
Environment=WALKS_ENV=demo
Environment=WALKS_DEMO_PIN=1
Environment=WALKS_CACHE_PIN=1
Environment=WALKS_REPLAY_ONLY=1
```

и `systemctl restart anyq`. Тогда 13 записанных запросов (плитки-примеры, запрос про аэропорт на морозе, казахский запрос и
кнопки уточнений) отвечаются из записи в зафиксированное время (пн 19.10, 14:00; ночной — 23:00) и по ручной погоде, без
вызова модели и без ключа, а любой другой запрос получает шаблон. Записанные запросы строятся с отметками из сида
`data/city_feedback.json`, а не из `/var/lib/anyq/city_feedback.json`. Убрать drop-in:
`systemctl revert anyq && systemctl restart anyq`. Запись обновляют локально: `uv run python scripts/warm_cache.py`.

### Афиша

`anyq-events.timer` запускает `anyq-events.service` в 00:05, 06:05, 12:05 и 18:05 (+ до 10 минут случайной задержки,
`Persistent=true`), `python -m collect.events` обновляет `data/events.json` (+ `events_stats.json`) **на месте, внутри
развёрнутого релиза** (`ReadWritePaths=/opt/anyq/current/data`), поэтому на стенде файл афиши отличается от
закоммитированного снимка, а новый деплой начинает с закоммитированного. Источник, который не ответил, сохраняет прежние события; приложение перечитывает файл при
изменении. `systemctl list-timers anyq-events.timer`, `journalctl -u anyq-events -n 50 --no-pager`.

Страница (`GET /`) отдаётся с `Cache-Control: no-cache, no-transform`: так прокси Cloudflare не подмешивает в неё
скрипт Web Analytics, который строгая CSP (`script-src 'self'`) всё равно блокирует и пишет ошибку в консоль.

Лимиты: `MemoryMax=1G`, `CPUQuota=150%`, `Restart=on-failure`; запись только в `/var/lib/anyq`.
Рост диска от публичного ввода ограничен в коде: журнал запросов ротируется на 5 МБ
(`walks.reqlog.MAX_LOG_BYTES`), отметки людей не больше 5000 (`walks.feedback.MAX_ENTRIES`; если файл отметок содержит
демонстрационные отметки сида, они остаются), профилей не больше 1000 (`walks.profile.MAX_PROFILES`), кэш LLM не больше 300 записей.

## Деплой одной командой с ПК

```powershell
$env:ANYQ_SSH = "root@<адрес сервера>"   # хост не хранится в репозитории
.\deploy\vps\deploy.ps1
```

Скрипт берёт `git archive HEAD` (только закоммиченное; про незакоммиченное в `app/`, `data/`, `deploy/vps/`
предупредит), отправляет по ОДНОМУ ssh-соединению (на порту 22 у сервера ufw LIMIT: примерно 5 новых
соединений за 30 с), на сервере выполняется `remote.sh`: пользователь `anyq`, `uv sync`, установка юнитов,
переключение `current`, перезапуск `anyq`, проверка `/healthz`.

## Туннель (один раз)

Нужен `cert.pem` Cloudflare для зоны `an8kk.dev` (`cloudflared tunnel login` откроет браузер; у
владельца он лежит в `~/.cloudflared/` на ПК). С ПК:

```powershell
cloudflared tunnel create anyq
cloudflared tunnel route dns anyq anyq.an8kk.dev
```

Дальше положить на VPS `<id>.json` в `/etc/cloudflared/` (`cloudflared:cloudflared`, 0600), а `anyq.yml`
собрать из `cloudflared-anyq.yml.template` (подставить id; `root:cloudflared`, 0640) и включить:
`systemctl enable --now cloudflared-anyq`. Юнит ставит `remote.sh`.

## Эксплуатация

```sh
systemctl status anyq cloudflared-anyq
journalctl -u anyq -n 50 --no-pager
curl -s http://127.0.0.1:8520/healthz
# вернуть отметки людей к сиду (демо-сценарии снова как при записи кэша):
rm /var/lib/anyq/city_feedback.json && systemctl restart anyq
```

Откат: `ln -sfn /opt/anyq/<старый sha> /opt/anyq/current && systemctl restart anyq`. Остановить стенд:
`systemctl disable --now cloudflared-anyq anyq`. Остальные службы VPS (tempo, Muse, GradeMaster) деплой не
трогает.
