# JSON Schema and IDE Setup

Forge generates Draft 2020-12 JSON Schemas from the strict Pydantic project model. `project.schema.json` describes a complete merged project; `fragment.schema.json` removes the top-level required list so partial numbered files can be edited independently.

VS Code associations map `app/*/app.json` and project fragment paths to these schemas. Editors can therefore catch typos before runtime while `forge validate` remains authoritative because it also resolves environment values, merges fragments and applies cross-field validators.

Run `forge schema` after model changes and verify `git diff --exit-code -- schemas` in CI. v0.4.1 schemas include current `0.4.1` defaults.
