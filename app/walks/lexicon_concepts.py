"""The concepts of the rule parser's lexicon (data only; the types and the shared constants are in lexicon_data)."""

from __future__ import annotations

from .lexicon_data import (
    BETWEEN_CLASSES_BUDGET_MIN,
    LONG_VISIT_BUDGET_MIN,
    QUICK_BUDGET_MIN,
    WAITING_BUDGET_MIN,
    Concept,
)
from .lexicon_extra import EXTRA_CONCEPTS

# fmt: off
_CORE_CONCEPTS: tuple[Concept, ...] = (
    Concept(
        "coffee",
        ru=(
            "кофе", "кофейн", "кофеин", "капучин", "латте", "эспрессо", "американо", "раф=", "флэт уайт", "чай=", "чая", "чаю", "чаем", "чаек", "чаепит", "кафе", "матча=",
            "круассан", "десерт", "пирожн", "выпечк", "булочн", "пекарн", "сладк", "мороженое", "мороженн", "чашечк",
        ),
        kk=(
            "кофе", "кафе", "шай=", "шайхана", "тәтті", "кофехана", "тәттілер",
        ),
        en=(
            "coffee", "cafe", "latte", "espresso", "cappuccino", "americano", "flat white", "tea=", "teas", "matcha", "croissant", "pastry", "pastries", "dessert", "bakery",
            "cuppa", "sweets",
        ),
        categories=("cafe",),
        negation_excludes=("cafe",),
    ),
    Concept(
        "eat_full",
        ru=(
            "ресторан", "пообедать", "поужинать", "обед", "ужин", "ужинать", "завтрак", "позавтракать", "бранч", "трапез", "плотно поесть", "сытно", "нормально поесть",
            "полноценн", "кухн", "стейк", "суши", "бешбармак", "плов=", "лагман", "мант=", "шашлык", "застолье", "банкет",
        ),
        kk=(
            "мейрамхана", "тамақ", "тағам", "түскі ас", "кешкі ас", "таңғы ас", "тамақтан", "ас ішу", "ас мәзірі",
        ),
        en=(
            "restaurant", "dinner", "lunch", "brunch", "breakfast", "steak", "sushi", "supper", "proper meal", "full meal", "nice meal", "dining", "dine", "diner", "bistro",
            "trattoria",
        ),
        categories=("restaurant",),
        negation_excludes=("restaurant",),
    ),
    Concept(
        "eat_quick",
        ru=(
            "перекус", "закуск", "быстро поесть", "фастфуд", "бургер", "шаурм", "шаверм", "хотдог", "хот дог", "донер", "картошк фри", "нагетс", "стритфуд", "столов",
            "на скорую руку", "перехватить", "заморить червячка", "чебурек", "самса=", "самсу", "лепешк", "кебаб", "вок=", "подкрепиться", "сэндвич", "бутерброд", "шавуху",
        ),
        kk=(
            "жеңіл тамақ", "шаурма", "бургер", "фастфуд", "самса", "тез тамақ", "ауыз тию",
        ),
        en=(
            "snack", "quick bite", "bite to eat", "grab a bite", "fastfood", "burger", "takeaway", "takeout", "streetfood", "hot dog", "kebab", "shawarma", "sandwich",
            "something quick", "pizza slice", "bite=",
        ),
        categories=("fast_food", "cafe"),
        negation_excludes=("fast_food",),
    ),
    Concept(
        "eat_generic",
        ru=(
            "поесть", "покушать", "кушать", "пожрать", "пожевать", "голод", "проголодал", "хочу есть", "хочется есть", "хочу кушать", "хотим есть", "умираю с голоду", "еда=", "хочешь есть", "хочет есть", "хочется поесть", "хочется кушать", "хотим поесть", "хочу поесть",
            "еды=", "еду=", "едой=", "жрать", "жрат", "жрач", "хавать", "хавк", "хавч", "похав", "хоцца", "накормить", "накорм", "питани", "где можно поесть", "вкусно поесть", "пицц", "пиццер",
        ),
        kk=(
            "қарным ашты", "ашықтым", "қарным ашып", "тамақ ішкім", "жегім келеді", "жеу=", "тамақтанғым", "тамақтанайық",
        ),
        en=(
            "eat=", "eating", "munchies", "peckish", "chow", "need food", "get some food", "food", "foods", "hungry", "hungr", "starving", "starv", "meal", "something to eat", "place to eat", "feed=", "pizza", "grab food",
        ),
        categories=("restaurant", "cafe", "fast_food"),
        unless=("eat_full", "eat_quick"),
        negation_excludes=(),
    ),
    Concept(
        "drink_alcohol",
        ru=(
            "бар=", "бара=", "баре=", "бары=", "баров=", "бару=", "баром=", "пиво", "пива=", "пиве=", "пивн", "пивк", "вино=", "вина=", "винн", "коктейл", "виски", "водк",
            "коньяк", "ром=", "джин=", "текил", "шоты", "алкогол", "спиртн", "выпивк", "бокал", "паб=", "пабе=", "паба=", "крафтов", "кальян", "лаунж", "пропустить по", "настойк",
            "сидр", "шампанск", "ночная жизнь", "ночной клуб",
        ),
        kk=(
            "сыра", "шарап", "арақ", "ішімдік", "алкоголь", "коктейль", "кальян",
        ),
        en=(
            "bar=", "bars=", "pub=", "pubs=", "beer", "wine", "cocktail", "whisky", "whiskey", "vodka", "alcohol", "booze", "lounge", "hookah", "shisha", "brewery", "taproom",
            "happy hour", "nightlife", "tavern", "pint=", "pints=", "liquor", "champagne", "cider",
        ),
        categories=("bar_nightlife",),
        negation_excludes=("bar_nightlife",),
    ),
    Concept(
        "drink_generic",
        ru=(
            "выпить", "выпьем", "выпивать", "дринк", "по бокал", "пропустим", "накатить",
            "бухат", "бухнут", "бухну", "бухло", "бухал", "побух",
        ),
        kk=(
            "ішейік", "ішкім", "ішуге",
        ),
        en=(
            "drink=", "drinks=", "drinking", "have a drink", "grab a drink",
        ),
        categories=("bar_nightlife",),
        unless=("coffee", "no_alcohol"),
        negation_excludes=("bar_nightlife",),
    ),
    Concept(
        "dance_party",
        ru=(
            "танц", "потанц", "тусовк", "тусить", "потусить", "вечеринк", "дискотек", "клуб", "пати", "оторваться", "зажечь", "караоке", "диджей", "рейв", "дискач", "повеселиться",
            "гулять до утра", "развеяться",
        ),
        kk=(
            "би=", "билеу", "билегім", "клуб", "дискотека", "көңіл көтеру",
        ),
        en=(
            "dance", "dancing", "party", "partying", "club=", "clubs=", "clubbing", "nightclub", "disco", "rave", "karaoke", "dj=", "go out", "have fun tonight", "turn up",
        ),
        categories=("bar_nightlife",),
        not_stems=("клубник",),
        unless=("kids", "kids_specific", "minor", "celebrate"),
        negation_excludes=("bar_nightlife",),
    ),
    Concept(
        "no_alcohol",
        ru=(
            "безалкогол", "без алкогол", "без выпивк", "без спиртн", "не алкогол", "трезв", "сухой закон", "без бухл", "не пью", "не пьем",
        ),
        kk=(
            "алкогольсіз", "алкоголсіз", "спирттісіз",
        ),
        en=(
            "no alcohol", "without alcohol", "alcoholfree", "nonalcoholic", "dry=", "sober", "teetotal", "dont drink",
        ),
        flags=("no_alcohol",),
    ),
    Concept(
        "museum",
        ru=(
            "музе", "галере", "выставк", "экспозиц", "артпространств", "арт пространств", "арт центр", "артцентр", "вернисаж", "экспонат", "картин", "планетари",
        ),
        kk=(
            "мұражай", "галерея", "көрме", "сурет галерея", "сурет көрме", "суреттер көрме",
        ),
        en=(
            "museum", "gallery", "exhibit", "exhibition", "exposition", "art space", "art center", "planetarium", "artwork",
        ),
        budget_min=LONG_VISIT_BUDGET_MIN,
        categories=("museum_gallery",),
        negation_excludes=("museum_gallery",),
    ),
    Concept(
        "interactive",
        ru=(
            "интерактив",
        ),
        kk=(
            "интерактив",
        ),
        en=(
            "interactive", "hands on", "handson",
        ),
        budget_min=LONG_VISIT_BUDGET_MIN,
        categories=("museum_gallery",),
        keywords=("интерактив",),
        negation_excludes=(),
    ),
    Concept(
        "landmark",
        ru=(
            "достопримечат", "памятник", "монумент", "архитектур", "небоскр", "собор", "мечет", "храм=", "церков", "статуя", "статуи", "скульптур", "историческ", "знаменит",
            "символ города", "осмотреть", "посмотреть город", "главные места", "красивые здания",
        ),
        kk=(
            "көрікті", "ескерткіш", "сәулет", "мешіт", "тарихи", "көрнекті",
        ),
        en=(
            "landmark", "sight=", "sights", "sightseeing", "attraction", "monument", "statue", "architecture", "historic", "historical", "cathedral", "mosque", "temple",
            "skyscraper", "must see", "mustsee", "famous",
        ),
        categories=("attraction_landmark",),
        negation_excludes=("attraction_landmark",),
    ),
    Concept(
        "viewpoint",
        ru=(
            "смотровая", "смотровой", "панорам", "вид на", "виды=", "видом=", "красивый вид", "с видом", "вид с высоты", "обзорн", "высотк", "с высоты", "небоскреб",
            "верхний этаж", "крыша", "крыше",
        ),
        kk=(
            "көрініс", "панорама", "биіктен", "шолу алаңы",
        ),
        en=(
            "viewpoint", "view=", "views", "panorama", "panoramic", "skyline", "overlook", "lookout", "observation deck", "scenic", "photo spot", "rooftop", "vista",
        ),
        categories=("viewpoint",),
        negation_excludes=("viewpoint",),
    ),
    Concept(
        "sunset_view",
        ru=(
            "закат", "рассвет", "золотой час", "золотое время",
        ),
        kk=(
            "күн батуы", "таң атуы",
        ),
        en=(
            "sunset", "sunrise", "golden hour", "sundown", "dusk", "twilight",
        ),
        categories=("viewpoint",),
        keywords=("закат",),
        negation_excludes=(),
    ),
    Concept(
        "city_from_above",
        ru=(
            "город сверху", "города сверху", "городом сверху", "вид сверху", "виды сверху", "посмотреть на город", "посмотреть на столицу", "посмотреть сверху", "взглянуть на город",
            "обозреть город", "вид на город", "панораму города", "окинуть взглядом город", "птичьего полета", "на город свысока", "увидеть город", "город с высоты", "город как на ладони",
        ),
        kk=(
            "қаланы биіктен", "қала көрінісі", "қаланың көрінісі", "жоғарыдан", "қаланы көру", "қала панорамасы",
        ),
        en=(
            "from above", "from the top", "city from above", "view of the city", "view over the city", "views of the city", "birds eye", "overlook the city", "see the city from",
            "look at the city", "top of the city", "above the city", "city view", "city views", "city from the top", "whole city",
        ),
        categories=("viewpoint", "attraction_landmark"),
        keywords=("вид на город", "панорама"),
        negation_excludes=("viewpoint",),
    ),
    Concept(
        "park",
        ru=(
            "парк", "сквер", "бульвар", "набережн", "сад=", "сада=", "саду=", "саде=", "сады=", "садов=", "лес=", "леса=", "лесу=", "лесопарк", "роща", "рощ", "аллея", "аллей",
            "природ", "пруд", "озер", "на свежем воздухе", "свежий воздух", "свежим воздухом", "пикник", "лавочк", "ботаническ", "дендропарк", "газон", "на природе",
            "на открытом воздухе",
        ),
        kk=(
            "саябақ", "жағалау", "табиғат", "орман", "көгал", "ашық аспан",
        ),
        en=(
            "park=", "parks=", "parkland", "garden", "boulevard", "embankment", "riverside", "promenade", "green space", "nature", "outdoors", "outdoor", "picnic", "fresh air",
            "lake", "pond", "forest", "woods", "open air", "greenery",
        ),
        categories=("park_garden",),
        not_stems=("парков", "паркинг", "паркет", "parking"),
        negation_excludes=("park_garden",),
    ),
    Concept(
        "playground",
        ru=(
            "площадк", "горки=", "горка=", "качел", "песочниц", "карусел", "лазилк", "батут", "игровая комната", "игровой комнат", "детская комната", "аниматор", "лабиринт",
        ),
        kk=(
            "ойын алаңы", "балалар алаңы", "ойын бөлмесі", "ойнау алаңы", "ойнайтын алаң",
        ),
        en=(
            "playground", "play area", "swings", "swing=", "slide=", "jungle gym", "playroom", "sandbox",
        ),
        categories=("kids_playground",),
        negation_excludes=("kids_playground",),
    ),
    Concept(
        "entertainment",
        ru=(
            "развлеч", "боулинг", "квест", "аттракцион", "аквапарк", "лазертаг", "бильярд", "картинг", "настольн игр", "настолк", "приставк", "антикафе", "зоопарк", "океанариум",
            "парк развлечений", "веревочн", "мини гольф", "пейнтбол", "кегл", "vr=", "аркад", "игровые автоматы", "тир=", "плейстейшн", "плэйстейшн",
        ),
        kk=(
            "ойын сауық", "көңілді", "боулинг", "квест", "аттракцион", "аквапарк",
        ),
        en=(
            "entertainment", "bowling", "quest", "escape room", "arcade", "amusement", "aquapark", "trampoline", "billiard", "karting", "laser tag", "lasertag", "zoo=", "aquarium",
            "board game", "board games", "fun=", "paintball", "funfair", "theme park", "playstation",
        ),
        categories=("entertainment",),
        negation_excludes=("entertainment",),
    ),
    Concept(
        "shopping",
        ru=(
            "тц=", "трц=", "торгов центр", "торгов комплекс", "молл", "шопинг", "магазин", "покупк", "купить", "купите", "одежд", "обув", "сувенир", "подарок", "подарк",
            "распродаж", "бутик", "универмаг", "затариться", "прибарахлиться",
        ),
        kk=(
            "сауда", "дүкен", "сатып ал", "сыйлық", "киім", "тц=", "трц=", "сауда орталығы",
        ),
        en=(
            "mall", "shopping", "shop=", "shops", "store=", "stores", "buy=", "boutique", "souvenir", "gift=", "gifts", "clothes", "clothing", "shopping center", "shopping centre",
            "retail", "bargains",
        ),
        categories=("mall",),
        negation_excludes=("mall",),
    ),
    Concept(
        "theatre_cinema",
        ru=(
            "театр", "кино", "кинотеатр", "фильм", "киношк", "опера", "оперу", "балет", "концерт", "филармон", "спектакл", "постановк", "мюзикл", "цирк", "стендап", "стенд ап",
            "оркестр", "афиш", "премьер", "сеанс", "кинозал", "шоу=", "выступлен",
        ),
        kk=(
            "театр", "кино", "кинотеатр", "концерт", "опера", "спектакль", "кинога", "фильм", "кино көру",
        ),
        en=(
            "theatre", "theater", "cinema", "movie", "movies", "film", "films", "opera", "ballet", "concert", "philharmonic", "show=", "musical", "circus", "standup", "stand up",
            "gig=", "orchestra", "screening", "live music",
        ),
        categories=("culture_theatre_cinema",),
        negation_excludes=("culture_theatre_cinema",),
        budget_min=LONG_VISIT_BUDGET_MIN,  # a film or a play takes two hours: the default hour would drop it
    ),
    Concept(
        "culture",
        ru=(
            "культур", "искусств", "приобщиться", "духовн", "эстетическ", "творческ", "арт=", "арты",
        ),
        kk=(
            "мәдениет", "өнер", "мәдени", "көркем", "рухани", "шығармашылық",
        ),
        en=(
            "culture", "cultural", "arts", "art=", "artistic", "creative", "enrichment", "highbrow", "heritage",
        ),
        categories=("museum_gallery", "culture_theatre_cinema"),
        negation_excludes=(),
    ),
    Concept(
        "library_cowork",
        ru=(
            "библиотек", "коворкинг", "читальн", "читальный зал", "комната для работы",
        ),
        kk=(
            "кітапхана", "коворкинг", "оқу залы", "кітап оқу залы", "оқитын орын", "жұмыс орны",
        ),
        en=(
            "library", "coworking", "reading room", "study room", "workspace", "work space", "work hub", "study hall",
        ),
        categories=("coworking_library",),
        negation_excludes=("coworking_library",),
    ),
    Concept(
        "sport_gym",
        ru=(
            "спорт", "тренажерн", "тренажерк", "качалк", "качаться", "качат", "фитнес", "тренировк", "тренироваться", "йога=", "йоги=", "йогу=", "йогой=", "пилатес", "растяжк",
            "плаван", "бассейн", "каток", "катани", "коньк", "лыж", "сноуборд", "велосипед", "велик=", "велики=", "самокат", "ролик", "скейт", "скалодром", "боулдеринг", "бокс=",
            "борьб", "кроссфит", "зал=", "залу=", "залом=", "покататься", "потренироваться", "поплавать",
        ),
        kk=(
            "спорт", "жаттығу", "бассейн", "жүзу", "мұз айдыны", "шаңғы", "велосипед", "фитнес", "жаттығуға", "спортзал",
        ),
        en=(
            "sport", "sports", "gym=", "gyms", "fitness", "workout", "work out", "swim", "swimming", "pool=", "skate", "skating", "ski=", "skiing", "bike", "bikes", "cycling",
            "cycle=", "yoga", "pilates", "climb", "climbing", "exercise", "training", "crossfit", "rollerblading", "scooter",
        ),
        categories=("sport",),
        negation_excludes=("sport",),
    ),
    Concept(
        "gym_indoor",
        ru=(
            "спортзал", "спортивн зал", "тренажерн", "тренажерк", "качалк", "фитнес", "в зал",
        ),
        kk=(
            "спортзал", "жаттығу залы", "фитнес",
        ),
        en=(
            "gym=", "gyms=", "fitness", "weight room", "workout room",
        ),
        categories=("sport",),
        keywords=("спортзал", "фитнес", "gym"),
        negation_excludes=("sport",),
    ),
    Concept(
        "sport_outdoor",
        ru=(
            "футбол", "баскетбол", "волейбол", "теннис", "бадминтон", "мяч=", "мяча=", "мячи=", "мячик", "бегать", "побегать", "бег=", "бега=", "бегу=", "пробежк", "трусц",
            "размяться", "размять", "поразмять", "подвигаться", "двигаться", "активн отдых", "поиграть в мяч", "пинг понг", "пингпонг",
        ),
        kk=(
            "футбол", "баскетбол", "волейбол", "жүгіру", "жүгіруге", "белсенді", "теннис",
        ),
        en=(
            "football", "soccer", "basketball", "volleyball", "tennis", "badminton", "jog", "jogging", "run=", "running", "ball=", "active=", "play sports", "play football",
            "get moving", "stretch=", "frisbee", "ping pong", "pingpong", "kickabout",
        ),
        categories=("sport", "park_garden"),
        negation_excludes=("sport",),
    ),
    Concept(
        "kids",
        ru=(
            "ребен", "дети=", "детей=", "детям=", "детьми=", "детях=", "малыш", "сын=", "сына=", "сыну=", "сыном=", "сыновь", "дочь=", "дочк", "доч=", "внук", "внучк", "племянн",
            "школьник", "дошкольн", "младенц", "грудничк", "карапуз", "семейн", "всей семьей", "с семьей", "для детей", "детсад", "детский сад",
        ),
        kk=(
            "бала=", "балам", "балалар", "бүлдіршін", "нәресте", "отбасы", "отбасымен", "сәби", "ұлым", "қызым", "балаларымен", "кішкентай", "баласымен", "баламен", "баламмен", "балаларыммен", "сәбимен",
        ),
        en=(
            "kid=", "kids=", "child", "children", "toddler", "baby", "babies", "infant", "son=", "daughter", "family", "families", "nephew", "niece", "preschool", "little ones",
            "grandkids", "my boy", "my girl",
        ),
        categories=("kids_playground", "museum_gallery"),
        tier="mood",
        flags=("with_kids",),
        budget_min=LONG_VISIT_BUDGET_MIN,
        negation_excludes=(),
    ),
    Concept(
        "kids_specific",
        ru=(
            "детск",
        ),
        flags=("with_kids",),
        keywords=("детск",),
        budget_min=LONG_VISIT_BUDGET_MIN,
        negation_excludes=(),
    ),
    Concept(
        "work_laptop",
        ru=(
            "поработ", "работать=", "работаю=", "работаем=", "розетк", "вайфай", "интернет", "зарядит", "зарядк", "ноутбук", "ноутом", "ноут=", "удаленн", "фриланс", "дедлайн",
            "созвон", "зум=", "для работы", "по работе", "рабочее место", "поучиться", "учеба", "учебы", "курсовая", "диплом=", "сессия", "лекци", "wifi", "дипломн", "диссертац", "эссе=", "курсач", "написать диплом",
        ),
        kk=(
            "розетка", "розеткасы", "жұмыс істеу", "жұмыс істегім", "ноутбук", "интернет", "wifi", "оқу үшін", "диплом жұмыс", "курстық жұмыс", "диссертация",
        ),
        en=(
            "wifi", "socket", "outlet", "plug=", "charger", "charge", "laptop", "internet", "remote work", "work remotely", "to work", "freelance", "deadline", "working=",
            "study=", "studying", "zoom=", "power outlet", "charging", "thesis", "dissertation", "essay", "essays", "assignment",
        ),
        categories=("cafe", "coworking_library"),
        tier="mood",
        flags=("wifi",),
        unless=("night_shift",),
        negation_excludes=(),
    ),
    Concept(
        "quiet_read",
        ru=(
            "почитать", "читать=", "книг", "книжк", "позаниматься", "подготовиться к экзамен", "уроки=", "почитаю", "почитаем", "с книгой", "тетрад", "учебник",
        ),
        kk=(
            "кітап оқу", "кітап", "оқығым", "сабақ дайындау", "оқуға", "оқимын", "сабақ оқу", "емтиханға дайындал",
        ),
        en=(
            "read=", "reading", "book=", "books", "novel", "homework", "study quietly", "to study", "study for", "exam=", "exams=", "revise=", "revision=", "to concentrate", "concentrate=",
        ),
        categories=("coworking_library", "cafe"),
        tier="mood",
        flags=("quiet",),
        negation_excludes=(),
    ),
    Concept(
        "quiet",
        ru=(
            "тихо", "тихи", "тиха", "тиху", "тише", "потише", "тишин", "спокойн", "без шума", "не шумн", "нешумн", "уединен", "умиротвор", "подальше от толпы", "без толпы",
            "малолюдн", "безлюдн", "не людн", "пустынн", "камерн", "релакс", "расслабл", "тишь", "менее людн", "поменьше людей", "меньше людей", "не так людн", "не толпа",
        ),
        kk=(
            "тыныш", "тынық", "тыныштық", "сабырлы", "шусыз", "жайбарақат",
        ),
        en=(
            "quiet", "calm", "peaceful", "tranquil", "serene", "relaxing", "secluded", "low key", "lowkey", "not crowded", "away from the crowd", "peace=", "silent", "silence",
            "hush", "uncrowded", "less crowded", "less busy", "not too busy", "not busy", "fewer people", "quieter", "less people", "no noise", "not noisy", "not loud", "without noise", "noise free", "low noise",
            "away from noise",
        ),
        flags=("quiet",),
    ),
    Concept(
        "unusual",
        ru=(
            "необычн", "уникальн", "нестандарт", "оригинальн", "креатив", "странн", "чудн", "экзотич", "эксцентрич", "ни на что не похож", "стрит арт", "стритарт", "граффити",
            "инсталляц", "артобъект", "арт объект", "хипстер", "фишк", "изюминк", "секретн", "малоизвестн", "нетуристическ", "что нибудь новое", "новенькое", "что то интересное",
        ),
        kk=(
            "ерекше", "ғажайып", "әдеттен тыс", "өзгеше", "ерекшелік", "тосын",
        ),
        en=(
            "unusual", "unique", "quirky", "weird", "strange", "offbeat", "off the beaten path", "hidden gem", "original", "creative", "exotic", "hipster", "street art",
            "graffiti", "instagrammable", "secret", "hidden", "something different", "something new", "odd=",
        ),
        categories=("attraction_landmark", "museum_gallery", "viewpoint", "entertainment"),
        tier="mood",
        flags=("unusual",),
        keywords=("необычн", "уникальн", "арт", "стрит-арт", "инсталляц"),
        negation_excludes=(),
    ),
    Concept(
        "night",
        ru=(
            "ночн", "ночью", "ночь=", "ночи=", "поздно", "поздн", "после полуночи", "заполночь", "за полночь", "полноч", "до утра", "допоздна", "круглосуточн", "всю ночь",
        ),
        kk=(
            "түнгі", "түнде", "түн=", "түнгі уақыт", "түнімен", "түн ортасы",
        ),
        en=(
            "night=", "nights=", "nighttime", "late=", "late night", "latenight", "after midnight", "midnight", "overnight", "all night", "24 7", "around the clock", "till late",
        ),
        categories=("bar_nightlife", "entertainment", "culture_theatre_cinema", "cafe", "attraction_landmark", "viewpoint"),
        tier="mood",
        flags=("night",),
        negation_excludes=(),
    ),
    Concept(
        "evening",
        ru=(
            "вечер", "вечерк", "вечерн", "после работы", "сегодня вечером", "стемнел", "после заката", "темнеет",
        ),
        kk=(
            "кешке", "кешкі", "кешкісін", "кештете",
        ),
        en=(
            "tonight", "evening", "after work", "after dark", "this evening", "later today", "eve=", "nightfall",
        ),
        flags=("evening",),
    ),
    Concept(
        "tourist",
        ru=(
            "турист", "туристическ", "экскурс", "путешеств", "приезжий", "приезжаю", "приезжа", "гость города", "первый раз", "впервые", "транзит", "пересадк", "между рейсами",
            "командировк", "гид=", "что посмотреть", "что посетить", "что тут есть", "что здесь есть", "че тут есть", "че здесь есть", "что интересного", "первый день",
            "что стоит посмотреть", "что можно посмотреть",
        ),
        kk=(
            "турист", "туристік", "қонақ", "саяхатшы", "алғаш рет", "алғаш келдім", "саяхат", "не көруге", "көретін жер", "көруге болады", "алғашқы күн", "бірінші күн",
        ),
        en=(
            "tourist", "sightsee", "visitor", "first time in", "just arrived", "trip=", "traveler", "traveller", "travelling", "traveling", "layover", "stopover", "business trip",
            "guide=", "new in town", "first day", "what to see", "what to visit", "things to see", "whats here", "what is here", "whats there to see",
        ),
        categories=("attraction_landmark", "viewpoint", "museum_gallery", "park_garden", "cafe"),
        budget_min=LONG_VISIT_BUDGET_MIN,
        tier="mood",
        flags=("tourist",),
        unless=("not_tourist",),
        negation_excludes=(),
    ),
    Concept(
        "waiting",
        ru=(
            "жду=", "ждем=", "ждать=", "ожида", "в ожидании", "до поезда", "до рейса", "до автобуса", "до отправления", "перед поездом", "перед рейсом", "перед автобусом",
            "задержка рейса", "задержали рейс", "убить время", "скоротать", "время убить",
        ),
        kk=(
            "күтіп отыр", "күтіп жатыр", "күтемін", "күтеміз", "күту", "пойызға дейін", "рейске дейін", "автобусқа дейін", "уақыт өткізу", "уақытты өткізу",
        ),
        en=(
            "waiting=", "wait=", "waiting for", "before my train", "before the train", "before my bus", "before the bus", "until my train", "until the train", "kill time", "killing time",
            "time to kill", "to kill time", "delayed",
        ),
        categories=("cafe", "mall", "park_garden", "attraction_landmark"),
        tier="mood",
        budget_min=WAITING_BUDGET_MIN,
        negation_excludes=(),
    ),
    Concept(
        "between_classes",
        ru=(
            "между парами", "между парой", "между пары", "между лекци", "между занят", "между урок", "на перемен", "большой перемен", "окно между", "окно в расписании", "перерыв между", "обеденный перерыв",
            "в перерыв", "перерыве=", "перерыв=",
        ),
        kk=(
            "сабақ арасында", "пар арасында", "дәріс арасында", "үзіліс", "үзілісте", "түскі үзіліс", "сабақтан кейін",
        ),
        en=(
            "between classes", "between lectures", "between lessons", "between meetings", "between class", "lunch break", "lunch hour", "coffee break", "study break", "break between",
            "on my break",
        ),
        categories=("cafe", "fast_food", "park_garden"),
        tier="mood",
        budget_min=BETWEEN_CLASSES_BUDGET_MIN,
        negation_excludes=(),
    ),
    Concept(
        "stroll",
        ru=(
            "прогул", "погуля", "гуля", "прогуляться", "пройтись", "прогулочн", "променад", "побродить", "бродить", "пошататься", "подышать", "проветриться", "пешая",
            "размять ноги", "пройдемся", "поброд",
        ),
        kk=(
            "серуен", "серуендеу", "қыдыр", "аралау", "қыдыру", "серуендегім", "серуендейік", "аралап",
        ),
        en=(
            "stroll=", "strolls", "strolling", "walk=", "walks=", "wander", "wandering", "hike", "hiking", "take a walk", "go for a walk", "saunter", "amble", "get some air", "explore on foot",
            "walkabout",
        ),
        categories=("park_garden", "attraction_landmark", "viewpoint"),
        tier="activity",
        covered_by=("kids_playground", "sport"),
        negation_excludes=(),
        forbids=("fast_food", "bar_nightlife", "mall", "other"),
    ),
    Concept(
        "date_evening",
        ru=(
            "свидани", "романтик", "романтичн", "с девушкой", "с парнем", "с женой", "с мужем", "с любимой", "с любимым", "вдвоем", "с половинк", "годовщин", "предложение руки",
            "с женихом", "с невестой", "для двоих", "на двоих",
        ),
        kk=(
            "кездесу", "романтик", "сүйіктім", "қызбен", "жігітпен", "жұбайым", "екеуміз", "ғашық",
        ),
        en=(
            "date=", "dates=", "romantic", "girlfriend", "boyfriend", "wife=", "husband", "couple", "anniversary", "with my gf", "with my bf", "for two", "sweetheart", "fiancee",
            "fiance",
        ),
        categories=("restaurant", "cafe", "viewpoint", "culture_theatre_cinema"),
        tier="mood",
        negation_excludes=(),
    ),
    Concept(
        "hangout",
        ru=(
            "посидеть", "посиделк", "встретиться с друзьями", "встреча с друзьями", "с друзьями", "с подругами", "с компанией", "компанией", "с коллегами", "с ребятами",
            "потусоваться", "пообщаться", "поболтать", "посидим", "большой компани", "большая компани", "всей компани", "большой группой", "всей группой", "нас много", "всем вместе",
        ),
        kk=(
            "отыру", "отырайық", "достармен", "жолдастармен", "әңгімелесу", "үлкен компания", "бәріміз бірге", "топпен",
        ),
        en=(
            "hang out", "hangout", "chill", "meet friends", "with friends", "catch up", "get together", "with colleagues", "with a group", "large group", "big group", "group of friends", "all of us together", "all together",
        ),
        categories=("cafe", "restaurant"),
        tier="mood",
        negation_excludes=(),
    ),
    Concept(
        "dog_walk",
        ru=(
            "собак", "пес=", "пса=", "псом=", "питомц", "щенк", "выгул", "с четвероногим", "лабрадор", "кошк", "с котом", "с котиком", "с животн", "petfriendly", "pet friendly", "можно с собак",
        ),
        kk=(
            "ит=", "итпен", "иті", "үй жануары", "ит жетектеп", "күшік", "мысық", "итіммен", "жануармен",
        ),
        en=(
            "dog=", "dogs=", "puppy", "pet=", "pets=", "dog park", "with my dog", "leash", "off leash", "doggo", "petfriendly", "pet friendly", "dog friendly", "dogfriendly", "my cat", "with my cat", "with a dog", "with our dog",
        ),
        categories=("park_garden",),
        tier="mood",
        flags=("pets",),
        keywords=("собак", "dog"),
        negation_excludes=(),
    ),
    Concept(
        "shelter_from_weather",
        ru=(
            "дожд", "ливень", "ливня", "непогод", "промок", "холодно", "холод=", "холода=", "холоду=", "мороз", "стужа", "замерз", "метел", "снег", "буран", "ветер=", "ветра=",
            "ветрено", "жарко", "жара=", "духота", "душно", "переждать", "укрыться", "спрятаться", "согреться", "погреться", "обогре", "теплое место", "в тепле", "под крышей",
            "крытое", "в помещении", "не на улице", "от погоды", "тепло", "теплее", "околел", "продрог", "замерзаю", "слякот", "град=", "гроза",
        ),
        kk=(
            "жаңбыр", "суық", "аяз", "боран", "жылы жер", "паналау", "жауын шашын", "жылынғым", "үсіп", "қар=", "ыстық",
        ),
        en=(
            "rain", "raining", "rainy", "storm", "cold=", "freezing", "frozen", "snow", "snowing", "windy", "wait out", "shelter", "warm up", "warm place", "indoor", "indoors",
            "out of the rain", "hide from", "too hot", "heatwave", "heat=", "chilly", "drizzle", "bad weather",
        ),
        categories=("cafe", "museum_gallery", "mall", "culture_theatre_cinema", "coworking_library"),
        tier="mood",
        negation_excludes=(),
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
)
CONCEPTS: tuple[Concept, ...] = (*_CORE_CONCEPTS, *EXTRA_CONCEPTS)
# fmt: on
