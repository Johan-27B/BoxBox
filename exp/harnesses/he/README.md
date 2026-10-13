# Harness Evolution Versions

`h00/` through `h24/` contain the initial harness and its 24 evolved versions.
`index.json` records their order, parent versions, exported file hashes, and the
selected test version, H24.

To inspect an update:

```bash
diff -ru exp/harnesses/he/h07 exp/harnesses/he/h08
```

These snapshots are provided for inspecting harness evolution. For running
experiments, use the entry points in [Experiment Configuration](../../../docs/EXPERIMENTS.md).
