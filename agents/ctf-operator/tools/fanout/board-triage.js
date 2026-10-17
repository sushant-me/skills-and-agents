// Board triage fan-out — pass this file's contents as the `script` argument of
// the workflow() tool, with args = { challenges: [{name, category, path, value}, ...] }.
//
// Build the challenge list from the platform client first, e.g.
//   python3 tools/ctfctfd.py --url <URL> --cookie <COOKIE> list
// which prints id / category / pts / solved / name for every visible challenge.
// Pass only the UNSOLVED ones in, as {name, category, path, value}.
//
// One scout per challenge, structured output only (no prose), so the result is
// a ranked work order rather than a wall of text. Then work it top-down
// yourself, spawning solver/verifier children per ctf-fanout.

phase("triage")
const list = args.challenges

const ranked = await pipeline(
  list,

  // stage 1 — classify one challenge. Triage ONLY: no solving, no submitting.
  async (_prev, c) => agent(
    `CTF triage only. Do not solve anything and do not submit anything.\n` +
    `Challenge: "${c.name}" (${c.category}, ${c.value} pts) at ${c.path}.\n` +
    `Report, terse:\n` +
    ` - asks: what the challenge is asking for, one sentence\n` +
    ` - artefacts: the files/endpoints shipped\n` +
    ` - attack: the single most likely attack class\n` +
    ` - family: any other challenge sharing an author, stamp, file format or\n` +
    `   container layout (else "")\n` +
    ` - minutes: your estimate to a first real attempt\n` +
    ` - solvable: yes | maybe | no`,
    {
      label: `triage:${c.name}`,
      phase: "triage",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["asks", "attack", "minutes", "solvable"],
        properties: {
          asks:      { type: "string" },
          artefacts: { type: "array", items: { type: "string" } },
          attack:    { type: "string" },
          family:    { type: "string" },
          minutes:   { type: "number" },
          solvable:  { type: "string", enum: ["yes", "maybe", "no"] },
        },
      },
    },
  ),

  // stage 2 — score it. No barrier: each item flows through independently.
  async (t, c) => t && ({
    name: c.name,
    category: c.category,
    value: c.value,
    attack: t.attack,
    family: t.family,
    minutes: t.minutes,
    solvable: t.solvable,
    // points per minute, with "no" forced to zero so it never outranks a real card
    score: (t.solvable === "no" ? 0 : c.value) / Math.max(t.minutes, 1),
  }),
)

const kept = ranked.filter(Boolean)
log(`triaged ${kept.length}/${list.length} challenges`)

// families matter: members of one family usually solve together, so surface them
const families = {}
for (const r of kept) if (r.family) (families[r.family] ||= []).push(r.name)

return {
  workOrder: kept.sort((a, b) => b.score - a.score),
  families,
  unsolvable: kept.filter(r => r.solvable === "no").map(r => r.name),
}
