"""Select an available local port without stopping other applications."""
import argparse
import errno
import socket


def choose_port(start=8501):
    if not 1 <= start <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    for port in range(start, min(start + 100, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    continue
                raise
            return port
    raise RuntimeError('No available port found. Try PORT=9000 ./run.sh')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('start', nargs='?', type=int, default=8501)
    args = parser.parse_args()
    try:
        print(choose_port(args.start))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f'Cannot select a port: {exc}\n')
