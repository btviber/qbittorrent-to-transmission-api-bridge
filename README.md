# qBittorrent to Transmission RPC Bridge

A bridge that lets Transmission-compatible apps work with qBittorrent.

## Usage

```bash
python3 bridge.py [options]
```

### Options

- `-h, --help` - Show help message
- `-v` - Show RPC operations (client actions)
- `-vv` - Show cache hits/misses and API calls (performance monitoring)
- `-vvv` - Show everything (sync changes, arguments, all details)
- `--host HOST` - Host to bind to (default: 0.0.0.0)
- `--port PORT` - Port to listen on (default: 9091)
- `--username USERNAME` - Username for authentication (optional)
- `--password PASSWORD` - Password for authentication (optional)

### Examples

```bash
# Start with defaults
python3 bridge.py

# Start with logging
python3 bridge.py -v

# With authentication
python3 bridge.py --username admin --password secret

# Custom port
python3 bridge.py --port 9092
```

## Setup

1. Enable qBittorrent Web UI
2. Run the bridge
3. Point your Transmission app to `http://localhost:9091`
