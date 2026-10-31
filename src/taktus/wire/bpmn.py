"""BPMN 2.0 process models as XML, read into a neutral graph and written from one (ADR-0168).

BPMN is the open standard for process models (ISO/IEC 19510). This module knows its elements and
nothing of Taktus's processes: `read` turns a document into one `Model` per `process` element —
its nodes, sequence flows and lanes — and `write` turns a `Model` into a document, with a
diagram a BPMN tool can show without laying it out. What a model means for Taktus is the process
component's (`process/domain/service/interchange.py`).

Reading is defused (ADR-0168 §2). The standard library's `expat` parser is driven directly: a
document type declaration, an entity declaration and an external entity reference each stop the
parse, parameter entities are never parsed, and a document larger than `MAX_BYTES` is refused
before parsing. Nothing the document refers to is read.

The extension elements of the namespace `EXTENSION` carry what Taktus adds to a task, a lane and
a process: plain attributes and a text, read back as `Node.extension`, `Lane.extension` and
`Model.extension`.
"""

from __future__ import annotations

import json
import xml.parsers.expat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL"
DI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DD = "http://www.omg.org/spec/DD/20100524/DI"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
EXTENSION = "urn:taktus:bpmn:1"
"""The namespace of what Taktus adds to an element it writes."""
WHEN = "urn:taktus:when:1"
"""The expression language of a condition Taktus wrote: a JSON list of conditions (ADR-0088)."""

MAX_BYTES = 10 * 1024 * 1024
"""The largest document read. A process model is far smaller; a larger one is refused."""

TASKS = frozenset(
    {
        "task",
        "userTask",
        "manualTask",
        "serviceTask",
        "sendTask",
        "receiveTask",
        "scriptTask",
        "businessRuleTask",
        "callActivity",
        "subProcess",
        "adHocSubProcess",
        "transaction",
    }
)
GATEWAYS = frozenset(
    {
        "exclusiveGateway",
        "inclusiveGateway",
        "parallelGateway",
        "eventBasedGateway",
        "complexGateway",
    }
)
EVENTS = frozenset(
    {
        "startEvent",
        "endEvent",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "boundaryEvent",
    }
)
PERFORMERS = frozenset({"humanPerformer", "potentialOwner", "performer"})
"""Elements that assign a task to someone. Never read into a model (ADR-0168 §3)."""
UNREAD = frozenset(
    {"dataObject", "dataObjectReference", "dataStoreReference", "textAnnotation", "association"}
)


class Unreadable(Exception):
    """A document that is no BPMN model this reader reads, or one it refuses."""


