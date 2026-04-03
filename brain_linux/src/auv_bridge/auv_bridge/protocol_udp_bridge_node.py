#!/usr/bin/env python3
from __future__ import annotations

from .bridge_node import main as run_bridge_main


def main(args=None) -> None:
    run_bridge_main(args=args, preferred_backend='protocol_udp', node_name='protocol_udp_bridge_node')