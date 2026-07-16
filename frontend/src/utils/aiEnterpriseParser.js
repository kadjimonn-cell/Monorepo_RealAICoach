/**
 * @typedef {Object} StructuredSections
 * @property {string} executiveSummary
 * @property {string} objectiveTree
 * @property {string} kpiPack
 * @property {string} riskRegister
 * @property {string} plan306090
 */

const sectionPatterns = {
  executiveSummary: ['executive summary', 'leadership summary', 'executive brief'],
  objectiveTree: ['objective tree', 'objective hierarchy', 'goals tree'],
  kpiPack: ['kpi pack', 'kpi set', 'metrics pack', 'metric pack'],
  riskRegister: ['risk register', 'risk matrix', 'risk log', 'key risks'],
  plan306090: ['30/60/90 plan', '30-60-90 plan', '30 60 90 plan', 'thirty sixty ninety plan'],
};

function normalizeLine(line) {
  return String(line || '')
    .replace(/^\s*[-*\d.)#\s]+/, '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .trim()
    .toLowerCase();
}

/**
 * @param {string} raw
 * @param {string[]} patterns
 */
function fallbackExtract(raw, patterns) {
  const source = String(raw || '');
  const lower = source.toLowerCase();
  const found = patterns.find((pattern) => lower.includes(pattern));
  if (!found) return '';
  const idx = lower.indexOf(found);
  if (idx < 0) return '';
  return source.slice(idx).split('\n').slice(0, 8).join('\n').trim();
}

/**
 * @param {string} raw
 * @returns {StructuredSections}
 */
export function parseStructuredSections(raw) {
  const lines = String(raw || '').split('\n');
  /** @type {{ index: number, key: keyof StructuredSections }[]} */
  const headingHits = [];

  lines.forEach((line, index) => {
    const normalized = normalizeLine(line);
    Object.keys(sectionPatterns).forEach((key) => {
      if (headingHits.some((hit) => hit.index === index)) return;
      const patterns = sectionPatterns[key];
      const matched = patterns.some((pattern) => normalized.includes(pattern));
      if (matched) {
        headingHits.push({ index, key: /** @type {keyof StructuredSections} */ (key) });
      }
    });
  });

  /** @type {StructuredSections} */
  const parsed = {
    executiveSummary: '',
    objectiveTree: '',
    kpiPack: '',
    riskRegister: '',
    plan306090: '',
  };

  if (headingHits.length) {
    const sorted = [...headingHits].sort((a, b) => a.index - b.index);
    sorted.forEach((hit, idx) => {
      const start = hit.index;
      const end = idx + 1 < sorted.length ? sorted[idx + 1].index : lines.length;
      parsed[hit.key] = lines.slice(start, end).join('\n').trim();
    });
  }

  return {
    executiveSummary: parsed.executiveSummary || fallbackExtract(raw, sectionPatterns.executiveSummary),
    objectiveTree: parsed.objectiveTree || fallbackExtract(raw, sectionPatterns.objectiveTree),
    kpiPack: parsed.kpiPack || fallbackExtract(raw, sectionPatterns.kpiPack),
    riskRegister: parsed.riskRegister || fallbackExtract(raw, sectionPatterns.riskRegister),
    plan306090: parsed.plan306090 || fallbackExtract(raw, sectionPatterns.plan306090),
  };
}

export const parserAliasMatrix = sectionPatterns;