"""More concepts of the rule parser's lexicon: halal and price, haste, access needs and the way of travel (first: they
close the core order of `walks.lexicon_concepts`), weather words, minors, plain / long-stay wishes, celebrations,
diets, requests the assistant refuses. Data only, appended to `walks.lexicon_concepts.CONCEPTS` (its types and shared
constants are in lexicon_data)."""

from __future__ import annotations

from .lexicon_data import LONG_STAY_BUDGET_MIN, QUICK_BUDGET_MIN, Concept

# fmt: off
EXTRA_CONCEPTS: tuple[Concept, ...] = (
    # a pizza: a meal of its own kind, and the cuisine the ranking looks for in a name or a tag («Додо Пицца», cuisine=pizza)
    Concept(
        "pizza",
        ru=("пицц", "пиццери", "пицу"),
        kk=("пицца",),
        en=("pizza=", "pizzas=", "pizzeria"),
        categories=("restaurant", "cafe", "fast_food"),
        keywords=("пицца", "pizza"),
        negation_excludes=("restaurant", "cafe", "fast_food"),
    ),
    Concept(
        "halal",
        ru=(
            "халяль", "халал", "мусульманск",
        ),
        kk=(
            "халал", "халал тамақ",
        ),
        en=(
            "halal", "muslim friendly", "muslim",
        ),
        categories=("restaurant", "cafe", "fast_food"),
        tier="mood",
        flags=("halal",),
        keywords=("halal", "халяль"),
        negation_excludes=(),
    ),
    Concept(
        "cheap",
        ru=(
            "бесплатн", "недорог", "не дорог", "дешев", "бюджетн", "подешевл", "эконом", "копейк", "задешево", "по карману", "без переплат", "без больших трат", "мало денег",
            "небольшой бюджет", "ограниченный бюджет", "по скромному", "демократичн", "недороже", "сэкономить", "скромный бюджет",
        ),
        kk=(
            "тегін", "арзан", "арзанырақ", "үнемді", "қымбат емес", "тиімді", "арзандау",
        ),
        en=(
            "cheap", "cheaply", "inexpensive", "budget", "affordable", "low cost", "lowcost", "economical", "bargain", "on a budget", "free=", "not expensive", "dirt cheap",
            "thrifty", "pocket friendly", "cheapest", "for free", "no cost", "student budget",
        ),
        flags=("cheap",),
    ),
    Concept(
        "expensive",
        ru=(
            "дорого=", "дорогой ресторан", "дорогие=", "дорогое=", "дороговат", "премиум", "премиальн", "люкс", "роскошн", "фешенебельн", "элитн", "статусн", "пафосн",
            "высокой кухн", "дорогостоящ",
        ),
        kk=(
            "қымбат", "сәнді", "люкс", "премиум", "жоғары деңгей",
        ),
        en=(
            "fine dining", "luxury", "expensive", "upscale", "premium", "high end", "highend", "exclusive", "posh", "fancy", "pricey", "gourmet", "michelin", "swanky", "splurge",
            "treat myself",
        ),
        flags=("expensive",),
        unless=("plain",),
    ),
    Concept(
        "fast",
        ru=(
            "быстр", "срочно", "на скорую", "мигом", "поскорее", "экспресс", "некогда", "нет времени", "мало времени", "в спешке", "спешу", "тороплюсь", "торопл", "на бегу",
            "на ходу", "оперативно", "в темпе", "времени в обрез", "скоренько", "недолго", "побыстрее", "шустро", "пулей",
        ),
        kk=(
            "тез=", "жылдам", "асығыс", "шұғыл", "тезірек", "асығамын", "уақыт аз",
        ),
        en=(
            "fast=", "quick", "quickly", "asap", "in a hurry", "hurry", "rush", "no time", "short on time", "not much time", "express", "speedy", "fastest", "quicker", "swiftly",
            "on the go", "right away",
        ),
        budget_min=QUICK_BUDGET_MIN,
        flags=("fast",),
    ),
    Concept(
        "wheelchair",
        ru=(
            "инвалид", "колясочник", "кресл коляск", "кресла колясок", "маломобильн", "костыл", "ограниченными возможностями",
        ),
        kk=(
            "мүгедек", "мүмкіндігі шектеулі", "мүгедектер арба", "инвалид арба",
        ),
        en=(
            "wheelchair", "mobility", "disabled", "disability", "handicap", "crutches", "walker=",
        ),
        flags=("access",),
    ),
    Concept(
        "step_free",
        ru=(
            "доступная среда", "доступное место для", "доступн для", "безбарьерн", "без барьер", "без ступен", "без порог", "пандус", "пожилым", "пожилых", "пожилой", "пожилая", "пожилого",
            "по лестниц", "без лестниц", "нет лестниц", "лестниц нет", "ступеньк", "тяжело ходить", "трудно ходить", "тяжело подниматься", "плохо хожу", "плохо ходит", "болят ноги", "больные ноги",
        ),
        kk=(
            "бөгетсіз", "пандус", "баспалдақсыз", "баспалдақ жоқ", "баспалдақтарсыз", "кедергісіз", "тосқауылсыз", "пандуспен", "баспалдақ", "жүру қиын", "жүре алмаймын", "аяғым ауырады", "қариялар", "қарт", "егде",
        ),
        en=(
            "accessible", "accessibility", "stepfree", "ramp=", "ramps", "barrier free", "barrierfree", "elderly", "no stairs", "without stairs", "avoid stairs", "stairs are hard", "hard to walk", "difficult to walk", "trouble walking", "bad knees", "mobility issues",
        ),
        flags=("access",),
    ),
    Concept(
        "stroller",
        ru=(
            "коляск", "колясочк", "прогулочная коляска", "с коляс", "детской коляс",
        ),
        kk=(
            "бала арба", "балалар арба", "баласы арба", "арбамен", "арбалы", "арбалос", "арбас", "коляска",
        ),
        en=(
            "stroller", "strollers", "pram", "prams", "buggy", "pushchair", "baby carriage", "baby buggy", "with a stroller",
        ),
        flags=("with_kids", "access"),
        unless=("wheelchair", "wheelchair_on"),
    ),
    Concept(
        "mode_car",
        ru=(
            "на машине", "на авто=", "автомобил", "такси", "за рулем", "на личной машине", "машин", "на тачке", "яндекс го", "индрайв", "парковк", "припаркова", "на колесах",
            "по пробкам",
        ),
        kk=(
            "көлікпен", "машинамен", "такси", "жүргізіп", "тұрақ", "автокөлікпен",
        ),
        en=(
            "car=", "cars=", "taxi", "uber", "drive=", "driving", "by car", "parking", "park the car", "my car", "rental car", "ride share", "rideshare", "by taxi", "drive there",
        ),
        flags=("car",),
    ),
    Concept(
        "mode_transit",
        ru=(
            "автобус", "маршрутк", "общественн транспорт", "трамвай", "lrt=", "лрт=", "легкорельс", "электричк", "городской транспорт", "на транспорте",
        ),
        kk=(
            "автобуспен", "қоғамдық көлік", "автобус", "трамвай", "жеңіл рельсті", "аялдама",
        ),
        en=(
            "bus=", "buses", "transit", "public transport", "public transit", "tram=", "trams", "lrt=", "light rail", "by bus", "bus stop", "city transport", "metro=", "subway",
        ),
        flags=("transit",),
    ),
    Concept(  # Kazakh / national food: the places whose record says so come first (walks.attributes.local_food_signal)
        "local_food",
        ru=(
            "казахск кухн", "казахскую кухню", "казахская кухня", "казахской кухн", "казахск еда", "казахскую еду", "казахская еда", "казахское", "казахских блюд",
            "национальн кухн", "национальную кухню", "национальная кухня", "национальн блюд", "национальные блюда", "местн кухн", "местную кухню", "местная кухня",
            "традиционн кухн", "бешбармак", "бесбармак", "казы=", "куырдак", "баурсак",
        ),
        kk=(
            "қазақ тағам", "қазақша тағам", "қазақ асхана", "ұлттық тағам", "ұлттық ас", "ұлттық асхана", "бешбармақ", "қазы=", "қуырдақ", "бауырсақ", "ет асу",
        ),
        en=(
            "kazakh food", "kazakh cuisine", "kazakh dish", "kazakh dishes", "something kazakh", "kazakh to eat", "kazakh restaurant", "national cuisine", "national dish",
            "local food", "local cuisine", "traditional food", "beshbarmak", "kazy=", "baursak",
        ),
        categories=("restaurant", "cafe"),
        tier="mood",
        flags=("local_food",),
        negation_excludes=(),
    ),
    Concept(  # a trampoline hall, a play centre, a kids' room: indoor entertainment for children, not a playground
        "play_centre",
        ru=(
            "батут", "игровой центр", "игрового центр", "игровом центр", "игровая комнат", "игровой комнат", "игровую комнат", "детская комнат", "детский центр",
            "детский развлекательн", "игровая зона", "игровую зону",
        ),
        kk=(
            "батут", "ойын орталығы", "ойын орталығына", "ойын бөлмесі",
        ),
        en=(
            "trampoline", "play centre", "play center", "indoor play", "soft play", "kids club", "kids' club",
        ),
        categories=("entertainment",),
        flags=("with_kids",),
        negation_excludes=("entertainment",),
    ),
    Concept(
        "drink_emoji",
        en=(
            "🍺", "🍻", "🍷", "🍸", "🍹", "🥂", "🍾",
        ),
        categories=("bar_nightlife",),
        unless=("kids", "kids_specific", "minor", "no_alcohol"),
        negation_excludes=("bar_nightlife",),
    ),
    Concept(
        "minor",
        ru=(
            "подросток", "подростк", "школьник", "школьниц", "старшеклассник", "несовершеннолетн", "тинейджер", "тинэйджер", "малолетн", "ученик", "десятилетн",
            "одиннадцатилетн", "двенадцатилетн", "тринадцатилетн", "четырнадцатилетн", "пятнадцатилетн", "шестнадцатилетн", "семнадцатилетн", "семилетн", "восьмилетн",
            "девятилетн", "шестилетн", "пятилетн", "четырехлетн", "трехлетн", "двухлетн",
        ),
        kk=(
            "жасөспірім", "оқушы", "кәмелетке толмаған", "кәмелетке", "мектеп оқушы",
        ),
        en=(
            "teen", "teens=", "teenage", "teenager", "teenagers", "underage", "under age", "minor=", "minors=", "highschool", "high schooler", "schoolkid", "school kid",
            "schoolchild", "schoolchildren", "pupil", "pupils", "middle school", "juvenile",
        ),
        tier="mood",
        flags=("minor",),
        negation_excludes=(),
    ),
    Concept(
        "celebrate",
        ru=(
            "отпраздновать", "праздновать", "празднуем", "празднован", "отмечаем", "отметить день", "отметить праздник", "день рожден", "дня рожден", "дню рожден", "дне рожден",
            "днюх", "юбилей", "новоселье", "выпускной", "наурыз",
        ),
        kk=(
            "тойла", "тойға", "мереке", "мерей", "туған күн", "наурыз",
        ),
        en=(
            "celebrate", "celebrating", "celebration", "birthday", "bday", "nauryz",
        ),
        categories=("restaurant", "entertainment"),
        tier="mood",
        negation_excludes=(),
    ),
    Concept(
        "wx_cold",
        ru=(
            "холодно", "холод=", "холода=", "мороз", "морозн", "стужа", "замерз", "продрог", "околел", "метел", "буран", "снегопад", "гололед", "снег=", "снегу=",
        ),
        kk=(
            "суық", "аяз", "боран", "үсіп", "қар=", "қар жауып", "салқын",
        ),
        en=(
            "cold=", "freezing", "frost", "frosty", "blizzard", "snowstorm", "snow", "snowing", "chilly",
        ),
        tier="mood",
        flags=("wx_cold",),
    ),
    Concept(
        "wx_rain",
        ru=(
            "дожд", "ливень", "ливня", "ливне", "ливни", "гроза", "слякот", "морось", "непогод", "промок", "мокро",
        ),
        kk=(
            "жаңбыр", "жауын", "нөсер",
        ),
        en=(
            "rain", "raining", "rainy", "drizzle", "downpour", "thunderstorm", "wet weather", "bad weather",
        ),
        tier="mood",
        flags=("wx_rain",),
    ),
    Concept(
        "wx_heat",
        ru=(
            "жара=", "жару=", "жаре=", "жары=", "жарко", "духота", "душно", "зной", "знойн", "пекло", "изнуряющ",
        ),
        kk=(
            "ыстық", "аптап", "ыссы", "ысып", "көлеңке",
        ),
        en=(
            "heat=", "heatwave", "heat wave", "too hot", "scorching", "sweltering", "hot weather", "boiling",
        ),
        tier="mood",
        flags=("wx_heat",),
    ),
    Concept(
        "photo_spot",
        ru=(
            "фотогенич", "красивые фото", "красивых фото", "красивое фото", "красивого фото", "красивых кадр", "фотоспот", "фото спот", "фотолокаци", "для фото", "на фото",
            "сфотографироваться", "сфоткаться", "пофотографировать", "поснимать", "сделать фото", "сделать красивые фото", "фотосесси", "инстаграм", "для инсты", "фотозон",
        ),
        kk=(
            "суретке түсу", "суретке түс", "суретке түсетін", "сурет түсіру", "суретке түсіргім", "фотоға", "фотосессия", "фотоспот", "әдемі сурет", "әдемі фото", "инстаграм",
        ),
        en=(
            "photo spot", "photospot", "photo op", "photogenic", "good photos", "nice photos", "beautiful photos", "great photos", "take photos", "take pictures", "take a photo", "for photos",
            "for pictures", "instagrammable", "instagram", "photoshoot", "photo shoot", "selfie spot",
        ),
        categories=("viewpoint", "attraction_landmark", "park_garden"),
        tier="mood",
        keywords=("фото", "photo"),
        negation_excludes=(),
    ),
    Concept(
        "wx_smog",
        ru=(
            "смог=", "смоге=", "смогом=", "смога=", "дымка=", "загрязнен", "грязный воздух", "грязном воздух", "плохой воздух", "плохом воздух", "нечем дышать", "pm25", "качество воздуха",
        ),
        kk=(
            "смог", "түтін", "ауа ластан", "ауа сапасы", "ластанған ауа",
        ),
        en=(
            "smog", "air pollution", "polluted", "bad air", "poor air", "haze", "smoky", "pm25", "aqi=", "air quality",
        ),
        tier="mood",
        flags=("wx_smog",),
    ),
    Concept(
        "plain",
        ru=(
            "без изыск", "простенько", "попроще", "ничего особенного", "ничего лишнего", "без пафоса", "без излишеств", "без затей", "ничего fancy", "ничего дорог", "ничего шикарн",
            "не пафосн", "ничего такого дорог",
        ),
        kk=(
            "қарапайым", "қарапайымырақ",
        ),
        en=(
            "nothing fancy", "nothing special", "nothing expensive", "no frills", "nofrills", "keep it simple", "nothing too fancy", "simple place",
        ),
        flags=("cheap",),
    ),
    Concept(
        "long_stay",
        ru=(
            "надолго", "на весь день", "на полдня", "не спеша", "неспешно", "без спешки",
        ),
        kk=(
            "ұзақ", "асықпай", "күні бойы",
        ),
        en=(
            "for a long time", "all day", "no rush", "unhurried", "leisurely", "take my time",
        ),
        budget_min=LONG_STAY_BUDGET_MIN,
    ),
    Concept(
        "wheelchair_on",
        ru=(
            "на коляск",
        ),
        flags=("access",),
        unless=("kids", "kids_specific"),
    ),
    Concept(
        "not_tourist",
        ru=(
            "не для турист", "туристам не", "не туристам", "не турист", "без турист", "туристов нет", "где нет турист",
        ),
        kk=(
            "туристерсіз", "туристер жоқ",
        ),
        en=(
            "not touristy", "not for tourists", "no tourists", "without tourists", "away from tourists", "non touristy",
        ),
        tier="mood",
    ),
    # Diets (Intent.diets). A diet request is about the plate: a bar is never added for it by a model.
    Concept(
        "diet_vegetarian",
        ru=(
            "вегетариан", "постное", "постную", "без мяса", "растительн",
        ),
        kk=(
            "вегетариан", "ет жемеймін",
        ),
        en=(
            "vegetarian", "veggie", "meat free",
        ),
        categories=("restaurant", "cafe"),
        tier="mood",
        flags=("diet_vegetarian",),
        keywords=("вегетариан", "vegetarian"),
        forbids=("bar_nightlife",),
        negation_excludes=(),
    ),
    Concept(
        "diet_vegan",
        ru=(
            "веган", "растительная кухня",
        ),
        kk=(
            "веган",
        ),
        en=(
            "vegan", "plant based",
        ),
        categories=("restaurant", "cafe"),
        tier="mood",
        flags=("diet_vegan",),
        keywords=("веган", "vegan"),
        forbids=("bar_nightlife",),
        negation_excludes=(),
    ),
    Concept(
        "diet_gluten_free",
        ru=(
            "глютен", "безглютен", "без глютен", "целиак", "глютенфри",
        ),
        kk=(
            "глютен", "целиакия",
        ),
        en=(
            "gluten", "glutenfree", "celiac", "coeliac",
        ),
        categories=("restaurant", "cafe"),
        tier="mood",
        flags=("diet_gluten_free",),
        keywords=("глютен", "gluten"),
        forbids=("bar_nightlife",),
        negation_excludes=(),
    ),
    Concept(
        "diet_kosher",
        ru=(
            "кошер", "кашрут",
        ),
        kk=(
            "кошер",
        ),
        en=(
            "kosher", "kashrut",
        ),
        categories=("restaurant", "cafe"),
        tier="mood",
        flags=("diet_kosher",),
        keywords=("кошер", "kosher"),
        forbids=("bar_nightlife",),
        negation_excludes=(),
    ),
    # A shift worker's «after my shift» is not «work with a laptop»
    Concept(
        "night_shift",
        ru=(
            "ночн смен", "в смену", "после смен", "перед смен", "смена закончил", "смену закончил", "на смене",
        ),
        kk=(
            "түнгі ауысым", "ауысымнан", "ауысым",
        ),
        en=(
            "night shift", "after my shift", "after shift", "my shift", "end of my shift", "shift ended", "shift is over",
        ),
        tier="mood",
    ),
    # «что посмотреть / what should I see»: the person names the sights themselves (a wish, not the tourist mood that
    # pads them with a café): landmarks, viewpoints and museums, within the budget
    Concept(
        "sights_wish",
        ru=(
            "что посмотреть", "что стоит посмотреть", "что интересного посмотреть", "что можно посмотреть",
            "что тут посмотреть", "достопримечательност",
        ),
        kk=(
            "не көруге болады", "көруге тұрарлық", "көрікті жерлер",
        ),
        en=(
            "what should i see", "what to see", "what is worth seeing", "whats worth seeing", "worth seeing",
            "things to see", "what can i see", "main sights",
        ),
        categories=("attraction_landmark", "viewpoint", "museum_gallery"),
        tier="kind",
    ),
    # A toilet: the kind `public_toilet` when no other kind is named («где туалет»); next to one («кафе с туалетом») a
    # keyword the dataset holds no facts about, so that the answer can say so
    Concept(
        "wish_toilet",
        ru=(
            "туалет", "уборн", "санузел",
        ),
        kk=(
            "дәретхана", "әжетхана",
        ),
        en=(
            "toilet", "restroom", "bathroom", "washroom", "wc=",
        ),
        tier="mood",
        categories=("public_toilet",),
        keywords=("туалет",),
    ),
    Concept(
        "wish_baby_changing",
        ru=(
            "пеленальн", "пеленат", "сменить подгузник", "комната матери", "комнату матери", "мать и дитя",
        ),
        kk=(
            "жаялық ауыстыр",
        ),
        en=(
            "changing table", "baby changing", "diaper", "nursing room", "mother and baby",
        ),
        tier="mood",
        keywords=("пеленальник",),
    ),
    Concept(
        "wish_kids_menu",
        ru=(
            "детское меню", "детского меню", "детским меню", "детском меню",
        ),
        kk=(
            "балалар мәзірі",
        ),
        en=(
            "kids menu", "childrens menu", "child menu", "kid menu",
        ),
        tier="mood",
        keywords=("детское меню",),
    ),
    Concept(
        "bbq",
        ru=(
            "шашлык", "мангал", "барбекю", "гриль=", "на углях",
        ),
        kk=(
            "шашлык", "кәуап",
        ),
        en=(
            "bbq", "barbecue", "grill=", "grilled", "kebab",
        ),
        categories=("restaurant",),
        keywords=("шашлык", "гриль", "bbq", "grill"),
        negation_excludes=("restaurant",),
    ),
    # Requests the assistant never helps with (walks.intent: Intent.refusal, no places are offered). A museum of
    # such things («музей оружия») is a museum.
    Concept(
        "refuse_drugs",
        ru=(
            "наркот", "наркоман", "кокаин", "героин", "мефедрон", "амфетамин", "экстази=", "лсд=", "марихуан", "гашиш", "спайс", "закладк", "травку=", "траву=", "курнуть",
            "обкуриться", "накуриться", "запрещенн вещест", "вещества=", "барыг",
        ),
        kk=(
            "есірткі", "кокаин", "героин", "марихуана", "гашиш",
        ),
        en=(
            "cocaine", "heroin", "meth=", "methamphetamine", "weed=", "marijuana", "cannabis", "mdma", "ecstasy=", "lsd=", "fentanyl", "hashish", "ketamine", "narcotic",
            "drugs=", "drug dealer", "get high", "ganja", "opium",
        ),
        tier="mood",
        unless=("museum",),
        flags=("refuse_drugs",),
    ),
    Concept(
        "refuse_sex",
        ru=(
            "проститут", "шлюх", "интим услуг", "интим салон", "эскорт", "секс услуг", "секс за деньги", "купить секс", "индивидуалк", "путан", "девочки по вызову",
            "девочек по вызову", "девушки по вызову", "снять девочк", "снять девушк", "эротическ массаж", "массаж с окончан", "массажк с окончан", "массаж с хеппи энд", "массаж с счастлив концовк", "бордель", "публичн дом", "жрица любви",
        ),
        kk=(
            "жезөкше", "интим қызмет",
        ),
        en=(
            "prostitut", "escort=", "escorts=", "hooker", "hookers=", "brothel", "sex worker", "sex services", "call girl", "callgirl", "paid sex", "erotic massage",
            "happy ending", "massage with ending",
        ),
        tier="mood",
        unless=("museum",),
        flags=("refuse_sex",),
    ),
    Concept(
        "refuse_weapons",
        ru=(
            "пистолет", "револьвер", "калашников", "огнестрел", "боеприпас", "травматик", "взрывчат", "оружие=", "оружия=", "оружию=", "оружием=", "оружейн магазин",
            "купить ствол", "достать ствол", "купить ружь", "купить патрон",
        ),
        kk=(
            "тапанша", "мылтық сатып", "қару сатып",
        ),
        en=(
            "gun=", "guns=", "handgun", "firearm", "firearms=", "pistol=", "rifle=", "weapon=", "weapons=", "ammo=", "ammunition", "explosives=", "gun shop", "gun store",
        ),
        tier="mood",
        unless=("museum",),
        flags=("refuse_weapons",),
    ),
    Concept(
        # an explicit state-service request (collect/gov: ЦОН of Astana, category `other`, tag gov_service=cson): the
        # only concept that names `other`; retrieve keeps `other` to those records
        "state_service",
        ru=(
            "цон=", "цона", "цоне", "цону", "цоны", "цоном", "цонов", "цонах", "центр обслуживания населения", "центра обслуживания населения",
            "центре обслуживания населения", "центры обслуживания населения", "госуслуг", "государственн услуг", "справк получ", "получ справк", "справк оформ",
        ),
        kk=(
            "хқко=", "хқкоға", "хқкода", "хқкодан", "хқконың", "халыққа қызмет көрсету орталығы", "халыққа қызмет көрсету орталығына", "мемлекеттік қызмет",
        ),
        en=(
            "tson=", "tsona", "public service cent", "public services cent", "government service", "gov service", "state service",
        ),
        categories=("other",),
        negation_excludes=("other",),
    ),
    # «something nice to see»: the sights themselves, not the cafe the tourist mood also lists
    Concept(
        "see_something",
        ru=(
            "что нибудь посмотреть", "что нибудь красивое посмотреть", "что нибудь интересное посмотреть", "на что посмотреть", "на что поглядеть", "что нибудь красивое",
        ),
        kk=(
            "көруге тұрарлық", "көретін бір нәрсе", "әдемі жер көргім", "көргім келеді",
        ),
        en=(
            "something nice to see", "something to see", "something beautiful to see", "somewhere nice to see", "anything to see", "something pretty to see", "something interesting to see",
        ),
        categories=("attraction_landmark", "viewpoint", "park_garden"),
        tier="activity",
        negation_excludes=(),
    ),
)
# fmt: on
