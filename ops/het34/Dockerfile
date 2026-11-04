FROM ghcr.io/gitroomhq/postiz-app@sha256:1e376ff2cb781022d528f171719cf174cf693a985a30cb40eefb13eae3ddda13
COPY apps/backend/src/api/routes/auth.controller.ts /app/apps/backend/src/api/routes/auth.controller.ts
COPY apps/backend/src/api/routes/users.controller.ts /app/apps/backend/src/api/routes/users.controller.ts
COPY apps/backend/src/services/auth/auth.service.ts /app/apps/backend/src/services/auth/auth.service.ts
COPY apps/frontend/src/proxy.ts /app/apps/frontend/src/proxy.ts
COPY libraries/helpers/src/auth/team-invitation.ts /app/libraries/helpers/src/auth/team-invitation.ts
COPY libraries/nestjs-libraries/src/database/prisma/schema.prisma /app/libraries/nestjs-libraries/src/database/prisma/schema.prisma
COPY libraries/nestjs-libraries/src/database/prisma/organizations/organization.repository.ts /app/libraries/nestjs-libraries/src/database/prisma/organizations/organization.repository.ts
COPY libraries/nestjs-libraries/src/database/prisma/organizations/organization.service.ts /app/libraries/nestjs-libraries/src/database/prisma/organizations/organization.service.ts
COPY libraries/nestjs-libraries/src/dtos/settings/add.team.member.dto.ts /app/libraries/nestjs-libraries/src/dtos/settings/add.team.member.dto.ts
RUN pnpm exec prisma generate --schema libraries/nestjs-libraries/src/database/prisma/schema.prisma
RUN NODE_OPTIONS=--max-old-space-size=4096 pnpm run build:backend
RUN NODE_OPTIONS=--max-old-space-size=4096 pnpm run build:frontend
COPY ops/het34/invitations.test.cjs /app/ops/het34/invitations.test.cjs
