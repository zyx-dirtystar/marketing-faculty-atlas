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

test("published follow-up reconciles the two fixed cohorts and preserves evidence levels", () => {
  const progress = audit.followup;
  assert.equal(progress.method_cohort, 777);
  assert.equal(progress.publication_cohort, 469);
  const rows = load("download/followup.json");
  assert.equal(rows.filter((row) => row.cohort === "method_review").length, 777);
  assert.equal(rows.filter((row) => row.cohort === "publication_search").length, 469);
  assert.equal(rows.filter((row) => row.cohort === "method_review" &&
    row.papers_queued === row.papers_checked).length, progress.method_faculty_all_queued_papers_checked);
  const narayandas = load("people/harvard-university.json")["das-narayandas--harvard"];
  const aiStudy = narayandas.papers.find((paper) => paper.doi === "10.1287/mnsc.2022.03920");
  assert(aiStudy.evidence.some((mark) => mark.tag === "field" && mark.level === reviewed));
  assert(!aiStudy.evidence.some((mark) => mark.tag === "ml"));
  const saunders = load("people/monash-university.json")["stephen-saunders--monash"];
  const sem = saunders.papers.find((paper) => paper.doi === "10.1108/ijqrm-06-2019-0198");
  assert(sem.evidence.some((mark) => mark.tag === "sem" && mark.level === reviewed));
  assert(!sem.evidence.some((mark) => mark.tag === "structural"));
  const janssen = load("people/universite-libre-de-bruxelles.json")["catherine-janssen--ulb"];
  assert(janssen.papers.some((paper) => paper.doi === "10.1002/jcpy.1345" && paper.listing_url));
});

test("deeper review preserves the cohorts, working papers and negative authorship decisions", () => {
  const report = audit.followup.deep_review;
  assert.equal(report.method_faculty, 84);
  assert.equal(report.methods_supported, report.method_faculty);
  assert.equal(report.publication_faculty, 270);
  assert.equal(report.publication_searches, report.publication_faculty);
  const emil = people.find((row) => row.id === "emil-palikot--northeastern");
  const contest = load(`people/${emil.school}.json`)[emil.id].papers
    .find((paper) => paper.doi === "10.1007/s11129-026-09311-3");
  assert.equal(contest.fulltext_check.state, "fulltext_read");
  assert(contest.evidence.some((mark) => mark.tag === "rct" && mark.level === reviewed));
  const kumar = people.find((row) => row.id === "amit-kumar--delaware");
  const homonym = load(`people/${kumar.school}.json`)[kumar.id].papers
    .find((paper) => paper.doi === "10.1016/j.aos.2025.101631");
  assert.equal(homonym.authorship, "review_needed");
  assert.deepEqual(homonym.evidence, []);
  const gabriele = people.find((row) => row.id === "francesco-gabriele--hkust");
  const drafts = load(`people/${gabriele.school}.json`)[gabriele.id].papers
    .filter((paper) => paper.discovery_method === "cv_working_paper");
  assert(drafts.length >= 2);
  assert.equal(ids(drafts).size, drafts.length);
  assert(drafts.every((paper) => paper.status === "wp"));
  const noelle = people.find((row) => row.id === "noelle-nelson--oregon");
  const recovered = load(`people/${noelle.school}.json`)[noelle.id].papers
    .find((paper) => paper.id === "work:68f74c48962051e91228d81f");
  assert.equal(recovered.doi, "10.1093/jcr/ucx056");
  assert.equal(recovered.title_check.state, "exact_title_byline");
});
