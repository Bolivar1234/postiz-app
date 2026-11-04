export type TeamInvitationClaims = {
  purpose: 'team-invitation';
  id: string;
  orgId: string;
  email: string;
  role: 'USER' | 'ADMIN';
  timeLimit: string;
};

export const normalizeInvitationEmail = (email: string) => email.trim().toLowerCase();

export function parseTeamInvitation(value: unknown, now = Date.now()): TeamInvitationClaims | false {
  if (!value || typeof value !== 'object' ||
    !('purpose' in value) || value.purpose !== 'team-invitation' ||
    !('id' in value) || typeof value.id !== 'string' || !value.id ||
    !('orgId' in value) || typeof value.orgId !== 'string' || !value.orgId ||
    !('email' in value) || typeof value.email !== 'string' || !value.email.includes('@') ||
    !('role' in value) || (value.role !== 'USER' && value.role !== 'ADMIN') ||
    !('timeLimit' in value) || typeof value.timeLimit !== 'string' ||
    !Number.isFinite(Date.parse(value.timeLimit)) || Date.parse(value.timeLimit) <= now) {
    return false;
  }
  return {
    purpose: 'team-invitation', id: value.id, orgId: value.orgId,
    email: normalizeInvitationEmail(value.email), role: value.role, timeLimit: value.timeLimit,
  };
}
