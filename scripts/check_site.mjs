import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { matchingPeople } from "../site/filters.js";

function load(path) {
  return JSON.parse(readFileSync(new URL("../dist/" + path, import.meta.url), "utf8"));
}

const { people, schools, audit } = load("data.json");
for (const person of people) {
  person.search = [person.name, person.unit, schools[person.school].name, ...person.primary_fields]
    .join(" ").toLowerCase();
}
const ids = (rows) => new Set(rows.map((row) => row.id));
const reviewed = "source_reviewed";

test("scope filters are exhaustive and agree with the pinned and live data", () => {
  assert.equal(ids(people).size, people.length);
  assert.equal(matchingPeople(people, {}).length, audit.scope.share_link.total);
  assert.equal(matchingPeople(people, { scope: "all" }).length, people.length);
  assert.equal(matchingPeople(people, { scope: "cross_unit" }).length, audit.scope.cross_unit.total);
  if (audit.live_index_check) {
    assert.deepEqual(audit.live_index_check.id_or_scope_differences, []);
    assert.equal(people.length, audit.live_index_check.all);
  }
});

test("source-reviewed recurring structural demand estimation", () => {
  const results = matchingPeople(people, { method: "demand_estimation", repeat: "2", level: reviewed });
  assert(ids(results).has("jean-pierre-dube--chicago"));
  assert(ids(results).has("guenter-j-hitsch--chicago"));
});

test("source-reviewed field advertising and controlled online experiments remain distinct", () => {
  const results = matchingPeople(people, { topic: "advertising", design: "field", together: "1", level: reviewed });
  assert(ids(results).has("brett-r-gordon--stanford"));
  assert(!ids(results).has("ilya-morozov--northwestern"));
  const profile = load("people/northwestern-university.json")["anna-tuchman--northwestern"];
  const bookstore = profile.papers.find((p) => p.doi === "10.1287/mksc.2023.0138");
  assert(bookstore.evidence.some((mark) => mark.tag === "online" && mark.level === reviewed));
  assert(!bookstore.evidence.some((mark) => mark.tag === "field"));
});

test("ML and causal inference can be required on the same paper", () => {
  const common = { method: "ml", objective: "causal", level: reviewed };
  const combined = ids(matchingPeople(people, common));
  const same = ids(matchingPeople(people, { ...common, together: "1" }));
  assert(same.has("brett-r-gordon--stanford"));
  assert([...same].every((id) => combined.has(id)));
  const example = {
    scope: "share_link", search: "", counts: { [reviewed]: { ml: 1, causal: 1 }, abstract_signal: {} },
    paper_tags: [{ [reviewed]: ["ml"], abstract_signal: [] }, { [reviewed]: ["causal"], abstract_signal: [] }],
  };
  assert.equal(matchingPeople([example], common).length, 1);
  assert.equal(matchingPeople([example], { ...common, together: "1" }).length, 0);
  assert.equal(matchingPeople([example], { repeat: "2" }).length, 0);
});

test("public profiles and exports preserve provenance and guard disputed authorships", () => {
  const profile = load("people/university-of-pennsylvania.json")["z-john-zhang--penn"];
  const mismatched = profile.papers.find((p) => p.doi === "10.1177/01492063241247499");
  assert.equal(mismatched.authorship, "review_needed");
  assert.deepEqual(mismatched.evidence, []);
  assert(profile.papers.some((p) => p.evidence.some((mark) => mark.tag === "analytical")));
  const exportRows = load("download/faculty.json");
  assert.equal(exportRows.length, people.length);
  assert.equal(load("download/authorships.json").length, audit.coverage.authorship_pairs);
});
