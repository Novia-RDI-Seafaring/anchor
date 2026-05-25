"""Recursive-descent parser tests against the Phase-1 SysML v2 subset."""
from __future__ import annotations

from pathlib import Path

from anchor.extensions.anchor_sysml.infra.parser import parse_text


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_empty_package():
    ir = parse_text("package P {}")
    assert len(ir.packages) == 1
    assert ir.packages[0].short_name == "P"
    assert ir.packages[0].blocks == []


def test_parse_part_def_with_attribute_and_default():
    ir = parse_text(
        """
        package P {
            part def Pump {
                attribute flow_rate : Real = 5.0;
            }
        }
        """
    )
    blk = ir.packages[0].blocks[0]
    assert blk.kind == "block-def"
    assert blk.short_name == "Pump"
    assert len(blk.attributes) == 1
    attr = blk.attributes[0]
    assert attr.name == "flow_rate"
    assert attr.type == "Real"
    assert attr.default == "5.0"


def test_parse_part_usage_with_typing_and_nested_part():
    ir = parse_text(
        """
        package SystemArchitecture {
            part drone : Drone {
                attribute totalMass = 750;
                part battery {
                    attribute capacity = 6000;
                }
            }
        }
        """
    )
    blk = ir.packages[0].blocks[0]
    assert blk.kind == "block-usage"
    assert blk.short_name == "drone"
    assert blk.typed_as == "Drone"
    assert {a.name for a in blk.attributes} == {"totalMass"}
    assert {p.name for p in blk.parts} == {"battery"}


def test_parse_port_directions():
    ir = parse_text(
        """
        package P {
            part def Pump {
                in  port inlet  : FluidPort;
                out port outlet : FluidPort;
                inout port both : FluidPort;
            }
        }
        """
    )
    ports = ir.packages[0].blocks[0].ports
    by_name = {p.name: p for p in ports}
    assert by_name["inlet"].direction == "in"
    assert by_name["outlet"].direction == "out"
    assert by_name["both"].direction == "inout"
    assert all(p.type == "FluidPort" for p in ports)


def test_parse_requirement_with_subject_and_assert():
    ir = parse_text(
        """
        package R {
            requirement <'REQ-9942'> totalMass {
                subject drone : Drone;
                assert constraint {
                    drone.totalMass <= 750
                }
            }
        }
        """
    )
    req = ir.packages[0].requirements[0]
    assert req.short_name == "totalMass"
    assert req.req_id == "REQ-9942"
    assert "drone" in (req.subject or "")
    assert any("750" in a for a in req.asserts)


def test_parse_satisfy_clause():
    ir = parse_text(
        """
        package SA {
            part drone : Drone;
            satisfy Drone_StakeholderRequirements::longDistance by drone;
        }
        """
    )
    sats = ir.packages[0].satisfies
    assert len(sats) == 1
    assert sats[0].requirement.endswith("longDistance")
    assert sats[0].by == "drone"


def test_parse_interface_connect_to():
    ir = parse_text(
        """
        package L {
            part def MiningFrigate {
                part hull : Hull;
                ref part miningLaser : Laser;
                interface highSlotInterface1 : HighSlotInterface connect
                    hullPort ::> hull.highSlot1 to
                    modulePort ::> miningLaser.highSlot;
            }
        }
        """
    )
    blk = ir.packages[0].blocks[0]
    assert len(blk.interfaces) == 1
    iface = blk.interfaces[0]
    assert iface.name == "highSlotInterface1"
    assert iface.type == "HighSlotInterface"
    assert "hull.highSlot1" == iface.end_a
    assert "miningLaser.highSlot" == iface.end_b


def test_parse_specialization_chain():
    ir = parse_text("package P { part def LKH5 :> Pump; }")
    blk = ir.packages[0].blocks[0]
    assert blk.specializes == ["Pump"]


def test_parse_metadata_passthrough():
    ir = parse_text(
        """
        package P {
            part def Pump {
                metadata {
                    @iso15926-uri = "http://data.posccaesar.org/rdl/RDS415644";
                }
            }
        }
        """
    )
    blk = ir.packages[0].blocks[0]
    assert "@iso15926-uri" in blk.metadata
    assert "RDS415644" in blk.metadata["@iso15926-uri"]


def test_skipped_constructs_emit_diagnostics_not_errors():
    ir = parse_text(
        """
        package P {
            part def Frigate {
                action engageDefenses;
                state docked {}
            }
        }
        """
    )
    # Block parsed fine; diagnostics surfaced for action + state.
    blk = ir.packages[0].blocks[0]
    assert blk.short_name == "Frigate"
    messages = " ".join(d.message for d in ir.diagnostics)
    assert "action" in messages
    assert "state" in messages


def test_parse_drone_base_architecture_fixture():
    text = (FIXTURES / "drone_base_architecture.sysml").read_text()
    ir = parse_text(text, filename="drone_base_architecture.sysml")
    pkg_names = [p.short_name for p in ir.packages]
    assert "Drone_BaseArchitecture" in pkg_names
    assert "Drone_StakeholderRequirements" in pkg_names
    assert "Drone_SystemArchitecture" in pkg_names
    assert "Drone_SystemRequirements" in pkg_names

    sa = next(p for p in ir.packages if p.short_name == "Drone_SystemArchitecture")
    assert {b.short_name for b in sa.blocks} == {"drone"}
    assert any(s.requirement.endswith("longDistance") for s in sa.satisfies)

    stake = next(p for p in ir.packages if p.short_name == "Drone_StakeholderRequirements")
    req_names = {r.short_name for r in stake.requirements}
    assert "longDistance" in req_names

    sysreqs = next(p for p in ir.packages if p.short_name == "Drone_SystemRequirements")
    by_id = {r.req_id: r for r in sysreqs.requirements if r.req_id}
    assert "REQ-9942" in by_id
    assert "REQ-9943" in by_id
    assert "REQ-9944" in by_id
