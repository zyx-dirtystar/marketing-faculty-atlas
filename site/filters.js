export function matchingPeople(people, filters) {
  const terms = (filters.q || "").toLowerCase().trim().split(/\s+/).filter(Boolean);
  const tags = [...new Set(["topic", "method", "design", "objective", "identification"]
    .map((key) => filters[key]).filter(Boolean))];
  const levels = filters.level ? [filters.level] : ["source_reviewed", "abstract_signal"];
  const minimum = filters.repeat === "2" ? 2 : 1;

  return people.filter((person) => {
    if (filters.scope !== "all" && person.scope !== (filters.scope || "share_link")) return false;
    if (filters.school && person.school !== filters.school) return false;
    if (filters.track && !person.primary_fields.includes(filters.track)) return false;
    if (filters.rank && person.rank !== filters.rank) return false;
    if (filters.status && person.status !== filters.status) return false;
    if (!terms.every((term) => person.search.includes(term))) return false;
    if (!tags.length) {
      if (!filters.level && minimum === 1) return true;
      const counts = new Map();
      for (const level of levels) {
        for (const [tag, count] of Object.entries(person.counts[level])) {
          counts.set(tag, (counts.get(tag) || 0) + count);
        }
      }
      return [...counts.values()].some((count) => count >= minimum);
    }
    if (filters.together === "1") {
      return person.paper_tags.filter((paper) => tags.every((tag) =>
        levels.some((level) => paper[level].includes(tag)))).length >= minimum;
    }
    return tags.every((tag) =>
      levels.reduce((count, level) => count + (person.counts[level][tag] || 0), 0) >= minimum);
  });
}
