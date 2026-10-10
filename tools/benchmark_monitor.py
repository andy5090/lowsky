"""Measure local synthetic state generation and serialization, not sensor accuracy."""
import argparse
import json
import platform
import statistics
import time

try:
    from .monitor_server import Simulation
except ImportError:
    from monitor_server import Simulation


def benchmark(iterations=30):
    if not 1 <= iterations <= 1000:
        raise ValueError('Iterations must be 1-1000')
    simulation = Simulation()
    simulation.control({'action': 'case', 'case_id': 'case_003'})
    simulation.control({'action': 'seek', 'at_ms': 180000})
    timings = []
    for _ in range(iterations):
        started = time.perf_counter()
        state = simulation.state()
        encoded = json.dumps(state, ensure_ascii=False).encode()
        timings.append((time.perf_counter() - started) * 1000)
    return {'case_id': 'case_003', 'at_ms': 180000, 'synthetic': True,
            'received_tracks': len(state['tracks']), 'virtual_endpoints': state['sensor_fleet']['total'],
            'iterations': iterations, 'median_ms': round(statistics.median(timings), 2),
            'max_ms': round(max(timings), 2), 'payload_bytes': len(encoded),
            'python': platform.python_version(), 'platform': platform.system(),
            'scope': 'Simulation.state plus JSON serialization; excludes HTTP, browser, Godot rendering and LLM latency',
            'detection_accuracy': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.iterations), indent=2))
