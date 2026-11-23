import { matchingPeople } from "./filters.js";

const app = document.getElementById("app");
const reviewed = "source_reviewed";
const primaryAbstract = "primary_abstract";
const signal = "abstract_signal";
const evidenceLabels = { [reviewed]: "Source reviewed", [primaryAbstract]: "Primary abstract evidence",
  [signal]: "Abstract signal" };
const levels = Object.keys(evidenceLabels);
const roleLabels = { pub: "Publication", rr: "Revise & resubmit", wp: "Working paper" };
const navState = { request: 0 };
const schoolCache = new Map();
const number = new Intl.NumberFormat("en");
const format = (n) => number.format(n || 0);
const escape = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let data, byId, label;

function link(url, caption) {
  if (!/^https?:\/\//i.test(url || "")) return "";
  return `<a target="_blank" rel="noopener noreferrer" href="${escape(url)}">${escape(caption)}</a>`;
}

async function getJson(path) {
  const result = await fetch(path);
  if (!result.ok) throw new Error(`HTTP ${result.status} loading ${path}`);
  return result.json();
}

function select(name, caption, options, selected) {
  return `<label>${escape(caption)}
    <select name="${escape(name)}">${options.map(([value, text]) =>
    `<option value="${escape(value)}"${value === (selected || "") ? " selected" : ""}>${escape(text)}</option>`
  ).join("")}</select></label>`;
}

function tagsFor(person) {
  const tags = new Set(levels.flatMap((level) => Object.keys(person.counts[level])));
  return [...tags].sort((a, b) => {
    for (const level of levels) {
      const difference = (person.counts[level][b] || 0) - (person.counts[level][a] || 0);
      if (difference) return difference;
    }
    return label[a].localeCompare(label[b]);
  });
}

const bestLevel = (person, tag) => levels.find((level) => person.counts[level][tag]);

function tagButton(tag, level, target) {
  return `<a class="tag ${level}" href="${escape(target)}">${escape(label[tag])}</a>`;
}

function entries(keys) {
  return Object.entries(keys).sort((a, b) => a[1].localeCompare(b[1]));
}

function atlasDirectory(params) {
  const filters = Object.fromEntries(params);
  const results = matchingPeople(data.people, filters);
  const pages = Math.max(1, Math.ceil(results.length / 30));
  const page = Math.min(pages, Math.max(1, Number.parseInt(filters.page, 10) || 1));
  const visible = results.slice((page - 1) * 30, page * 30);
  const withSignals = data.audit.status[signal];
  const checked = data.audit.status[reviewed];
  const active = [...params.keys()].some((key) => key !== "scope");
  const taxonomyFilters = [
    ["method", "Method"], ["topic", "Research topic"], ["design", "Research design"],
    ["objective", "Research objective"], ["identification", "Identification strategy"],
  ];
  const status = (person) => `<span class="state ${person.status}">${escape(data.statuses[person.status])}</span>`;
  app.innerHTML = `
    <section class="intro">
      <div><h1>Marketing faculty</h1><p>Find scholars by the questions they study and the methods they use.</p></div>
      <dl class="stats">
        <div><dt>Faculty</dt><dd>${format(data.audit.faculty_total)}</dd></div>
        <div><dt>Source reviewed</dt><dd>${format(checked)}</dd></div>
        <div><dt>Primary abstract</dt><dd>${format(data.audit.status[primaryAbstract])}</dd></div>
        <div><dt>Abstract signals only</dt><dd>${format(withSignals)}</dd></div>
      </dl>
    </section>
    <section class="panel" aria-label="Faculty filters">
      <form id="filters">
        <div class="form-grid main-filters">
          <label>Search<input name="q" type="search" placeholder="Name, school, department" value="${escape(filters.q)}"></label>
          ${select("scope", "Roster", [["", "Business school · shared link"], ["all", "All Marketing faculty"], ["cross_unit", "Other academic units"]], filters.scope)}
          ${select("school", "School", [["", "All schools"], ...entries(Object.fromEntries(Object.values(data.schools).map((s) => [s.id, s.name])))], filters.school)}
          ${select("track", "Econ Atlas field", [["", "All Marketing fields"], ...Object.keys(data.audit.track).sort().map((s) => [s, s.replace("Marketing: ", "")])], filters.track)}
        </div>
        <div class="form-grid methods">
          ${taxonomyFilters.map(([key, caption]) =>
      select(key, caption, [["", "Any"], ...entries(data.taxonomy[key])], filters[key])).join("")}
        </div>
        <details class="advanced"${["rank", "status"].some((key) => filters[key]) ? " open" : ""}>
          <summary>Rank and coverage</summary>
          <div class="form-grid methods">
            ${select("rank", "Rank", [["", "Any rank"], ...[...new Set(data.people.map((p) => p.rank))].sort().map((s) => [s, s])], filters.rank)}
            ${select("status", "Coverage status", [["", "All coverage states"], ...Object.entries(data.statuses)], filters.status)}
          </div>
        </details>
        <div class="refine">
          ${select("level", "Evidence", [["", "All evidence levels"], ...Object.entries(evidenceLabels)], filters.level)}
          <label class="check"><input name="together" type="checkbox" value="1"${filters.together ? " checked" : ""}> Match tags on the same paper</label>
          <label class="check"><input name="repeat" type="checkbox" value="2"${filters.repeat ? " checked" : ""}> At least two papers</label>
          <button type="submit">Apply filters</button>
          ${active ? '<a class="reset" href="#/">Clear</a>' : ""}
        </div>
      </form>
    </section>
    <div class="results-bar"><strong>${format(results.length)} matches</strong><span>Page ${page} of ${pages}</span></div>
    <div class="table-frame">
      <table>
        <thead><tr><th>Faculty</th><th>School</th><th>Econ Atlas field</th><th>Research tags</th><th>Evidence coverage</th></tr></thead>
        <tbody>${visible.map((person) => {
    const dest = `#/p/${encodeURIComponent(person.id)}`;
    const tags = tagsFor(person);
    return `<tr>
      <td><a class="person-name" href="${dest}">${escape(person.name)}</a><small>${escape(person.rank)}</small></td>
      <td>${escape(data.schools[person.school].short)}<small>${escape(person.unit)}</small></td>
      <td>${person.primary_fields.filter((s) => s.startsWith("Marketing:")).map((s) => escape(s.slice(11))).join("<br>")}</td>
      <td><div class="tags">${tags.slice(0, 4).map((tag) => tagButton(tag, bestLevel(person, tag), dest + "?tag=" + encodeURIComponent(tag))).join("")}
      ${tags.length > 4 ? `<a class="more" href="${dest}">+${tags.length - 4}</a>` : ""}</div></td>
      <td>${status(person)}<small>${format(person.abstracts_checked)} indexed abstracts · ${format(person.paper_count)} listed works</small></td>
    </tr>`;
  }).join("") || '<tr><td colspan="5">No faculty match these filters.</td></tr>'}</tbody>
      </table>
    </div>
    <nav class="pagination" aria-label="Results pages">
      ${page > 1 ? pageLink(params, page - 1, "Previous page") : ""}
      ${page < pages ? pageLink(params, page + 1, "Next page") : ""}
    </nav>`;

  document.getElementById("filters").addEventListener("submit", (event) => {
    event.preventDefault();
    const next = new URLSearchParams([...new FormData(event.currentTarget)].filter(([, value]) => value));
    location.hash = next.size ? `/?${next}` : "/";
  });
}

function pageLink(params, page, name) {
  const next = new URLSearchParams(params);
  next.set("page", page);
  return `<a href="#/?${escape(next.toString())}">${escape(name)}</a>`;
}

function evidenceRow(mark) {
  const tokens = mark.token_range ? ` · tokens ${mark.token_range[0]}–${mark.token_range[1]}` : "";
  return `<li><b>${escape(label[mark.tag])}</b> <span class="state ${mark.level}">${evidenceLabels[mark.level]}</span>
    <p>${escape(mark.note)}</p><small>${link(mark.source, mark.locator)}${tokens}</small></li>`;
}

function paperCard(paper, tag) {
  const marks = tag ? paper.evidence.filter((mark) => mark.tag === tag) : paper.evidence;
  const status = [
    paper.year, roleLabels[paper.status], paper.venue,
    paper.discovery === "openalex_exact_orcid" ? "OpenAlex · exact ORCID" : "",
    paper.listing_url ? "Faculty publication source" : "",
    paper.retracted ? "Retracted" : "",
    paper.authorship === "review_needed" ? "Authorship needs review" : "",
  ].filter(Boolean).join(" · ");
  return `<article class="paper">
    <small>${escape(status)}</small>
    <h3>${link(paper.url, paper.title) || escape(paper.title)}</h3>
    <p class="authors">${escape(paper.authors.join(", "))}</p>
    ${paper.listing_url ? `<small>${link(paper.listing_url, "Publication listing or CV")}</small>` : ""}
    ${marks.length ? `<details${tag ? " open" : ""}><summary>${marks.length} evidence entries</summary><ul class="evidence">${marks.map(evidenceRow).join("")}</ul></details>` : ""}
    ${paper.versions.length > 1 ? `<details><summary>${paper.versions.length} source records</summary><ul>${paper.versions.map((v) =>
    `<li>${escape(v.year)} ${escape(roleLabels[v.status])} · ${link(v.url, v.title) || escape(v.title)}</li>`).join("")}</ul></details>` : ""}
  </article>`;
}

async function profile(id, params, request) {
  const row = byId.get(id);
  if (!row) {
    app.innerHTML = '<p>Faculty profile not found. <a href="#/">Faculty directory</a></p>';
    return;
  }
  if (!schoolCache.has(row.school)) {
    schoolCache.set(row.school, getJson(`people/${encodeURIComponent(row.school)}.json`).catch((error) => {
      schoolCache.delete(row.school);
      throw error;
    }));
  }
  app.innerHTML = '<p>Loading profile…</p>';
  const person = (await schoolCache.get(row.school))[id];
  if (request !== navState.request) return;
  const path = `#/p/${encodeURIComponent(id)}`;
  const tag = Object.hasOwn(label, params.get("tag")) ? params.get("tag") : "";
  const papers = person.papers.filter((paper) => !tag || paper.evidence.some((mark) => mark.tag === tag));
  const tags = tagsFor(person);
  const primary = tags.filter((item) => person.counts[reviewed][item] >= 2);
  const sources = { homepage_url: "Homepage", profile_url: "Faculty profile", cv_url: "CV",
    google_scholar_url: "Google Scholar", source_url: "Roster source" };
  const placement = person.placement;
  app.innerHTML = `<p class="breadcrumb"><a href="#/">Faculty</a> / <a href="#/?scope=all&amp;school=${escape(person.school)}">${escape(data.schools[person.school].short)}</a></p>
    <section class="profile-head">
      <h1>${escape(person.name)}</h1>
      <p>${escape(person.title || person.rank)} · ${escape(data.schools[person.school].name)}</p>
      <p>${escape(person.unit)} · ${escape(person.primary_fields.join(" · "))}</p>
      <div class="links">${link(person.upstream_url, "Econ Atlas")}${Object.entries(person.links).map(([key, url]) => link(url, sources[key] || key)).join("")}</div>
    </section>
    <div class="profile-grid">
      <section class="panel profile-aside">
        <h2>Research profile</h2>
        <p class="state ${person.status}">${escape(data.statuses[person.status])}</p>
        ${primary.length ? `<p>At least two source-reviewed papers cover ${escape(primary.map((item) => label[item]).join(", "))}.</p>` : ""}
        ${person.research_interests ? `<p class="original">${escape(person.research_interests)}<small>Econ Atlas research interests</small></p>` : ""}
        <p>${format(person.source_reviewed_count)} source-reviewed works · ${format(person.abstracts_checked)} indexed abstracts · ${format(person.paper_count)} listed works.</p>
        ${Object.entries(data.taxonomy).map(([dimension, terms]) => {
    const sectionTags = tags.filter((item) => Object.hasOwn(terms, item));
    if (!sectionTags.length) return "";
    return `<h3 class="group-label">${escape(dimension)}</h3>
      <ul class="tag-list">${sectionTags.map((item) => `<li>
        ${tagButton(item, bestLevel(person, item), path + "?tag=" + encodeURIComponent(item))}
        <small>${format(person.counts[reviewed][item])} reviewed · ${format(person.counts[primaryAbstract][item])} primary abstracts · ${format(person.counts[signal][item])} signals
          ${person.latest[item] ? " · " + person.latest[item] : ""}</small>
      </li>`).join("")}</ul>`;
  }).join("")}
        ${person.education.length ? `<details><summary>Education</summary><ul>${person.education.map((item) => `<li>${escape(item.degree.toUpperCase())} · ${escape(item.institution)} ${escape(item.year)} ${escape(item.field)}</li>`).join("")}</ul></details>` : ""}
        ${followupPanel(person.followup)}
        ${placement ? `<details><summary>Placement project cross-check</summary><p>${placement.state === "shared_profile_url" ? "Shared identifier and concordant name" : "Identity review needed"}</p><ul>${placement.candidates.map((item) => `<li>${link(item.profile_url, item.name) || escape(item.name)} · ${escape(item.institution)} · ${escape(item.checked_at)}<small>${escape(item.tracks.join(", "))}${item.institution_name_differs ? " · Institution names differ" : ""}</small></li>`).join("")}</ul></details>` : ""}
      </section>
      <section>
        <div class="results-bar"><h2>${tag ? escape(label[tag]) : "Papers"} <small>${format(papers.length)}</small></h2>${tag ? `<a href="${path}">Show all papers</a>` : ""}</div>
        ${papers.map((paper) => paperCard(paper, tag)).join("") || "<p>No papers available for this view.</p>"}
      </section>
    </div>`;
}

