"""Reader-only variant of fixture 1 (NOT a producer output).

Documented transformation of the hand-written expected XML: TextRegion and AdvertRegion
elements are written in reverse document order, and the two TextLine children of
r_p_b0002 are swapped. RegionRefIndexed and readingOrder {index} are unchanged, so a
conforming reader must produce exactly fixture-1-order.expected-reading.json.
"""
import sys
from lxml import etree as ET

NS = "{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}"
source, target = sys.argv[1], sys.argv[2]
tree = ET.parse(source, ET.XMLParser(remove_blank_text=True))
page = tree.getroot().find(f"{NS}Page")
regions = [e for e in page if e.tag in (f"{NS}TextRegion", f"{NS}AdvertRegion")]
for e in regions:
    page.remove(e)
anchor = page.find(f"{NS}SeparatorRegion")
for e in reversed(regions):
    anchor.addprevious(e)
region = next(e for e in page if e.get("id") == "r_p_b0002")
lines = region.findall(f"{NS}TextLine")
lines[0].addprevious(lines[1])
tree.write(target, encoding="UTF-8", xml_declaration=True, pretty_print=True)
