"""Split the five-layer diagram into two native, editable draw.io pages.

The second page repeats b2 as a continuation anchor. Its transparent port
touches e2's left boundary so f4 keeps its original d3 -> e2 relationship.
"""

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


def split_drawio(path: Path) -> None:
    base = ET.parse(path).getroot().find(".//mxGraphModel")
    if base is None:
        raise ValueError(f"Missing uncompressed mxGraphModel: {path}")
    cells = {cell.get("id"): cell for cell in base.findall(".//mxCell")}
    upper = ["l1", "l2", "a1", "a2", "a3", "b1", "b2", "b3", "f1"]
    lower = ["l3", "l4", "l5", "c1", "c2", "c3", "d1", "d2", "d3", "d4", "e1", "e2", "e3", "f2", "f3", "f4"]
    root = ET.Element("mxfile", {"host": "drawio", "version": "30.3.14"})

    for index, (name, ids, page_width, page_height) in enumerate([
        ("五层功能架构（1/2）：入口与虚实适配", upper, 1100, 375),
        ("五层功能架构（2/2）：自治、算法与约束", lower, 1220, 750),
    ]):
        diagram = ET.SubElement(root, "diagram", {"id": f"five-layer-part-{index+1}", "name": name})
        graph = ET.SubElement(diagram, "mxGraphModel", dict(base.attrib))
        graph.set("pageWidth", str(page_width))
        graph.set("pageHeight", str(page_height))
        cellroot = ET.SubElement(graph, "root")
        cellroot.extend([deepcopy(cells["0"]), deepcopy(cells["1"])])
        for cell_id in ids:
            cellroot.append(deepcopy(cells[cell_id]))
        if index == 1:
            repeated = deepcopy(cells["b2"])
            repeated.set("parent", "1")
            cellroot.append(repeated)
        current = {cell.get("id"): cell for cell in cellroot.findall("mxCell")}

        def geometry(cell_id, x=None, y=None, width=None, height=None):
            geom = current[cell_id].find("mxGeometry")
            for key, value in (("x", x), ("y", y), ("width", width), ("height", height)):
                if value is not None:
                    geom.set(key, str(value))

        def font(cell_id, size=26):
            current[cell_id].set("style", current[cell_id].get("style").replace("fontSize=24;", f"fontSize={size};"))

        if index == 0:
            for cell_id, y in (("l1", 20), ("l2", 195)):
                geometry(cell_id, 20, y, 1060, 160)
                current[cell_id].set("style", current[cell_id].get("style").replace("startSize=38;", "startSize=50;"))
            for cell_id, x in (("a1", 20), ("a2", 370), ("a3", 720), ("b1", 20), ("b2", 370), ("b3", 720)):
                geometry(cell_id, x, 60, 320, 90)
                font(cell_id)
            points = current["f1"].find(".//Array")
            points.clear()
            points.set("as", "points")
            for x, y in ((550, 187), (200, 187)):
                ET.SubElement(points, "mxPoint", {"x": str(x), "y": str(y)})
        else:
            for cell_id, y, height in (("l3", 115, 225), ("l4", 355, 165), ("l5", 535, 195)):
                geometry(cell_id, 20, y, 1180, height)
                current[cell_id].set("style", current[cell_id].get("style").replace("startSize=38;", "startSize=50;"))
            geometry("b2", 430, 15, 340, 85)
            font("b2", 28)
            for cell_id, x, y, width, height in (
                ("c1", 25, 85, 260, 100), ("c2", 305, 60, 410, 150), ("c3", 745, 60, 410, 150),
                ("d1", 25, 60, 250, 95), ("d2", 315, 60, 250, 95), ("d3", 605, 60, 250, 95), ("d4", 895, 60, 250, 95),
                ("e1", 75, 60, 310, 120), ("e2", 435, 60, 310, 120), ("e3", 795, 60, 310, 120),
            ):
                geometry(cell_id, x, y, width, height)
                font(cell_id, 26 if cell_id in ("c2", "c3") else 28)
            for cell_id in ("l3", "l4", "l5"):
                current[cell_id].set("style", current[cell_id].get("style").replace("fontSize=26;", "fontSize=28;"))
            edge = current["f2"]
            edge.set("style", edge.get("style").replace("entryX=0.5;entryY=0;", "entryX=0;entryY=0.5;entryPerimeter=0;"))
            points = ET.SubElement(edge.find("mxGeometry"), "Array", {"as": "points"})
            for x, y in ((325, 110), (325, 237)):
                ET.SubElement(points, "mxPoint", {"x": str(x), "y": str(y)})
            port = ET.Element("mxCell", {"id": "e2_f4_port", "value": "", "style": "ellipse;opacity=0;fillOpacity=0;strokeOpacity=0;connectable=1;", "vertex": "1", "parent": "1"})
            ET.SubElement(port, "mxGeometry", {"x": "454", "y": "654", "width": "2", "height": "2", "as": "geometry"})
            cellroot.append(port)
            edge = current["f4"]
            edge.set("target", "e2_f4_port")
            edge.set("style", edge.get("style").replace("entryX=0.5;entryY=0;", "entryX=0.5;entryY=0.5;entryPerimeter=0;"))
            points = ET.SubElement(edge.find("mxGeometry"), "Array", {"as": "points"})
            for x, y in ((420, 527), (420, 655)):
                ET.SubElement(points, "mxPoint", {"x": str(x), "y": str(y)})

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
