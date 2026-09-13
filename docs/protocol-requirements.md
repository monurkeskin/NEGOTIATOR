# Preparing a protocol for new participants

A new session needs its domain, profiles, instructions, survey and any device or
model assets selected by the study. It does not need another participant's old
records unless the method explicitly uses those records as an input.

In a published protocol, label every external requirement by its use:

```json
{
  "id": "original-session-records",
  "description": "Authorized inputs for recomputing the original results",
  "required_for": "historical-analysis"
}
```

`required_for` defaults to `execution`. Keep that value for a model checkpoint,
gesture pack or calibration input that the next session needs. Execution inputs
must have a local `path` and matching `sha256` before a published protocol starts.
Split a requirement that combines a runtime asset and historical records into
two entries. Do not classify a required runtime file as historical to bypass a
preparation error.

Study preparation checks execution requirements. The separate check
`protocol_readiness(spec, operation="historical-analysis")` reports missing
historical evidence. Reproduction manifests still require their own actual inputs
and hashes; a successful new session is not a recomputation of an old result.

This distinction does not remove practice sessions, scheduled breaks, surveys or
other protocol stages. A method that learns from practice must still require that
input. Each session retains its own durable record, so preserving an earlier
record does not depend on reusing its filename.

Configurations written for older releases retain execution requirements until
they are reviewed and explicitly reclassified. This field is available from
2.1.0; the archived 2.0.0 artifact keeps its original behavior.
