"""Overture records that are not places a walker visits: residential complexes, offices, real estate, schools...

Overture's taxonomy is crowd/ML-labelled: most "historic_site" records in Astana are residential complexes
("ЖК Городской Романс"). The merge demotes such records to category `other` (kept in `overture_places.json`,
never added to `poi.enriched.json`, and matched to OSM only on a near-identical name).
"""

from __future__ import annotations

import re

# Taxonomy values (primary or any hierarchy level) that are never a walking destination. The category map in
# overture_places.py already sends these to `other`; checked here too so a future mapping change cannot leak them.
NON_POI_TAXONOMY = {
    "real_estate", "real_estate_service", "real_estate_agent", "property_management", "apartment", "apartments",
    "condominium", "residential_building", "housing_development", "construction_services", "building_contractor",
    "professional_services", "corporate_office", "commercial_building", "bank_credit_union", "bank", "atms",
    "financial_service", "school", "elementary_school", "high_school", "preschool", "college_university",
    "hospital", "medical_center", "clinic", "doctor", "dentist", "government_office", "public_service_and_government",
    "automotive_repair", "automotive_services_and_repair", "car_dealer", "car_wash", "gas_station",
}

# Word-bounded (Cyrillic/Latin/kk aware) name patterns, one reason code each. Order = precedence.
_W = r"(?<![\w])(?:{})(?![\w])"
NAME_PATTERNS: dict[str, re.Pattern[str]] = {
    "residential_complex": re.compile(
        _W.format(r"жк|zhk|жилой\s+комплекс\w*|жилой\s+квартал|жилой\s+массив|residential\s+complex|apartments?|апартамент\w*")
        + r"|тұрғын\s+кешен\w*", re.I),
    "business_centre_office": re.compile(
        _W.format(r"бц|бизнес[\s-]?центр\w*|business[\s-]?cent(?:er|re)|офис\w*|office"), re.I),
    "legal_entity": re.compile(_W.format(r"тоо|ао|ип|оао|зао|ооо|llp|ltd|llc|холдинг"), re.I),
    "real_estate_construction": re.compile(
        r"недвижим|real\s+estate|(?<![\w])realty|риэлт|застройщик|девелопер|(?<![\w])developer|строительн"
        r"|(?<![\w])construction|(?<![\w])строй\w*", re.I),
    "school_education": re.compile(
        _W.format(r"школ[аыеуой]?|гимнази\w+|лицей|колледж\w*|университет\w*|university|school|college|kindergarten"
                  r"|интернат|детский\s+сад"), re.I),
    "clinic_medical": re.compile(
        r"клиник|поликлиник|больниц|медицинск|медцентр|(?<![\w])clinic|(?<![\w])hospital|стоматолог|(?<![\w])dental"
        r"|аптек|(?<![\w])pharmacy", re.I),
    "government_office": re.compile(
        r"акимат|akimat|министерств|ministry|департамент|(?<![\w])управлени|(?<![\w])комитет|налогов|прокуратур"
        r"|(?<![\w])полици|судебн|нотариус|(?<![\w])цон(?![\w])", re.I),
    "bank_atm": re.compile(_W.format(r"банк|bank|банкомат\w*|atm|обменн\w+\s+пункт"), re.I),
    "car_service": re.compile(
        r"автосервис|автомойк|шиномонтаж|автозапчаст|автосалон|автоцентр|(?<![\w])азс(?![\w])|заправк|car\s?wash"
        r"|auto\s?service|detailing|(?<![\w])сто(?![\w])", re.I),
}
# A school/university mention does not disqualify a library or a theatre inside it.
_EDUCATION_EXEMPT = re.compile(r"библиотек|library|кітапхан|музей|museum|театр|theat", re.I)

# Overture's `historic_site` is the label its sources put on residential complexes, new-build addresses and
# offices ("Highvill", "Nova City", "Бараева 16"). Real heritage carries a name that says what it is.
HERITAGE_NAME = re.compile(
    r"памятник|монумент|мемориал|обелиск|ескерткіш|мечеть|мешіт|собор|церков|храм|синагог|музей|museum|театр"
    r"|theat|опера|opera|парк|park|сквер|площадь|алаң|фонтан|саябағ|саябақ|набережн|(?<![\w])арка(?![\w])|стела"
    r"|бульвар|аллея|аллеи|алле[яй]|башня|дворец|сарай|крепость|усадьба|замок|ворота|қақпа|кафедраль|monument"
    r"|memorial|cathedral|church|mosque|temple|статуя|скульптур|heykel", re.I)

HISTORIC_UNVERIFIED = "historic_site_unverified"


def non_poi_reason(ov: dict) -> str | None:
    """Reason code if this Overture record (already mapped to one of our categories) is not a walkable POI."""
    if ov["category"] == "other":
        return None
    cats = ov["categories"]
    if NON_POI_TAXONOMY & {cats["primary"], *(cats["hierarchy"] or [])}:
        return "taxonomy"
    name = ov["name"] or ""
    for reason, rx in NAME_PATTERNS.items():
        if rx.search(name) and not (reason == "school_education" and _EDUCATION_EXEMPT.search(name)):
            return reason
    if cats["primary"] == "historic_site" and not HERITAGE_NAME.search(name):
        return HISTORIC_UNVERIFIED
    return None
