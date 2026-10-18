# Дополнительная польза ИИ при маппинге категорий поверх словаря

git `3c89ac3+uncommitted`, 17.10.2026 04:11, наборы: holdout, abstain, main, пауза между вызовами 6 с, режим `--public-only`: только звенья Google (без частного профиля), кэш ответов выключен, цепочка `gemini:gemini-2.5-flash-lite → gemini:gemini-3.5-flash-lite → gemini:gemma-4-26b-a4b-it`.

Словарь (правила) находит категории по ключевым словам; ИИ только добавляет к ним то, что словарь не распознал (union категорий, OR флагов). Без поиска и без генерации: только цепочка разбора намерения. Пробел правил — что-то из `expected` кейса, чего нет в их намерении (нет допустимой категории / есть запрещённая / не взведён флаг «дети», «розетка», «доступность»).

- Опрошено запросов: 69; измерено (живой ответ звена Google): **69**; исключено из итогов (кэш / частный профиль): 0; не измерено: 0; не опрошено после остановки: 0.
- Отвечали звенья: gemini:gemini-2.5-flash-lite, gemini:gemini-3.5-flash-lite.
- У правил есть пробел в 4 измеренных запросах; ИИ закрыл полностью: **1**, частично: 0; добавил новый пробел: 2.
- Измерено по наборам: main 41, holdout 20, abstain 8.
- Только holdout: пробел правил в 4, ИИ закрыл полностью **1**.

| набор | кейс | запрос | категории правил | добавил ИИ | звено | итог |
|---|---|---|---|---|---|---|
| holdout | `h01-akorda-wk-beshbarmak` | Хочу поесть бешбармак | restaurant | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h02-nurly-fri-train` | У меня час до поезда, где быстро перекусить рядом | fast_food, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h03-keruen-sat-date` | куда пойти с девушкой вечером | restaurant, cafe, viewpoint, culture_theatre_cinema | bar_nightlife, attraction_landmark, +night | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h04-lovers-sun-stroller` | гулять с коляской и без алкоголя | park_garden, attraction_landmark, viewpoint | kids_playground, +with_kids, +quiet | gemini:gemini-3.5-flash-lite | ✅ ИИ закрыл: with_kids |
| holdout | `h05-arena-tue-rain` | где переждать дождь | cafe, museum_gallery, mall, culture_theatre_cinema, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h06-kenesary-sat-first-time` | я первый раз в Астане, хочу погулять часа два, что посмотре… | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h07-hazret-holiday-laptop` | where can I work with a laptop | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h08-nu-wed-kk-kids` | баламен қайда баруға болады | kids_playground, museum_gallery | entertainment, park_garden | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h09-botsad-thu-typos` | кде паесть дешево и быстра | restaurant, cafe, fast_food | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h10-opera-fri-night-out` | хочу выпить и потанцевать | bar_nightlife | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h11-akorda-holiday-cold-tea` | где погреться и выпить горячего чая | cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h12-keruen-sun-smog-air` | хочу пройтись по свежему воздуху | park_garden, attraction_landmark, viewpoint | +quiet | gemini:gemini-3.5-flash-lite | ❌ не помог: categories |
| holdout | `h13-nurly-tue-late-hungry` | куда пойти ночью, я только приехал и голодный | restaurant, cafe, fast_food | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h14-kenesary-wed-dog` | выгулять собаку | park_garden | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h15-arena-sat-football` | где можно поиграть в футбол или побегать | sport, park_garden | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h16-lovers-tue-sunset` | где красиво смотреть на закат | viewpoint | attraction_landmark | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h17-saparzhai-tue-coffee` | Где здесь можно кофе выпить | cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h18-nu-tue-en-read` | quiet place to read, open late | coworking_library, cafe, bar_nightlife, entertainment, culture_theatre_cinema, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | ❌ не помог: categories |
| holdout | `h19-hazret-sun-kk-museum` | Музей немесе көрмеге барғым келеді | museum_gallery | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| holdout | `h20-keruen-newyear-cold` | куда сходить на Новый год, что открыто | — | entertainment, attraction_landmark, bar_nightlife, +night | gemini:gemini-3.5-flash-lite | ❌ не помог: categories |
| abstain | `a01-leftbank-3am-museum` | Хочу в музей | museum_gallery | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a02-airport-lrt-2330-quiet-socket` | Тихое кафе с розеткой, поработать | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a03-industrial-museum` | Хочу в музей | museum_gallery | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a04-leftbank-pool` | Бассейн рядом | sport | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a05-nw-edge-cafe-socket` | Кофе и розетка, поработать | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a06-se-edge-stroller-museum` | Хочу в музей с коляской | museum_gallery | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a07-nw-edge-museum` | Хочу в музей | museum_gallery | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| abstain | `a08-leftbank-frost-playground` | Прогулка с ребёнком, площадка | kids_playground | park_garden | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `tz1` | Рядом с Mega Silk Way, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | mall | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `tz2` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `tz3` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `tz4` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `tz5` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `expo-wk14-normal-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `expo-wk14-cold-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-2.5-flash-lite | у правил нет пробела |
| main | `expo-eve-normal-walk` | Рядом с EXPO, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `expo-night-normal-night` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `expo-hol-smog-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `expo-wk14-normal-mobility` | Мне нужно доступное место для коляски: кофе и посидеть, нед… | cafe | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `msw-eve-cold-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `msw-wk14-smog-walk` | Рядом с Mega Silk Way, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `msw-night-cold-night` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | other | gemini:gemini-3.5-flash-lite | у правил нет пробела; ИИ добавил лишнее: categories |
| main | `msw-hol-normal-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `msw-eve-normal-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `msw-wk14-cold-mobility` | Мне нужно доступное место для коляски: кофе и посидеть, нед… | cafe | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-eve-normal-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-hol-normal-walk` | Рядом с Байтерек, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-wk14-cold-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-eve-smog-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-night-smog-night` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `baiterek-wk14-normal-mobility` | Мне нужно доступное место для коляски: кофе и посидеть, нед… | cafe | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `khan-eve-normal-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `khan-hol-cold-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `khan-eve-cold-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `khan-wk14-smog-walk` | Рядом с Хан Шатыр, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | mall | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `khan-night-normal-night` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | other | gemini:gemini-3.5-flash-lite | у правил нет пробела; ИИ добавил лишнее: categories |
| main | `khan-eve-smog-mobility` | Мне нужно доступное место для коляски: кофе и посидеть, нед… | cafe | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `lrt-night-cold-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `lrt-hol-normal-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `lrt-eve-smog-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `lrt-wk14-cold-walk` | Рядом с LRT Аэропорт, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `lrt-eve-normal-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-wk14-normal-walk` | Рядом с домом, прогулка 30–60 мин | park_garden, attraction_landmark, viewpoint | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-eve-normal-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-wk14-normal-quiet` | Тихое место с кофе и розеткой | cafe, coworking_library | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-night-normal-night` | Необычная ночная активность | attraction_landmark, museum_gallery, viewpoint, entertainment, bar_nightlife, culture_theatre_cinema, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-hol-smog-mobility` | Мне нужно доступное место для коляски: кофе и посидеть, нед… | cafe | +with_kids | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-eve-cold-tourist` | Турист, 2 часа до вылета | attraction_landmark, viewpoint, museum_gallery, park_garden, cafe | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
| main | `left-wk14-smog-kids` | С ребёнком: площадка или интерактивный музей | museum_gallery, kids_playground | — | gemini:gemini-3.5-flash-lite | у правил нет пробела |
