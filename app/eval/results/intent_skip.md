# Уверенность правил: модель разбора не спрашивают

`python -m eval.intent_skip`: живая модель разбора (без кэша) на запросах наборов main, holdout, holdout2,
abstain и типичных первых сообщениях. «Тот же разбор» — проверка walks.confident.same_reading, по которой
конвейер оставляет ответ, подготовленный по разбору правил. «Не измерено»: модель не ответила за 3 попытки.

- Правила уверены: 21 разных запросов; тот же разбор у модели: 21, изменён: 0, не измерено: 0.
- Правила не уверены: 72; модель изменила разбор в 38 из 72 измеренных.

| Набор | Запрос | Правила уверены | Разбор модели |
|---|---|---|---|
| abstain | Бассейн рядом | да | тот же |
| abstain | Хочу в музей | да | тот же |
| holdout | Где здесь можно кофе выпить | да | тот же |
| typical | coffee nearby | да | тот же |
| typical | museum nearby | да | тот же |
| typical | where is a pharmacy | да | тот же |
| typical | аптека рядом | да | тот же |
| typical | банкомат рядом | да | тот же |
| typical | бар рядом | да | тот же |
| typical | дәріхана қайда | да | тот же |
| typical | жақын жерде кафе | да | тот же |
| typical | кинотеатр рядом | да | тот же |
| typical | кофе рядом | да | тот же |
| typical | кофе ішкім келеді | да | тот же |
| typical | музей | да | тот же |
| typical | мұражай | да | тот же |
| typical | продуктовый магазин рядом | да | тот же |
| typical | ресторан рядом | да | тот же |
| typical | супермаркет рядом | да | тот же |
| typical | торговый центр | да | тот же |
| typical | хочу в парк | да | тот же |
| abstain | Кофе и розетка, поработать | нет | тот же |
| abstain | Прогулка с ребёнком, площадка | нет | изменён: categories, free_text_keywords |
| abstain | Тихое кафе с розеткой, поработать | нет | тот же |
| abstain | Хочу в музей с коляской | нет | тот же |
| holdout | quiet place to read, open late | нет | тот же |
| holdout | where can I work with a laptop | нет | тот же |
| holdout | Музей немесе көрмеге барғым келеді | нет | тот же |
| holdout | У меня час до поезда, где быстро перекусить рядом | нет | изменён: categories, free_text_keywords |
| holdout | Хочу поесть бешбармак | нет | тот же |
| holdout | выгулять собаку | нет | тот же |
| holdout | где красиво смотреть на закат | нет | тот же |
| holdout | где можно поиграть в футбол или побегать | нет | тот же |
| holdout | где переждать дождь | нет | изменён: free_text_keywords |
| holdout | где погреться и выпить горячего чая | нет | изменён: free_text_keywords |
| holdout | гулять с коляской и без алкоголя | нет | тот же |
| holdout | кде паесть дешево и быстра | нет | тот же |
| holdout | куда пойти ночью, я только приехал и голодный | нет | изменён: free_text_keywords |
| holdout | куда пойти с девушкой вечером | нет | изменён: categories, free_text_keywords |
| holdout | хочу выпить и потанцевать | нет | изменён: categories, free_text_keywords |
| holdout | хочу пройтись по свежему воздуху | нет | изменён: free_text_keywords |
| holdout | я первый раз в Астане, хочу погулять часа два, что посмотреть | нет | изменён: categories, free_text_keywords |
| holdout2 | Date tonight but no bars please, somewhere calm and pretty near the National Museum | нет | изменён: categories, free_text_keywords |
| holdout2 | I am staying near the botanical garden, where can I take a nice walk and grab breakfast for cheap? | нет | изменён: categories, free_text_keywords |
| holdout2 | It is minus 22 outside and my kid is bored, where can we go somewhere warm and indoor nearby? | нет | изменён: categories, free_text_keywords |
| holdout2 | Need a quiet place to work on my laptop for about three hours tonight near Momyshuly park, ideally with a socket | нет | изменён: categories, free_text_keywords |
| holdout2 | halal dinner for 4 people nearby, preferably not fast food | нет | тот же |
| holdout2 | Ауа лас болып тұр, ноутбукпен үш сағат жұмыс істеуге қолайлы кафе керек, жақын жерде | нет | тот же |
| holdout2 | Бесінбі күні кешке жақсы кешкі ас ішейтін жер керек, Көктал маңында тұрамын | нет | тот же |
| holdout2 | В Астане дикая ветрища, где спрятаться от ветра и пообедать недалеко от бульвара | нет | изменён: categories, free_text_keywords |
| holdout2 | Воздух ужасный, куда пойти вечером в помещении рядом, не сидеть в общаге | нет | изменён: categories, free_text_keywords |
| holdout2 | Жаңбыр жауып тұр, Ұлттық музей маңында қайда бірер сағат отырып күтемін? | нет | изменён: free_text_keywords |
| holdout2 | Живём в частном секторе на Коктале, куда выбраться с семьёй в субботу, не очень далеко | нет | изменён: categories, free_text_keywords |
| holdout2 | Жұлдызаралық уақытта арзан әрі дәмді тамақтанатын жер қайда, университет маңында? | нет | изменён: categories, free_text_keywords |
| holdout2 | Куда сходить с ребёнком в субботу днём, чтобы и погулять, и поесть рядом | нет | изменён: categories, free_text_keywords |
| holdout2 | Мороз −22, где погреться и поужинать рядом, только не далеко идти | нет | изменён: categories, free_text_keywords |
| holdout2 | Пирамида маңында екі сағатта не көруге болады, жаяу жүріп | нет | изменён: categories, free_text_keywords |
| holdout2 | Пойызға дейін бір сағат уақытым бар, вокзал маңында тез тамақтанатын жер қайда? | нет | тот же |
| holdout2 | Рано утром на морозе жду поезд, где можно погреться с кофе недалеко от вокзала | нет | тот же |
| holdout2 | Сегодня праздник, выходной. Куда сходить днём недалеко, погулять и поесть | нет | изменён: categories, free_text_keywords |
| holdout2 | У меня час до пар, куда можно сходить рядом с мечетью, прогуляться | нет | тот же |
| holdout2 | балалармен демалыс күні неде өткіземіз, жақын жерде | нет | изменён: categories, free_text_keywords |
| holdout2 | гуляю с коляской, нужно без лестниц и с пандусами, куда пойти рядом | нет | изменён: categories, free_text_keywords |
| holdout2 | кде паесть дешево и быстра рядом с Астана Молл | нет | тот же |
| holdout2 | что вообще открыто в 11 вечера воскресенья рядом, поесть или погулять | нет | изменён: categories, free_text_keywords |
| holdout2 | чё открито в 11 рядом с Азией парком, жрать хоцца ченить | нет | изменён: free_text_keywords |
| main | Где прогуляться можно щас? | нет | изменён: categories, free_text_keywords |
| main | Мне нужно доступное место для коляски: кофе и посидеть, недалеко | нет | тот же |
| main | Необычная ночная активность | нет | изменён: free_text_keywords |
| main | Рядом с EXPO, прогулка 30–60 мин | нет | тот же |
| main | Рядом с LRT Аэропорт, прогулка 30–60 мин | нет | тот же |
| main | Рядом с Mega Silk Way, прогулка 30–60 мин | нет | тот же |
| main | Рядом с Байтерек, прогулка 30–60 мин | нет | тот же |
| main | Рядом с Хан Шатыр, прогулка 30–60 мин | нет | тот же |
| main | Рядом с домом, прогулка 30–60 мин | нет | тот же |
| main | С ребёнком: площадка или интерактивный музей | нет | тот же |
| main | Тихое место с кофе и розеткой | нет | тот же |
| main | Турист, 2 часа до вылета | нет | тот же |
| main | Я именно погулять хочу | нет | тот же |
| main | хочу погулять | нет | изменён: categories |
| typical | a quiet place to read | нет | тот же |
| typical | what should i see | нет | изменён: categories |
| typical | аптека и банкомат | нет | тот же |
| typical | баламен қайда баруға болады | нет | изменён: categories |
| typical | где погулять с собакой | нет | изменён: free_text_keywords |
| typical | где поужинать | нет | изменён: free_text_keywords |
| typical | где поужинать недорого | нет | изменён: categories, free_text_keywords |
| typical | кофе с wifi поработать | нет | тот же |
| typical | куда пойти вечером с друзьями | нет | изменён: categories, free_text_keywords |
| typical | куда сходить с ребёнком | нет | изменён: categories |
| typical | погулять хочу просто | нет | изменён: categories |
| typical | хочу поесть | нет | тот же |
| typical | что посмотреть | нет | изменён: categories |
