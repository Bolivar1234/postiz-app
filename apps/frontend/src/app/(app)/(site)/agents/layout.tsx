import { Metadata } from 'next';
import { Agent } from '@gitroom/frontend/components/agents/agent';
export const metadata: Metadata = {
  title: 'Postiz - Agent',
  description: 'agents',
};
export default async function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  if (!process.env.OPENAI_API_KEY?.trim()) {
    return (
      <section
        role="status"
        className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center"
      >
        <h1 className="text-xl font-semibold">
          Built-in AI is not configured on this server.
        </h1>
        <p>
          You can continue using the calendar and media library. Ask your
          administrator to enable built-in AI.
        </p>
      </section>
    );
  }
  return <Agent>{children}</Agent>;
}