@dataclass(frozen=True)
class Node:
    """A task, a gateway or an event of a process."""

    id: str
    element: str
    """The BPMN element's local name: `userTask`, `exclusiveGateway`, `startEvent`, …"""
    name: str | None = None
    default: str | None = None
    """A gateway's default flow, by its id."""
    attached_to: str | None = None
    """A boundary event's task, by its id."""
    definitions: tuple[str, ...] = ()
    """An event's definitions, by local name: `timerEventDefinition`, …"""
    performers: tuple[str, ...] = ()
    """The performer elements a task carried, by local name; their content is not read."""
    extension: Mapping[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        if self.element in TASKS:
            return "task"
        if self.element in GATEWAYS:
            return "gateway"
        return "event"


@dataclass(frozen=True)
class Flow:
    """A sequence flow, with its condition where it carries one."""

    id: str
    source: str
    target: str
    condition: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class Lane:
    """A lane, with the nodes in it, by id."""

    id: str
    name: str | None
    nodes: tuple[str, ...]
    extension: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Model:
    """One `process` element of a document."""

    id: str
    name: str | None
    nodes: tuple[Node, ...]
    flows: tuple[Flow, ...]
    lanes: tuple[Lane, ...] = ()
    extension: Mapping[str, str] = field(default_factory=dict)
    unread: tuple[str, ...] = ()
    """What the document held in this process that is not read, one line each."""


# Reading ------------------------------------------------------------------------------------


def _parse(data: bytes) -> ET.Element:
    if len(data) > MAX_BYTES:
        raise Unreadable(f"the model is larger than {MAX_BYTES} bytes and is not read")
    builder = ET.TreeBuilder()
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")

    def refuse(what: str) -> None:
        raise Unreadable(f"the model declares {what}; a model with one is not read (ADR-0168 §2)")

    def doctype(*_: object) -> None:
        refuse("a document type")

    def entity(*_: object) -> None:
        refuse("an entity")

    def external(*_: object) -> int:
        refuse("a reference to an external entity")
        return 0

    def start(tag: str, attributes: dict[str, str]) -> None:
        builder.start(_qualified(tag), {_qualified(k): v for k, v in attributes.items()})

    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    parser.UnparsedEntityDeclHandler = entity
    parser.ExternalEntityRefHandler = external
    parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: builder.end(_qualified(tag))
    parser.CharacterDataHandler = builder.data
    try:
        parser.Parse(data, True)
    except xml.parsers.expat.ExpatError as error:
        raise Unreadable(f"the model is not well-formed XML: {error}") from None
    return builder.close()


def _qualified(tag: str) -> str:
    return "{" + tag if "}" in tag else tag


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ns(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def read(data: bytes) -> tuple[Model, ...]:
    """Every process of the document, in document order. Raises `Unreadable`."""
    root = _parse(data)
    if _ns(root.tag) != MODEL or _local(root.tag) != "definitions":
        raise Unreadable("the document is no BPMN 2.0 model: its root is not `definitions`")
    return tuple(_process(p) for p in root if _ns(p.tag) == MODEL and _local(p.tag) == "process")


def _extension(element: ET.Element, name: str) -> dict[str, str]:
    for holder in element:
        if _ns(holder.tag) == MODEL and _local(holder.tag) == "extensionElements":
            for item in holder:
                if _ns(item.tag) == EXTENSION and _local(item.tag) == name:
                    found = dict(item.attrib)
                    if item.text and item.text.strip():
                        found["text"] = item.text.strip()
                    return found
    return {}


def _process(process: ET.Element) -> Model:
    nodes: list[Node] = []
    flows: list[Flow] = []
    lanes: list[Lane] = []
    unread: list[str] = []
    for element in process:
        if _ns(element.tag) != MODEL:
            continue
        local = _local(element.tag)
        identifier = element.get("id", "")
        if local == "sequenceFlow":
            expression = next(
                (
                    c
                    for c in element
                    if _ns(c.tag) == MODEL and _local(c.tag) == "conditionExpression"
                ),
                None,
            )
            flows.append(
                Flow(
                    id=identifier,
                    source=element.get("sourceRef", ""),
                    target=element.get("targetRef", ""),
                    condition=None
                    if expression is None
                    else (expression.text or "").strip() or None,
                    language=None if expression is None else expression.get("language"),
                )
            )
        elif local == "laneSet":
            lanes.extend(_lanes(element))
        elif local in TASKS or local in GATEWAYS or local in EVENTS:
            nodes.append(_node(element, local))
            if local in {"subProcess", "adHocSubProcess", "transaction"} and any(
                _ns(c.tag) == MODEL
                and _local(c.tag) not in {"incoming", "outgoing"}
                and _local(c.tag) != "extensionElements"
                for c in element
            ):
                unread.append(f"the inside of the sub-process {identifier!r}: it is one step")
        elif local in UNREAD or local in {"documentation", "extensionElements"}:
            continue
        else:
            unread.append(f"the element {local} {identifier!r}")
    return Model(
        id=process.get("id", ""),
        name=process.get("name"),
        nodes=tuple(nodes),
        flows=tuple(flows),
        lanes=tuple(lanes),
        extension=_extension(process, "process"),
        unread=tuple(unread),
    )


def _node(element: ET.Element, local: str) -> Node:
    children = [c for c in element if _ns(c.tag) == MODEL]
    return Node(
        id=element.get("id", ""),
        element=local,
        name=(element.get("name") or "").strip() or None,
        default=element.get("default"),
        attached_to=element.get("attachedToRef"),
        definitions=tuple(
            _local(c.tag) for c in children if _local(c.tag).endswith("EventDefinition")
        ),
        performers=tuple(_local(c.tag) for c in children if _local(c.tag) in PERFORMERS),
        extension=_extension(element, "step"),
    )


def _lanes(lane_set: ET.Element) -> list[Lane]:
    """The innermost lanes: a lane with lanes inside it gives its nodes to them."""
    found: list[Lane] = []
    for lane in lane_set:
        if _ns(lane.tag) != MODEL or _local(lane.tag) != "lane":
            continue
        inner = [c for c in lane if _ns(c.tag) == MODEL and _local(c.tag) == "childLaneSet"]
        nested = [n for child in inner for n in _lanes(child)]
        refs = tuple(
            (c.text or "").strip()
            for c in lane
            if _ns(c.tag) == MODEL and _local(c.tag) == "flowNodeRef" and (c.text or "").strip()
        )
        if nested:
            found.extend(nested)
            held = {n for lane_ in nested for n in lane_.nodes}
            rest = tuple(r for r in refs if r not in held)
            if not rest:
                continue
            refs = rest
        found.append(
            Lane(
                id=lane.get("id", ""),
                name=(lane.get("name") or "").strip() or None,
                nodes=refs,
                extension=_extension(lane, "lane"),
            )
        )
    return found


# Writing ------------------------------------------------------------------------------------

WIDTH, HEIGHT, GAP_X, GAP_Y, LANE_HEAD = 120, 80, 60, 40, 30
SIZES = {"task": (WIDTH, HEIGHT), "gateway": (50, 50), "event": (36, 36)}


def write(model: Model) -> bytes:
    """The model as a BPMN 2.0 document, with a collaboration of one participant and a diagram."""
    for prefix, uri in (("bpmn", MODEL), ("bpmndi", DI), ("dc", DC), ("di", DD), ("xsi", XSI)):
        ET.register_namespace(prefix, uri)
    ET.register_namespace("taktus", EXTENSION)
    q = _q
    root = ET.Element(
        q(MODEL, "definitions"),
        {"id": f"definitions-{model.id}", "targetNamespace": EXTENSION, "exporter": "Taktus"},
    )
    collaboration = ET.SubElement(
        root, q(MODEL, "collaboration"), {"id": f"collaboration-{model.id}"}
    )
    participant = ET.SubElement(
        collaboration,
        q(MODEL, "participant"),
        {"id": f"participant-{model.id}", "name": model.name or model.id, "processRef": model.id},
    )
    attributes = {"id": model.id, "isExecutable": "false"}
    if model.name:
        attributes["name"] = model.name
    process = ET.SubElement(root, q(MODEL, "process"), attributes)
    _write_extension(process, "process", model.extension)
    if model.lanes:
        lane_set = ET.SubElement(process, q(MODEL, "laneSet"), {"id": f"lanes-{model.id}"})
        for lane in model.lanes:
            element = ET.SubElement(lane_set, q(MODEL, "lane"), _named(lane.id, lane.name))
            _write_extension(element, "lane", lane.extension)
            for ref in lane.nodes:
                ET.SubElement(element, q(MODEL, "flowNodeRef")).text = ref
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for flow in model.flows:
        outgoing.setdefault(flow.source, []).append(flow.id)
        incoming.setdefault(flow.target, []).append(flow.id)
    for node in model.nodes:
        attributes = _named(node.id, node.name)
        if node.default:
            attributes["default"] = node.default
        element = ET.SubElement(process, q(MODEL, node.element), attributes)
        _write_extension(element, "step", node.extension)
        for ref in incoming.get(node.id, ()):
            ET.SubElement(element, q(MODEL, "incoming")).text = ref
        for ref in outgoing.get(node.id, ()):
            ET.SubElement(element, q(MODEL, "outgoing")).text = ref
    for flow in model.flows:
        element = ET.SubElement(
            process,
            q(MODEL, "sequenceFlow"),
            {"id": flow.id, "sourceRef": flow.source, "targetRef": flow.target},
        )
        if flow.condition is not None:
            expression = ET.SubElement(
                element,
                q(MODEL, "conditionExpression"),
                {q(XSI, "type"): "bpmn:tFormalExpression"},
            )
            if flow.language:
                expression.set("language", flow.language)
            expression.text = flow.condition
    _diagram(root, model, participant.get("id", ""))
    ET.indent(root, space="  ")
    written: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return written


def _q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _named(identifier: str, name: str | None) -> dict[str, str]:
    return {"id": identifier, "name": name} if name else {"id": identifier}


def _write_extension(element: ET.Element, name: str, values: Mapping[str, str]) -> None:
    if not values:
        return
    holder = ET.SubElement(element, _q(MODEL, "extensionElements"))
    attributes = {k: v for k, v in sorted(values.items()) if k != "text"}
    item = ET.SubElement(holder, _q(EXTENSION, name), attributes)
    if "text" in values:
        item.text = values["text"]


def _diagram(root: ET.Element, model: Model, participant: str) -> None:
    """Columns by depth in the graph, rows by lane (ADR-0168 §5)."""
    depth = _depths(model)
    lane_of = {n: lane.id for lane in model.lanes for n in lane.nodes}
    bands = [lane.id for lane in model.lanes] or [""]
    rows: dict[tuple[str, int], int] = {}
    place: dict[str, tuple[str, int, int]] = {}
    for node in model.nodes:
        band = lane_of.get(node.id, bands[0])
        column = depth.get(node.id, 0)
        row = rows.get((band, column), 0)
        rows[(band, column)] = row + 1
        place[node.id] = (band, column, row)
    band_rows = {b: max((r for (bb, _), r in rows.items() if bb == b), default=1) for b in bands}
    band_top: dict[str, int] = {}
    top = 0
    for band in bands:
        band_top[band] = top
        top += band_rows[band] * (HEIGHT + GAP_Y) + GAP_Y
    columns = max(depth.values(), default=0) + 1
    width = LANE_HEAD + GAP_X + columns * (WIDTH + GAP_X)
    diagram = ET.SubElement(root, _q(DI, "BPMNDiagram"), {"id": f"diagram-{model.id}"})
    plane = ET.SubElement(
        diagram, _q(DI, "BPMNPlane"), {"id": f"plane-{model.id}", "bpmnElement": participant}
    )
    _shape(plane, participant, 0, 0, width, top, horizontal=True)
    for lane in model.lanes:
        height = band_rows[lane.id] * (HEIGHT + GAP_Y) + GAP_Y
        _shape(
            plane, lane.id, LANE_HEAD, band_top[lane.id], width - LANE_HEAD, height, horizontal=True
        )
    centre: dict[str, tuple[int, int]] = {}
    kinds = {node.id: node.kind for node in model.nodes}
    for node in model.nodes:
        band, column, row = place[node.id]
        w, h = SIZES[kinds[node.id]]
        cx = LANE_HEAD + GAP_X + column * (WIDTH + GAP_X) + WIDTH // 2
        cy = band_top[band] + GAP_Y + row * (HEIGHT + GAP_Y) + HEIGHT // 2
        centre[node.id] = (cx, cy)
        _shape(plane, node.id, cx - w // 2, cy - h // 2, w, h)
    for flow in model.flows:
        if flow.source not in centre or flow.target not in centre:
            continue
        edge = ET.SubElement(
            plane, _q(DI, "BPMNEdge"), {"id": f"{flow.id}-di", "bpmnElement": flow.id}
        )
        (x1, y1), (x2, y2) = centre[flow.source], centre[flow.target]
        points = (
            [(x1, y1), (x2, y2)]
            if y1 == y2
            else [(x1, y1), ((x1 + x2) // 2, y1), ((x1 + x2) // 2, y2), (x2, y2)]
        )
        for x, y in points:
            ET.SubElement(edge, _q(DD, "waypoint"), {"x": str(x), "y": str(y)})


def _shape(
    plane: ET.Element, element: str, x: int, y: int, w: int, h: int, *, horizontal: bool = False
) -> None:
    attributes = {"id": f"{element}-di", "bpmnElement": element}
    if horizontal:
        attributes["isHorizontal"] = "true"
    shape = ET.SubElement(plane, _q(DI, "BPMNShape"), attributes)
    ET.SubElement(
        shape, _q(DC, "Bounds"), {"x": str(x), "y": str(y), "width": str(w), "height": str(h)}
    )


def _depths(model: Model) -> dict[str, int]:
    """The longest path from a node without incoming flows to each node."""
    before: dict[str, list[str]] = {n.id: [] for n in model.nodes}
    for flow in model.flows:
        if flow.target in before and flow.source in before:
            before[flow.target].append(flow.source)
    depth: dict[str, int] = {}

    def of(node: str, seen: frozenset[str]) -> int:
        if node in depth:
            return depth[node]
        found = max((of(b, seen | {node}) + 1 for b in before[node] if b not in seen), default=0)
        depth[node] = found
        return found

    for node in before:
        of(node, frozenset())
    return depth


def conditions_text(conditions: Sequence[Mapping[str, object]]) -> str:
    """Conditions as the text of a condition expression in the language `WHEN`."""
    return json.dumps(list(conditions), sort_keys=True, separators=(",", ":"))
