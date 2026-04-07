# ResonantOS Build Log

## Additional Bugs Found (2026-04-02)

### Bug 8: OpenClaw sub-agents require explicit Ollama auth profile
When switching a sub-agent (e.g. setup agent) from Anthropic to Ollama,
the sub-agent's auth-profiles.json must contain an explicit Ollama entry:
```json
"ollama:default": { "type": "api_key", "provider": "ollama", "key": "ollama" }
```
Without this, sub-agents fail with "No API key found for provider ollama"
even though the main agent handles keyless Ollama correctly.
**Fix:** Add ollama:default profile to each sub-agent's auth-profiles.json.

### Bug 9: Setup agent model not updated when gateway primary model changes
The model set for the setup agent (`agents.list[].model` in openclaw.json)
is independent of `agents.defaults.model.primary`. Switching the primary
gateway model to `ollama/qwen3:14b` does not cascade to the setup agent —
it must be updated separately via the dashboard API or by editing
openclaw.json directly. The setup agent was still set to
`anthropic/claude-sonnet-4-6` after the gateway model was changed.
**Fix:** Update setup agent model explicitly:
```bash
curl -s -X PUT http://localhost:19100/api/agents/setup/model \
  -H "Content-Type: application/json" \
  -d '{"model": "ollama/qwen3:14b"}'
```
Then add the Ollama auth profile (Bug 8) since the setup agent's auth
store doesn't inherit from the main agent.

## Additional Bugs Found (2026-04-06)

### Bug 10: WebSocket URL hardcoded in setup dashboard
`templates/setup.html:1238` — WebSocket URL hardcoded to `ws://127.0.0.1:18789`
instead of using `window.location.hostname`. This caused the dashboard to fail
when accessed remotely via Tailscale, as the browser would try to connect to
localhost instead of the remote node.
**Fix:** Use dynamic host: `ws://${window.location.hostname}:18789` so the
dashboard works correctly regardless of how it's accessed (local or remote).

### Bug 11: GW_HOST and GW_PORT hardcoded in server_v2.py
`server_v2.py:145-147` — GW_HOST and GW_PORT were hardcoded instead of
reading from environment variables. This prevented flexible deployment
scenarios where the gateway host/port needed to differ from defaults.
**Fix:** Read from `GW_HOST`/`GW_PORT` env vars with fallback to defaults:
```python
GW_HOST = os.environ.get('GW_HOST', '127.0.0.1')
GW_PORT = int(os.environ.get('GW_PORT', 18789))
```
