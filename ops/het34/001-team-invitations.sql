-- Additive, one-time migration. Preserve this ledger on application rollback.
-- Apply with psql -v ON_ERROR_STOP=1; never use broad prisma db push in production.
BEGIN;
CREATE TABLE "TeamInvitation" (
  "id" TEXT PRIMARY KEY,
  "organizationId" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "role" "Role" NOT NULL,
  "expiresAt" TIMESTAMP(3) NOT NULL,
  "consumedAt" TIMESTAMP(3),
  "consumedBy" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "TeamInvitation_organizationId_fkey" FOREIGN KEY ("organizationId")
    REFERENCES "Organization"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX "TeamInvitation_organizationId_email_idx"
  ON "TeamInvitation"("organizationId", "email");
COMMIT;
