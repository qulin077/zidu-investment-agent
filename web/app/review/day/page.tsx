import { ReviewTodayClient } from "../ui";

export const dynamic = "force-dynamic";

export default async function ReviewDayPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const { date } = await searchParams;
  return <ReviewTodayClient initialDate={date || ""} />;
}
