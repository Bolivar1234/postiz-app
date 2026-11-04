FROM ghcr.io/gitroomhq/postiz-app@sha256:1e376ff2cb781022d528f171719cf174cf693a985a30cb40eefb13eae3ddda13
ENV MAIN_URL=https://socials.qwntik.com FRONTEND_URL=https://socials.qwntik.com \
    NEXT_PUBLIC_BACKEND_URL=https://socials.qwntik.com/api BACKEND_INTERNAL_URL=http://localhost:3000 \
    DISABLE_REGISTRATION=true
COPY apps/backend/src/api/routes/auth.controller.ts /app/apps/backend/src/api/routes/auth.controller.ts
COPY apps/backend/src/api/routes/users.controller.ts /app/apps/backend/src/api/routes/users.controller.ts
COPY apps/backend/src/services/auth/auth.service.ts /app/apps/backend/src/services/auth/auth.service.ts
COPY apps/frontend/src/proxy.ts /app/apps/frontend/src/proxy.ts
COPY apps/frontend/src/app/(app)/auth/page.tsx /app/apps/frontend/src/app/(app)/auth/page.tsx
COPY libraries/helpers/src/auth/team-invitation.ts /app/libraries/helpers/src/auth/team-invitation.ts
COPY libraries/nestjs-libraries/src/database/prisma/schema.prisma /app/libraries/nestjs-libraries/src/database/prisma/schema.prisma
COPY libraries/nestjs-libraries/src/database/prisma/organizations/organization.repository.ts /app/libraries/nestjs-libraries/src/database/prisma/organizations/organization.repository.ts
COPY libraries/nestjs-libraries/src/database/prisma/organizations/organization.service.ts /app/libraries/nestjs-libraries/src/database/prisma/organizations/organization.service.ts
COPY libraries/nestjs-libraries/src/dtos/settings/add.team.member.dto.ts /app/libraries/nestjs-libraries/src/dtos/settings/add.team.member.dto.ts
COPY libraries/nestjs-libraries/src/services/email.service.ts /app/libraries/nestjs-libraries/src/services/email.service.ts
COPY libraries/nestjs-libraries/src/database/prisma/notifications/notification.service.ts /app/libraries/nestjs-libraries/src/database/prisma/notifications/notification.service.ts
RUN pnpm exec prisma generate --schema libraries/nestjs-libraries/src/database/prisma/schema.prisma
RUN NODE_OPTIONS=--max-old-space-size=4096 pnpm run build:backend
RUN NODE_OPTIONS=--max-old-space-size=4096 pnpm run build:frontend
COPY ops/het34/invitations.test.cjs /app/ops/het34/invitations.test.cjs
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/Bolivar1234/postiz-app" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.qwntik.base.digest="sha256:1e376ff2cb781022d528f171719cf174cf693a985a30cb40eefb13eae3ddda13"
CMD ["sh", "-c", "nginx && pnpm -r --parallel --filter ./apps/backend --filter ./apps/frontend --filter ./apps/orchestrator run pm2 && pm2 logs"]
