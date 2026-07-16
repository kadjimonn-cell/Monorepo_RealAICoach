import fs from 'fs';
import path from 'path';

const read = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), relativePath), 'utf8');
const readBackend = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), '..', 'backend', relativePath), 'utf8');

describe('platform subscription access-control contract', () => {
  it('removes paid authenticated feature APIs from the public backend contract', () => {
    const publicApiContract = readBackend('utils/public_api_contract.py');

    expect(publicApiContract).not.toContain('"/api/personal-assistant/"');
    expect(publicApiContract).not.toContain('"/api/research-navigator/"');
    expect(publicApiContract).not.toContain('"/api/ai-enterprise/"');
    expect(publicApiContract).not.toContain('"/api/bill-generator/"');
    expect(publicApiContract).not.toContain('"/api/mobility-assistant/"');
  });

  it('keeps frontend route gating aligned with backend paid-tier expectations', () => {
    const accessControlContext = read('src/context/AccessControlContext.tsx');

    expect(accessControlContext).toContain('const BASIC_AUTHENTICATED_UI_PREFIXES = [');
    expect(accessControlContext).toContain("'/features/writing-studio'");
    expect(accessControlContext).toContain("'/features/research-navigator'");
    expect(accessControlContext).toContain("'/features/ai-enterprise'");
    expect(accessControlContext).toContain("reason: 'basic_required'");
    expect(accessControlContext).toContain("message: 'This feature requires a Basic or Premium subscription.'");
  });

  it('reads entitlement-driven feature access from feature_entitlements when available', () => {
    const subscriptionContext = read('src/context/SubscriptionContext.tsx');

    expect(subscriptionContext).toContain('feature_entitlements?: Record<string, any>;');
    expect(subscriptionContext).toContain('const source = status?.feature_entitlements || status?.features || null;');
    expect(subscriptionContext).toContain("if (typeof val === 'string') {");
  });
});