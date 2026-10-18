# Свой Valhalla для публичного стенда

Пешие отрезки маршрута на стенде считает свой Valhalla в Docker на том же сервере, по выгрузке OSM только для
Астаны. Приложение ходит к нему по `WALKS_VALHALLA_URL=http://127.0.0.1:8002/route` (`app/walks/walking.py`).

## Зачем

Условия публичного сервера FOSSGIS (`valhalla1.openstreetmap.de`, https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/,
раздел «Nicht erlaubte Nutzungen» / «Prohibited Uses»):

> Die gewerbliche Nutzung ist nur gestattet, wenn die Nutzung der Dienste keinen wesentlichen Teil eines
> Onlineangebots darstellt. Beispiel für keinen wesentlichen Teil: Anfahrtsskizzen auf Websites.

В английской версии той же страницы: *«Commercial use is only permitted if the use of the services does not
constitute a substantial part of an online offering. Example of a non-substantial part: Directions sketches on
websites.»* Кроме того: «Webseiten mit hohem Trafficaufkommen dürfen unsere Services grundsätzlich nicht
nutzen», максимум один запрос в секунду, «Wir garantieren keine Verfügbarkeit», доступ могут закрыть без
предупреждения. Для помощника по прогулкам время и линия пешего пути входят в каждый ответ, то есть это не
«схема проезда на сайте». Поэтому стенд не опирается на чужой демо-сервер: сами данные OSM свободны (ODbL), не
свободен только сервис.

## Что здесь

| Файл | Что делает |
|---|---|
| `docker-compose.yml` | контейнер `anyq-valhalla` (проект `anyq-valhalla`), образ `ghcr.io/valhalla/valhalla-scripted:3.9.1` закреплён тегом и digest; порт `127.0.0.1:8002` (наружу не слушает); `mem_limit 768m` без swap, `cpus 1.5`, `restart: unless-stopped`, healthcheck на `/status`, `read_only`, `cap_drop: ALL`, лог 3×10 МБ |
| `osmium.Dockerfile` | одноразовый образ с `osmium-tool` для вырезки Астаны |
| `update.sh` | первая установка и каждое обновление: скачать Geofabrik `asia/kazakhstan-latest.osm.pbf` (с проверкой md5), вырезать `osmium extract -b 71.20,50.95,71.65,51.30 --strategy simple` (`complete_ways` по всей стране упирается в 2 ГБ памяти и убивается лимитом; ~30 МБ при `simple`, вырезка около 5 МБ), построить тайлы в соседней папке, остановить контейнер, поменять папки, поднять, дождаться healthy, проверочный маршрут; если новый граф не поднялся, возвращает старый |

Данные: `/var/lib/anyq-valhalla/data` (тайлы `valhalla_tiles.tar`, `valhalla.json`, вырезка `astana.osm.pbf`). Тайлы строятся
только `update.sh`, при старте контейнера ничего не строится и не скачивается (`use_tiles_ignore_pbf=True`).
Сборка идёт с пониженным приоритетом и лимитом 2 ГБ памяти, чтобы не мешать соседям на сервере. В тайлы
встраиваются высоты SRTM (скачиваются при сборке для 11 тайлов): без них пешие времена на 1–7 % быстрее, чем на
публичном сервере, с ними совпадают (20 случайных отрезков: длина в пределах 4 %). Админ-границы, часовые пояса и
скорости по умолчанию не строятся: для пешехода они ничего не меняют (проверено), а клипнутая вырезка дала бы
неверные границы.

## Установка и обновление

С ПК (сервер в `$env:ANYQ_SSH`, одно ssh-соединение: на порту 22 у сервера лимит новых подключений):

```powershell
tar -c -C deploy/vps valhalla | ssh $env:ANYQ_SSH 'rm -rf /opt/anyq-valhalla && mkdir -p /opt/anyq-valhalla && tar -x -C /opt/anyq-valhalla --strip-components=1 && bash /opt/anyq-valhalla/update.sh'
```

Либо, если релиз уже выложен `deploy.ps1`: `bash /opt/anyq/current/deploy/vps/valhalla/update.sh` на сервере.
Обновлять стоит после крупных правок OSM в городе (раз в месяц-два достаточно); `--keep-source` пропускает
повторную загрузку Казахстана.

Приложению адрес даёт `anyq.service`: `Environment=WALKS_VALHALLA_URL=http://127.0.0.1:8002/route`. С ним пауза между
запросами к маршрутизатору 0, а не 1,1 с. Сценарии демо (`WALKS_DEMO_PIN=1`) читают пешие отрезки только из
`data/walk_cache.json` и к Valhalla не ходят вообще; свой Valhalla отвечает за запросы вне записи.

## Проверка и эксплуатация

```sh
docker ps --filter name=anyq-valhalla --format '{{.Names}} {{.Status}}'
curl -s http://127.0.0.1:8002/status
curl -s http://127.0.0.1:8002/route -d '{"locations":[{"lat":51.1283,"lon":71.4305},{"lat":51.1325,"lon":71.4033}],"costing":"pedestrian"}'
docker logs --tail 50 anyq-valhalla
docker stats --no-stream anyq-valhalla
```

Остановить: `docker compose -f /opt/anyq-valhalla/docker-compose.yml down`. Приложение при недоступном Valhalla
считает отрезок по прямой (метка «по прямой, оценка») и повторяет попытку через минуту.

Атрибуция: данные маршрутов © участники OpenStreetMap (ODbL). Строка «Valhalla / FOSSGIS» в подписи данных
сейчас названа в `app/i18n.py` и `app/README.md`; для стенда со своим Valhalla она должна называть просто
Valhalla и OpenStreetMap (правка вне этой ветки).
