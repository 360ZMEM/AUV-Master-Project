# PC104 firmware echo timing

- Source bundle: `/Users/bytedance/coding/AUV-Master-Project/results/control/pc104_udp_timing_echo_300s_20260822`
- Downlink/uplink frames: `3000`/`4505`
- Parse errors: `0`
- Forward sequence gaps / estimated lost uplinks: `0`/`0`
- Unique/paired firmware receive events: `1002`/`1001`
- First-echo RTT p50/p95/p99/p99.9: `264.678`/`313.965`/`315.607`/`316.536 ms`
- PC104 receive-to-first-pack p50/p95/p99/p99.9: `16.000`/`16.000`/`16.000`/`16.000 ms`
- Valid DVL device timestamps: `0`
- PC104 relative clock rate offset: `961.967 ppm`
- Clock-fit absolute residual p95: `0.774 ms`

Boundary: first-echo RTT is an application-path round trip. It is not a synchronized one-way physical latency.
