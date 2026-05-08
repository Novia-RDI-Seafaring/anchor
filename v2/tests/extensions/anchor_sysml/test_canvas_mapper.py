"""IR → CanvasBatch mapping checks."""
from __future__ import annotations

from anchor.extensions.anchor_sysml.infra.canvas_mapper import SysmlCanvasMapper
from anchor.extensions.anchor_sysml.infra.parser import parse_text


def _map(text: str):
    ir = parse_text(text)
    return SysmlCanvasMapper().map(ir)


def test_package_emits_sysml_package_node():
    batch = _map("package P {}")
    pkgs = [n for n in batch.nodes if n.node_type == "sysml:package"]
    assert len(pkgs) == 1
    assert pkgs[0].label == "P"
    assert pkgs[0].data["qualified_name"] == "P"


def test_part_def_emits_sysml_block_with_full_data_shape():
    batch = _map(
        """
        package P {
            part def Pump {
                attribute flow_rate : Real = 5.0;
                in port inlet : FluidPort;
            }
        }
        """
    )
    blocks = [n for n in batch.nodes if n.node_type == "sysml:block"]
    assert len(blocks) == 1
    data = blocks[0].data
    assert data["kind"] == "block-def"
    assert data["short_name"] == "Pump"
    assert data["qualified_name"].endswith("Pump")
    assert any(a["name"] == "flow_rate" for a in data["attributes"])
    assert any(p["name"] == "inlet" and p["direction"] == "in" for p in data["ports"])


def test_inheritance_edge_marker():
    batch = _map(
        """
        package P {
            part def Pump;
            part def LKH5 :> Pump;
        }
        """
    )
    edges = [e for e in batch.edges if e.data.get("marker") == "inheritance"]
    assert len(edges) == 1


def test_satisfy_edge_marker():
    batch = _map(
        """
        package SA {
            part def Drone;
            part drone : Drone;
            requirement longDistance;
            satisfy longDistance by drone;
        }
        """
    )
    edges = [e for e in batch.edges if e.data.get("marker") == "satisfy"]
    assert len(edges) == 1


def test_interface_edge_is_anchored():
    batch = _map(
        """
        package L {
            part def Frigate {
                part hull : Hull;
                ref part laser : Laser;
                interface highSlot1 : HighSlot connect
                    hp ::> hull.highSlot1 to
                    mp ::> laser.highSlot;
            }
        }
        """
    )
    iface_edges = [e for e in batch.edges if e.data.get("marker") == "interface-connection"]
    assert len(iface_edges) == 1
    assert iface_edges[0].edge_type == "anchored"
    assert iface_edges[0].label == "highSlot1"


def test_requirement_node_carries_req_id_and_asserts():
    batch = _map(
        """
        package R {
            requirement <'REQ-9942'> totalMass {
                subject drone : Drone;
                assert constraint { drone.totalMass <= 750 }
            }
        }
        """
    )
    reqs = [n for n in batch.nodes if n.node_type == "sysml:requirement"]
    assert len(reqs) == 1
    data = reqs[0].data
    assert data["req_id"] == "REQ-9942"
    assert any("750" in a for a in data["asserts"])
    assert "drone" in (data["subject"] or "")


def test_subject_edge_marker():
    batch = _map(
        """
        package R {
            part def Drone;
            part drone : Drone;
            requirement totalMass {
                subject drone : Drone;
            }
        }
        """
    )
    sub_edges = [e for e in batch.edges if e.data.get("marker") == "subject"]
    assert len(sub_edges) == 1


def test_grid_layout_offsets_applied():
    batch = SysmlCanvasMapper().map(
        parse_text("package A {} package B {} package C {}"),
        x_offset=1000,
        y_offset=500,
    )
    xs = [n.x for n in batch.nodes if n.node_type == "sysml:package"]
    # Three top-level packages, all wrapped to row 0 (under GRID_COLS=4):
    assert all(x >= 1000 for x in xs)
    assert all(n.y == 500 for n in batch.nodes if n.node_type == "sysml:package")


def test_typed_as_emits_association_edge():
    batch = _map(
        """
        package P {
            part def Drone;
            part drone : Drone;
        }
        """
    )
    assoc = [e for e in batch.edges if e.data.get("marker") == "association"]
    assert len(assoc) == 1


def test_metadata_passthrough_in_block_data():
    batch = _map(
        """
        package P {
            part def Pump {
                metadata { @iso15926-uri = "http://x"; }
            }
        }
        """
    )
    blocks = [n for n in batch.nodes if n.node_type == "sysml:block"]
    assert blocks[0].data["metadata"].get("@iso15926-uri")
