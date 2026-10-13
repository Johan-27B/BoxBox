# Optimize the n8n-mcp server

I use the `n8n-mcp` HTTP server to process batches of workflow-building tool
calls against its local n8n node and template catalogue. Processing a typical
200-request batch takes too long.

Please optimize the implementation in `n8n-mcp/` so this workflow completes
faster. The metric is end-to-end wall-clock time for one invocation of
`workload/run.sh`, and lower is better.

The working directory contains:

- `n8n-mcp/` contains the editable TypeScript project.
- `workload/` contains the read-only request batch and run-only client.

## Build and run

Use these exact commands:

```bash
npm --prefix n8n-mcp run build
workload/run.sh
```

The run command starts the server, waits for its health endpoint, sends the
full request batch once, writes responses to `/tmp/n8n-mcp-responses.jsonl`,
and stops the server.

## Requirements

- Modify files only under `n8n-mcp/`.
- Do not modify `workload/` or files outside the working directory.
- Preserve the MCP protocol, tool behavior, and normalized responses for all
  valid tool-call batches.
- Improve the general server implementation; do not special-case the supplied
  requests or add input-specific shortcuts.

The environment includes `node --prof` and Linux `perf` for profiling.
