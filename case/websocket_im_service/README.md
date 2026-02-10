# WebSocket IM Service

This is a simple WebSocket IM server with a built-in UI.

## Endpoints

- `GET /` UI page
- `GET /health` health check
- `GET /ws` WebSocket endpoint

## Message Protocols

### UI/Generic clients (chat protocol)

**Client → Server**
```json
{"type":"chat","name":"user","room":"lobby","role":"user","content":"hello"}
```

**Server → Client**
```json
{"type":"chat","id":"<client_id>","name":"user","role":"user","room":"lobby","content":"hello","timestamp":"..."}
```

### Nanobot (message protocol)

**Nanobot → Server**
```json
{"type":"message","sender_id":"nanobot","chat_id":"lobby","content":"hello","media_base64":["data:image/png;base64,..."]}
```

## Run

```pwsh
python -m case.websocket_im_service.server
```

## ws_client config options

`ws_client` can send base64-encoded images from `media` paths:

```json
{
	"channels": {
		"wsClient": {
			"enabled": true,
			"sendMediaBase64": true,
			"mediaMaxBytes": 2097152
		}
	}
}
```
