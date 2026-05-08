// LKH centrifugal-pump example for the Anchor canvas demo (Phase 1).
// Authored for the anchor_sysml extension test suite.
package PumpEquipment {

    part def FluidPort;

    part def Pump {
        doc /* Centrifugal pump abstract definition.
             * Concrete model variants specialise this with concrete values.
             */
        attribute max_inlet_pressure : Real;
        attribute max_temperature    : Real;
        attribute flow_rate          : Real;

        in  port inlet  : FluidPort;
        out port outlet : FluidPort;

        metadata {
            @iso15926-uri = "http://data.posccaesar.org/rdl/RDS415644";
        }
    }

    part def LKH5 :> Pump {
        attribute flow_rate          = 5.0;
        attribute max_inlet_pressure = 4.0;
        attribute max_temperature    = 95.0;
    }

    part def LKH10 :> Pump {
        attribute flow_rate          = 10.0;
        attribute max_inlet_pressure = 5.0;
        attribute max_temperature    = 95.0;
    }

    part def LKH70 :> Pump {
        attribute flow_rate          = 70.0;
        attribute max_inlet_pressure = 7.0;
        attribute max_temperature    = 110.0;
    }

    requirement def MaxPressure {
        subject p : Pump;
        assert constraint {
            p.max_inlet_pressure <= 7.0
        }
    }
}
