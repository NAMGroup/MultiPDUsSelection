# MultiPDUsSelection — UE-Driven Latency-Aware Slice Selection

A UE-side system for 5G network slicing that keeps a device's traffic on the
best-performing slice. Multiple PDU sessions are established simultaneously, one
per slice. Per-slice latency is measured continuously, and the default route is
updated to whichever interface meets the application's latency requirements,  without
releasing and re-establishing PDU sessions.

Tested on a Raspberry Pi 4 with a Quectel RM520N-GL modem on an Amarisoft
5G SA core, using Linux policy-based routing and QMI/QMAP for multi-PDU session
management.

## Repository contents

| File / folder                  | What it is                                              |
|--------------------------------|---------------------------------------------------------|
| `PoC_slice_selector/Get_interface_latency.py` | Measures per-interface latency |
| `PoC_slice_selector/Interface_Selector_Latency.py` | Switches the default route based on latency requirements       |
| `slice_selection.md`           | Guide on how to establish the multi-slice PDU sessions           |
| `slice_switching_experiments/` | Switching-delay results: `multi_pdu_switching/` and `sequential_switching/` |



## Slice setup — `slice_selection.md`

Step-by-step guide for bringing up the simultaneous multi-slice PDU sessions on
the UE: establishing one PDU session per slice, the QMI/QMAP configuration, and
the Linux policy-based routing. Read this first — the runtime engine assumes these sessions are
already up.

## Experiments — `slice_switching_experiments/`

Switching-delay measurements comparing the two strategies:

- **Sequential** — the active PDU session is fully released before a new one is
  established on another slice, which exposes a visible service interruption.
- **Multi-PDU** — all sessions stay up and traffic is re-steered between them.

Results are split into one subfolder per strategy:

- `multi_pdu_switching/`
- `sequential_switching/`

Each holds 10 trials, `TEST1`–`TEST10`, and every trial has two logs:

- `ping_<STRATEGY>_TEST<N>.log` — continuous `ping` output for the trial. The
  service-interruption duration is derived from the gap in ICMP sequence
  numbers during the switch.
- `switch_events_<STRATEGY>_TEST<N>.log` — timestamped switch events (round
  start/stop markers) recording when the switch was issued and completed.

The two log types together give the two halves of the delay: the switch-events
log gives the command-level timing, and the ping log gives the actual outage
seen by the application.
