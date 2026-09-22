from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class SalesClassification:
    canal: str
    regiao: str | None
    criterio: str


VAREJO_SELLERS_BY_REGION = {
    "BRAGANCA": ("ALESSANDRO", "LEIZ", "HELOA"),
    "JUNDIAI": ("DYOVANA", "JOSIANE FRAZAO", "KAYLANE"),
    "VARGINHA": ("PETERSON", "BRUNA", "THAIS"),
    "POUSO ALEGRE": ("PAOLA", "RAFAELA", "VITORIA"),
    "POCOS DE CALDAS": ("JOSE FELIPE", "MILENA", "CAMILA GUIMENTI"),
    "ITAJUBA": ("JENNIFER", "GABRIELA", "JESSICA S"),
    "EXTREMA": ("GUSTAVO", "INAYARA", "TAINARA"),
    "CAMBUI": ("JULIANO", "EDMILA", "MATHEUS TEIXEIRA", "ARIANE"),
}

VAREJO_CITIES_BY_REGION = {
    "BRAGANCA": (
        "ATIBAIA",
        "PIRACAIA",
        "BOM JESUS DOS PERDOES",
        "JOANOPOLIS",
        "VARGEM",
        "NAZARE PAULISTA",
        "MARIPORA",
    ),
    "JUNDIAI": (
        "ITATIBA",
        "JARINU",
        "VARZEA PAULISTA",
        "CAMPO LIMPO",
        "ITUPEVA",
        "CAJAMAR",
        "VINHEDO",
    ),
    "VARGINHA": (
        "TRES PONTAS",
        "TRES CORACOES",
        "ELOI MENDES",
        "PARAGUACU",
        "MONSENHOR PAULO",
        "CAMPANHA",
        "CAMBUQUIRA",
        "SAO GONCALO",
        "CAREACU",
        "COQUEIRAL",
        "SANTANA DA VARGEM",
    ),
    "POUSO ALEGRE": (
        "JACUTINGA",
        "BORDA DA MATA",
        "BUENO BRANDAO",
        "LAMBARI",
        "CAXAMBU",
        "SAO LOURENCO",
        "SAO SEBASTIAO DA BELA VISTA",
        "NATERCIA",
        "HELIODORA",
        "OURO FINO",
        "BAEPENDI",
        "CARMO DE MINAS",
        "MONTE SIAO",
        "INCONFIDENTES",
        "CONCEICAO DO RIO VERDE",
    ),
    "POCOS DE CALDAS": (
        "ALFENAS",
        "MACHADO",
        "CALDAS",
        "SANTA RITA DE CALDAS",
        "CONGONHAL",
        "POCO FUNDO",
        "SILVIANOPOLIS",
        "FAMA",
        "ANDRADAS",
        "IPUIUNA",
        "IBITIURA",
        "CAMPOS GERAIS",
    ),
    "ITAJUBA": (
        "SANTA RITA SAPUCAI",
        "PIRANGUINHO",
        "MARIA DA FE",
        "PEDRALVA",
        "VIRGINIA",
        "DELFIM MOREIRA",
        "GONCALVES",
        "SAPUCAI MIRIM",
        "SAO BENTO",
        "CONCEICAO DOS OUROS",
        "CACHOEIRA DE MINAS",
        "BRASOPOLIS",
        "PARAISOPOLIS",
        "SAO JOSE DO ALEGRE",
        "CONSOLACAO",
    ),
    "EXTREMA": (
        "TOLEDO",
        "MUNHOZ",
        "PEDRA BELA",
        "PINHALZINHO",
        "SOCORRO",
        "SERRA NEGRA",
    ),
    "CAMBUI": (
        "BOM REPOUSO",
        "SENADOR",
        "ESTIVA",
        "CAMANDUCAIA",
        "ITAPEVA",
        "CORREGO DO BOM JESUS",
    ),
}

ATACADO_DDDS_BY_SELLER = {
    "LARISSA TERRA": ("11", "12", "13"),
    "JULIO MELO": ("15", "19"),
    "WILSON NETO": ("14", "16", "17", "18"),
}

