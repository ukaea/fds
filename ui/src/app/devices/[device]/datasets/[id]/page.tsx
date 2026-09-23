import { redirect } from 'next/navigation';

type Params = { params: Promise<{ id: string }> };

// Kept for links made before datasets were addressed by their identifier.
export default async function DatasetUnderDevicePage({ params }: Params) {
  const { id } = await params;
  redirect(`/datasets/${id}`);
}
