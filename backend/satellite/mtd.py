"""MTD_MSIL2A.xml에서 반사율 변환 파라미터를 읽는다(spec 2-2).

네임스페이스 접두사가 baseline마다 달라서(n1:... 등) 로컬 태그명만 보고 찾는다.
"""
import xml.etree.ElementTree as ET

# ESA band_id(0-indexed) -> 우리가 쓰는 밴드명. B01,B05~B07,B8A,B09,B10,B12는 안 쓴다.
BAND_ID_TO_NAME = {1: "B02", 2: "B03", 3: "B04", 7: "B08", 11: "B11"}

DEFAULT_QUANTIFICATION_VALUE = 10000


def _local_tag(element) -> str:
    tag = element.tag
    return tag.split("}")[-1] if "}" in tag else tag


def parse_mtd(xml_path) -> dict:
    """{"band_offsets": {"B02": int, ...}, "boa_quantification_value": int}.

    `BOA_ADD_OFFSET_VALUES_LIST`가 없는 구형 제품(baseline 04.00 이전)은 전부 오프셋 0으로
    채운다(spec 2-2: "값이 없는 구형 제품은 오프셋 0으로 처리한다").
    """
    root = ET.parse(xml_path).getroot()

    quantification_value = DEFAULT_QUANTIFICATION_VALUE
    for el in root.iter():
        if _local_tag(el) == "BOA_QUANTIFICATION_VALUE" and el.text and el.text.strip():
            quantification_value = int(float(el.text.strip()))
            break

    band_offsets = {name: 0 for name in BAND_ID_TO_NAME.values()}
    for el in root.iter():
        if _local_tag(el) != "BOA_ADD_OFFSET":
            continue
        band_id_raw = el.attrib.get("band_id")
        if band_id_raw is None or el.text is None or not el.text.strip():
            continue
        band_name = BAND_ID_TO_NAME.get(int(band_id_raw))
        if band_name:
            band_offsets[band_name] = int(float(el.text.strip()))

    return {"band_offsets": band_offsets, "boa_quantification_value": quantification_value}