ATACADO_CITIES_BY_DDD = {
    "11": ("SAO PAULO", "GUARULHOS", "SAO BERNARDO DO CAMPO", "SANTO ANDRE", "OSASCO", "JUNDIAI", "MOGI DAS CRUZES", "BARUERI", "ATIBAIA", "BRAGANCA PAULISTA"),
    "12": ("SAO JOSE DOS CAMPOS", "TAUBATE", "JACAREI", "PINDAMONHANGABA", "GUARATINGUETA", "CACAPAVA", "LORENA", "CARAGUATATUBA", "UBATUBA"),
    "13": ("SANTOS", "SAO VICENTE", "PRAIA GRANDE", "GUARUJA", "CUBATAO", "ITANHAEM", "PERUIBE", "REGISTRO", "BERTIOGA"),
    "15": ("SOROCABA", "ITAPETININGA", "TATUI", "ITAPEVA", "VOTORANTIM", "BOITUVA", "ARACOIABA DA SERRA", "SAO MIGUEL ARCANJO"),
    "19": ("CAMPINAS", "PIRACICABA", "LIMEIRA", "AMERICANA", "INDAIATUBA", "SUMARE", "RIO CLARO", "MOGI GUACU", "MOGI MIRIM", "SAO JOAO DA BOA VISTA"),
    "14": ("BAURU", "MARILIA", "JAU", "BOTUCATU", "OURINHOS", "AVARE", "LINS", "LENCOIS PAULISTA"),
    "16": ("RIBEIRAO PRETO", "FRANCA", "SAO CARLOS", "ARARAQUARA", "SERTAOZINHO", "JABOTICABAL", "MATAO", "BATATAIS"),
    "17": ("SAO JOSE DO RIO PRETO", "BARRETOS", "CATANDUVA", "BEBEDOURO", "FERNANDOPOLIS", "VOTUPORANGA", "OLIMPIA", "MIRASSOL"),
    "18": ("PRESIDENTE PRUDENTE", "ARACATUBA", "BIRIGUI", "ASSIS", "ANDRADINA", "ADAMANTINA", "DRACENA", "PENAPOLIS"),
}

VAREJO_CITY_TO_REGION = {
    normalize_key(city): region
    for region, cities in VAREJO_CITIES_BY_REGION.items()
    for city in cities
}
VAREJO_SELLER_TO_REGION = {
    normalize_key(seller): region
    for region, sellers in VAREJO_SELLERS_BY_REGION.items()
    for seller in sellers
}
ATACADO_SELLER_TO_DDDS = {
    normalize_key(seller): ddds
    for seller, ddds in ATACADO_DDDS_BY_SELLER.items()
}
ATACADO_CITY_TO_DDD = {
    normalize_key(city): ddd
    for ddd, cities in ATACADO_CITIES_BY_DDD.items()
    for city in cities
}


def find_region_by_seller(seller_key: str) -> str | None:
    if seller_key in VAREJO_SELLER_TO_REGION:
        return VAREJO_SELLER_TO_REGION[seller_key]
    for known_seller, region in VAREJO_SELLER_TO_REGION.items():
        if known_seller and known_seller in seller_key:
            return region
    return None


def find_ddds_by_seller(seller_key: str) -> tuple[str, ...] | None:
    if seller_key in ATACADO_SELLER_TO_DDDS:
        return ATACADO_SELLER_TO_DDDS[seller_key]
    for known_seller, ddds in ATACADO_SELLER_TO_DDDS.items():
        if known_seller and known_seller in seller_key:
            return ddds
    return None


def classify_sale(*, city: str | None, seller: str | None, segment: str | None = None) -> SalesClassification:
    city_key = normalize_key(city)
    seller_key = normalize_key(seller)
    segment_key = normalize_key(segment)

    seller_ddds = find_ddds_by_seller(seller_key)
    if seller_ddds:
        ddd = ATACADO_CITY_TO_DDD.get(city_key)
        region = f"DDD {ddd}" if ddd else "DDD " + "/".join(seller_ddds)
        return SalesClassification("atacado", region, "vendedor_atacado")

    if "ATAC" in segment_key:
        ddd = ATACADO_CITY_TO_DDD.get(city_key)
        return SalesClassification("atacado", f"DDD {ddd}" if ddd else None, "segmento")

    if city_key in VAREJO_CITY_TO_REGION:
        return SalesClassification("varejo", VAREJO_CITY_TO_REGION[city_key], "cidade_varejo")

    seller_region = find_region_by_seller(seller_key)
    if seller_region:
        return SalesClassification("varejo", seller_region, "vendedor_varejo")

    if "VAREJO" in segment_key:
        return SalesClassification("varejo", None, "segmento")

    if city_key in ATACADO_CITY_TO_DDD:
        return SalesClassification("atacado", f"DDD {ATACADO_CITY_TO_DDD[city_key]}", "cidade_atacado")

    return SalesClassification("indefinido", None, "sem_match")
