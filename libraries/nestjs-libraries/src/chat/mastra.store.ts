import { PostgresStore } from '@mastra/pg';

const databaseUrl = process.env.DATABASE_URL!;
let schemaName: string;
try {
  schemaName = new URL(databaseUrl).searchParams.get('schema') ?? 'public';
} catch {
  throw new Error('DATABASE_URL must be a valid PostgreSQL URL');
}
if (!/^[a-z_][a-z0-9_]{0,62}$/.test(schemaName)) {
  throw new Error('DATABASE_URL schema must be a PostgreSQL identifier');
}

export const pStore = new PostgresStore({
  id: 'postiz-store',
  connectionString: databaseUrl,
  schemaName,
});
