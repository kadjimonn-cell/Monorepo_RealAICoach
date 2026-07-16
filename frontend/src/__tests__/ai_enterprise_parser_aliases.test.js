/* global describe, test, expect */

import { parseStructuredSections } from '../utils/aiEnterpriseParser';

describe('aiEnterpriseParser alias snapshots', () => {
  const cases = [
    {
      name: 'markdown heading aliases',
      input: `
# Leadership Summary
Focus on retention and activation.

## Goals Tree
- Increase activation by 12%

### Metrics Pack
- Activation rate
- NRR

## Risk Matrix
- Churn spike during onboarding

## 30-60-90 Plan
- Day 30: baseline audit
- Day 60: experiment rollout
- Day 90: scale winners
`,
      expects: {
        executiveSummary: ['leadership summary', 'retention'],
        objectiveTree: ['goals tree'],
        kpiPack: ['metrics pack'],
        riskRegister: ['risk matrix'],
        plan306090: ['30-60-90 plan', 'day 90'],
      },
    },
    {
      name: 'numbered long-form headings',
      input: `
1) Executive Brief
Prioritize funnel quality over volume.

2) Objective Hierarchy
North star: increase win rate.

3) KPI Set
SQL->Win, Time-to-Value, CAC Payback

4) Key Risks
Pipeline concentration and forecast drift.

5) Thirty Sixty Ninety Plan
30: instrumentation, 60: process change, 90: governance
`,
      expects: {
        executiveSummary: ['executive brief'],
        objectiveTree: ['objective hierarchy'],
        kpiPack: ['kpi set'],
        riskRegister: ['key risks'],
        plan306090: ['thirty sixty ninety plan'],
      },
    },
    {
      name: 'bold markdown and fallback extraction',
      input: `
**Executive Summary**
Stabilize onboarding conversion.

**Objective Tree**
Goal -> Driver -> Initiative

Narrative without strict headings but still contains KPI pack and risk register references.
KPI pack should include activation and retention.
Risk register should include staffing risk.

30/60/90 plan should map owners and milestones.
`,
      expects: {
        executiveSummary: ['executive summary'],
        objectiveTree: ['objective tree'],
        kpiPack: ['kpi pack'],
        riskRegister: ['risk register'],
        plan306090: ['30/60/90 plan'],
      },
    },
  ];

  test.each(cases)('%s', ({ input, expects }) => {
    const parsed = parseStructuredSections(input);

    const availabilitySnapshot = {
      executiveSummary: Boolean(parsed.executiveSummary),
      objectiveTree: Boolean(parsed.objectiveTree),
      kpiPack: Boolean(parsed.kpiPack),
      riskRegister: Boolean(parsed.riskRegister),
      plan306090: Boolean(parsed.plan306090),
    };
    expect(availabilitySnapshot).toMatchInlineSnapshot(`
{
  "executiveSummary": true,
  "kpiPack": true,
  "objectiveTree": true,
  "plan306090": true,
  "riskRegister": true,
}
`);

    expect(parsed.executiveSummary.toLowerCase()).toEqual(expect.stringContaining(expects.executiveSummary[0]));
    expect(parsed.objectiveTree.toLowerCase()).toEqual(expect.stringContaining(expects.objectiveTree[0]));
    expect(parsed.kpiPack.toLowerCase()).toEqual(expect.stringContaining(expects.kpiPack[0]));
    expect(parsed.riskRegister.toLowerCase()).toEqual(expect.stringContaining(expects.riskRegister[0]));
    expect(parsed.plan306090.toLowerCase()).toEqual(expect.stringContaining(expects.plan306090[0]));
  });
});