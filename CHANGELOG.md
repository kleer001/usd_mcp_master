# Changelog

Notable changes per release. Dates are release dates; the repository history is the
finer record.

## 0.3.0

### Added

- **`usd-explain`, a command-line front door.** Nine read-only commands over the same
  functions the MCP tools call, printing JSON to stdout; a failure is a message on
  stderr and exit status 2. Writing is opt-in on the same terms as the server —
  `--enable-write` registers the three mutating commands and nothing else, and the dry
  run remains the default until `--confirm`. Attribute values are read as JSON so their
  type is stated rather than guessed.
- **Result bounds.** Every list that grows with the size of a stage is trimmed to a
  256 KB budget per field, and every authored array value to 25 KB. A trimmed field
  carries `<field>_truncated` with the reported and total counts, so no cap is silent.
  `usd-explain --full` reports everything whole.

### Changed

- **The safety contract covers both front doors.** `test_safety_contract.py` now pins
  the CLI's mutating command set alongside the server's tool set and asserts the two are
  the same three. It also parses every `bounded()` call and fails the build if `SPEC.md`
  names a different set of bounded fields.
- **The README opens in symptom language** rather than USD vocabulary: the questions
  people actually type when an override is not taking effect.

### Fixed

- **Documentation claims narrowed to what the build keeps.** An honesty audit found ten
  overstatements, including a bound described as covering every list when it covered
  none of the array values, "every authored opinion" after opinions became bounded, a
  dry run described as unskippable when `confirm=true` on a first call writes
  immediately, four ways a prim can disappear where the code covers six, and an instance
  described as unable to hold an edit when it is the instance's proxies that cannot.

## 0.2.0

Nine read-only tools, three opt-in mutating tools, two resources, two prompts, and the
safety contract as an executable test.
