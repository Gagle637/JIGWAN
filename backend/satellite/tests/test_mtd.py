from satellite.mtd import parse_mtd

MTD_WITH_OFFSETS = """<?xml version="1.0" encoding="UTF-8"?>
<n1:Level-2A_User_Product xmlns:n1="https://psd-14.sentinel2.eo.esa.int/PSD/User_Product_Level-2A.xsd">
  <n1:General_Info>
    <Product_Image_Characteristics>
      <QUANTIFICATION_VALUES_LIST>
        <BOA_QUANTIFICATION_VALUE unit="none">10000</BOA_QUANTIFICATION_VALUE>
      </QUANTIFICATION_VALUES_LIST>
      <BOA_ADD_OFFSET_VALUES_LIST>
        <BOA_ADD_OFFSET band_id="1">-1000</BOA_ADD_OFFSET>
        <BOA_ADD_OFFSET band_id="2">-1000</BOA_ADD_OFFSET>
        <BOA_ADD_OFFSET band_id="3">-1000</BOA_ADD_OFFSET>
        <BOA_ADD_OFFSET band_id="7">-1000</BOA_ADD_OFFSET>
        <BOA_ADD_OFFSET band_id="11">-1000</BOA_ADD_OFFSET>
      </BOA_ADD_OFFSET_VALUES_LIST>
    </Product_Image_Characteristics>
  </n1:General_Info>
</n1:Level-2A_User_Product>
"""

MTD_WITHOUT_OFFSETS = """<?xml version="1.0" encoding="UTF-8"?>
<n1:Level-2A_User_Product xmlns:n1="https://psd-12.sentinel2.eo.esa.int/PSD/User_Product_Level-2A.xsd">
  <n1:General_Info>
    <Product_Image_Characteristics>
      <QUANTIFICATION_VALUES_LIST>
        <BOA_QUANTIFICATION_VALUE unit="none">10000</BOA_QUANTIFICATION_VALUE>
      </QUANTIFICATION_VALUES_LIST>
    </Product_Image_Characteristics>
  </n1:General_Info>
</n1:Level-2A_User_Product>
"""


def test_parse_mtd_with_offsets(tmp_path):
    path = tmp_path / "MTD_MSIL2A.xml"
    path.write_text(MTD_WITH_OFFSETS, encoding="utf-8")

    result = parse_mtd(path)

    assert result["boa_quantification_value"] == 10000
    assert result["band_offsets"] == {
        "B02": -1000,
        "B03": -1000,
        "B04": -1000,
        "B08": -1000,
        "B11": -1000,
    }


def test_parse_mtd_without_offsets_defaults_to_zero(tmp_path):
    """구형 제품(baseline 04.00 이전)은 BOA_ADD_OFFSET_VALUES_LIST가 없다(spec 2-2)."""
    path = tmp_path / "MTD_MSIL2A.xml"
    path.write_text(MTD_WITHOUT_OFFSETS, encoding="utf-8")

    result = parse_mtd(path)

    assert result["boa_quantification_value"] == 10000
    assert all(offset == 0 for offset in result["band_offsets"].values())
    assert set(result["band_offsets"]) == {"B02", "B03", "B04", "B08", "B11"}
