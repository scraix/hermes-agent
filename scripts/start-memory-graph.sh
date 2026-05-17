#!/bin/bash
# Start Memory Graph dashboard server
set -e
cd /root/.hermes/hermes-agent
exec ~/.hermes/hermes-agent/venv/bin/python3 -m agent.memory_graph.server --port 8900 --host 127.0.0.1