function followupPanel(row) {
  if (!row) return "";
  if (row.cohort === "method_review") {
    return `<details><summary>Follow-up paper checks</summary>
      <p>${format(row.papers_checked)} of ${format(row.papers_queued)} queued papers checked.</p></details>`;
  }
  const sourceStates = { identity_checked: "Profile or CV read", identity_unconfirmed: "Identity needs review",
    connection_error: "Connection failed", pdf_text_unavailable: "PDF text unavailable" };
  return `<details><summary>Follow-up publication search</summary>
    <p>${row.checked_at ? `${format(row.papers_found)} linked works found · ${escape(row.checked_at)}` : "Search pending"}</p>
    ${row.sources.length ? `<ul>${row.sources.map((item) => `<li>${link(item.url, item.role.replaceAll("_", " "))}
      · ${escape(sourceStates[item.status] || item.status.replaceAll("_", " "))}</li>`).join("")}</ul>` : ""}</details>`;
}

function coverage() {
  const report = data.audit;
  const scopes = { share_link: "Business school · shared link", cross_unit: "Other academic units" };
  const count = (row, state) => format(row[state]);
  app.innerHTML = `<section class="intro"><div><h1>Coverage &amp; data</h1>
    <p>Roster and paper coverage for the ${escape(report.checked_at)} release.</p></div></section>
    <section class="panel coverage">
      <h2>Faculty coverage</h2>
      <dl>${Object.entries(data.statuses).map(([key, text]) => `<div><dt>${escape(text)}</dt><dd>${count(report.status, key)}</dd></div>`).join("")}</dl>
      <p>${format(report.coverage.pairs_with_indexed_abstract)} of ${format(report.coverage.authorship_pairs)} faculty–work pairs have an indexed abstract and a concordant byline.
      Abstract signals are candidates for review. Each source-reviewed tag links to the specific paper evidence.</p>
      <p>${format(report.coverage.faculty_with_orcid_papers_only)} faculty with papers found via exact ORCID.</p>
      <p>${format(report.placement.shared_profile_url)} concordant-name matches by shared identifier and ${format(report.placement.identity_review)} identity leads in ${link(report.placement.source, "mkt-io-placement")}.
      ${format(report.placement.institution_name_differences)} matches or leads have institution names that differ in the sources.</p>
      <p>${link(report.upstream + "/commit/" + report.upstream_commit, "Pinned Econ Atlas commit")} · ${report.live_index_check ? `Live index cross-check ${format(report.live_index_check.id_or_scope_differences.length)} differences` : "Live index cross-check unavailable"}</p>
    </section>
    ${report.followup ? `<section class="panel coverage">
      <h2>Follow-up research</h2>
      <p>${format(report.followup.method_faculty_attempted)} of ${format(report.followup.method_cohort)} faculty with method leads have at least one paper checked.
      ${format(report.followup.method_faculty_all_queued_papers_checked)} have results for every queued paper.</p>
      <p>${format(report.followup.method_faculty_with_manual_evidence)} faculty have a source review and
      ${format(report.followup.method_faculty_with_primary_abstract_only)} more have methods documented in a primary abstract.</p>
      <p>${format(report.followup.publication_faculty_attempted)} of ${format(report.followup.publication_cohort)} publication searches logged.
      ${format(report.followup.publication_faculty_with_papers)} faculty have linked works from this follow-up.</p>
      <p><a href="download/followup.csv">Follow-up CSV</a> · <a href="download/followup.json">Follow-up JSON</a></p>
    </section>` : ""}
    <section class="panel coverage">
      <h2>Download data</h2>
      <div class="downloads">${["faculty", "papers", "authorships", "evidence"].map((name) => `<div>
        <b>${name}</b> <a href="download/${name}.csv">CSV</a> <a href="download/${name}.json">JSON</a>
      </div>`).join("")}</div>
      <p><a href="download/coverage.json">Coverage report JSON</a> · <a href="https://github.com/zyx-dirtystar/marketing-faculty-atlas/blob/main/docs/methodology.md">Classification and data dictionary</a></p>
    </section>
    <section class="panel coverage">
      <h2>By roster, field and school</h2>
      ${[Object.entries(report.scope).map(([key, row]) => [scopes[key], row]),
    Object.entries(report.track),
    Object.entries(report.school).map(([key, row]) => [data.schools[key].name, row]).sort((a, b) => a[0].localeCompare(b[0]))
  ].map((rows) => `<div class="table-frame audit-table"><table><thead>
        <tr><th>Group</th><th>Faculty</th><th>Source reviewed</th><th>Primary abstract</th><th>Abstract signals only</th><th>Without labels</th></tr>
        </thead><tbody>${rows.map(([name, row]) => `<tr><td>${escape(name)}</td>
          <td>${count(row, "total")}</td><td>${count(row, reviewed)}</td><td>${count(row, primaryAbstract)}</td><td>${count(row, signal)}</td>
          <td>${format(row.total - levels.reduce((sum, level) => sum + (row[level] || 0), 0))}</td></tr>`).join("")}</tbody></table></div>`).join("")}
    </section>`;
}

async function render() {
  const request = ++navState.request;
  const [path, query] = (location.hash.slice(1) || "/").split("?");
  const params = new URLSearchParams(query);
  app.setAttribute("aria-busy", "true");
  try {
    if (path.startsWith("/p/")) await profile(decodeURIComponent(path.slice(3)), params, request);
    else if (path === "/coverage") coverage();
    else atlasDirectory(params);
  } catch (error) {
    if (request === navState.request) app.textContent = `Could not load this view. ${error.message}`;
  } finally {
    if (request === navState.request) {
      app.setAttribute("aria-busy", "false");
      window.scrollTo(0, 0);
    }
  }
}

try {
  data = await getJson("data.json");
  label = Object.assign({}, ...Object.values(data.taxonomy));
  for (const person of data.people) {
    person.search = [person.name, person.unit, data.schools[person.school].name,
      data.schools[person.school].short, ...person.primary_fields].join(" ").toLowerCase();
  }
  data.people.sort((a, b) => a.name.localeCompare(b.name));
  byId = new Map(data.people.map((person) => [person.id, person]));
  window.addEventListener("hashchange", render);
  await render();
} catch (error) {
  app.textContent = `Could not load the directory. ${error.message}`;
  app.setAttribute("aria-busy", "false");
}
