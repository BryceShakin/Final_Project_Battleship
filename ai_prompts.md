# AI Prompting and Constraint Strategy

I provide protocol_blueprint.md, fsm_specification.md, and the README
as context before requesting implementation. The prompts below are
prepared for the implementation stage; they do not claim code has
already been generated or tested.

## System Prompt

Implement only the protocol and game behavior defined in the supplied
documents. Preserve the exact message names, field names, data types,
allowed values, framing rules, and state transitions.

Do not invent additional messages, fields, or game rules. If a required
detail is missing or the documents conflict, identify the issue and ask
for clarification before implementing that behavior.

The server is authoritative. Validate client actions before changing
state, and never expose hidden opponent information.

## Parser and Serialization Prompt

Using protocol_blueprint.md, implement message parsing and serialization.

- Serialize each message as one UTF-8 JSON object followed by one LF byte.
- Buffer partial messages and extract multiple messages from one read.
- Validate required fields, types, allowed values, and MOVE action schemas.
- Reject invalid messages using the documented ERROR behavior.
- Treat recv() returning b"" as EOF and stop the receive loop.
- Handle socket failures and TCP keepalive according to the documents.
- Do not treat a short timer-check receive timeout as a disconnect.

## State Engine Prompt

Implement the transitions in fsm_specification.md using the README's
game rules and the blueprint's message definitions.

Require both valid setups before gameplay. Enforce active turns,
power-up eligibility, remaining attacks, and EMP turn skipping.
Invalid actions must not change game state. Apply valid actions and
check for victory before processing another event.

Handle DISCONNECT, EOF, and socket failures through cleanup that runs
once per connection. Preserve recorded outcomes and send each client
only the information permitted by STATE_UPDATE.

## Review Strategy

Before accepting generated code, compare it against the specifications:
- Exact message fields and LF framing.
- Partial and combined messages.
- Invalid payloads and out-of-turn actions.
- Setup, power-up effects, and victory transitions.
- EOF, connection failures, and cleanup without duplicate forfeits.

Correct deviations by citing the specific rule the implementation
violated, then request a revision limited to that rule.