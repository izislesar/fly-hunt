# Fantasy physics scale table (Task 8, frozen seed values)

Source: CrossFlySimulation (per plan execution strategy).
Scope ref: gravity -9.81, timestep 0.0005 s, solver iter 100,
contact solref [2e-4, 1e3], solimp [0.999, 0.9999, 1e-3, 0.5, 2.0].

## Bodies

| body | mass_kg | size_note | volume_m3 |
|------|---------|-----------|-----------|
| fly | 1e-6 | wingspan 3mm | n/a (point-scale flyer) |
| moose-box | 0.5 | ~0.4 m box edge (~0.05 m3) | 0.05 |

- fly mass: 1e-6 kg
- fly wingspan: 3mm
- moose-box mass: 0.5 kg
- moose-box volume: 0.05 m3

## Solver / integration

| param | value |
|-------|-------|
| gravity | -9.81 |
| dt (timestep) | 0.0005 s |
| iterations (solver iter) | 100 |
| solref | [2e-4, 1e3] |
| solimp | [0.999, 0.9999, 1e-3, 0.5, 2.0] |

- gravity: -9.81
- dt: 0.0005
- iterations: 100
- solref: [2e-4, 1e3]
- solimp: [0.999, 0.9999, 1e-3, 0.5, 2.0]

## Fantasy scale statement (1:100)

Real moose reference: moose ~500 kg / ~3 m body length.
Arena moose-box: 0.5 kg / ~0.4 m box (~0.05 m3) representing 1:100
fantasy scale vs the real animal. The fly (1e-6 kg, 3 mm wingspan)
hunts the box-moose at this 1:100 fantasy scale; masses and sizes
are seed gameplay values, not physically consistent scalings.

- scale: 1:100
- real-moose: ~500kg / ~3m

## Fudge flags (recovery, default OFF)

Allowed QA-fail remediation flags, all default OFF. Enable only when
`tools/check_physics.py` reports instability, and record which flag
was used in `out/fail_physics.log`.

| flag | effect | default |
|------|--------|---------|
| REDUCED_DT | halve dt 0.0005 -> 0.00025 | OFF |
| INCREASED_ITER | iterations 100 -> 200 | OFF |
| CONTACT_STIFFNESS_SCALE | scale solref[0] down x0.5 (softer contact) | OFF |
| CONTACT_DAMPING_SCALE | scale solref[1] up x2.0 (more damping) | OFF |
| GRAVITY_CLAMP | clamp gravity to [-9.81, 0] on NaN guard | OFF |

## Checker

`python tools/check_physics.py --steps 500` → exit 0 + `no NaN in 500 steps`.
Cross-checks `arena/hunt_arena.xml` option attributes when present
(Task 7 builds it in parallel; absent → inline minimal-model values).
