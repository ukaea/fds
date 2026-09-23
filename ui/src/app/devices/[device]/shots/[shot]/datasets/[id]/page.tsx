import DatasetDetail from '@/components/detail/dataset-detail';

type Params = { params: Promise<{ id: string }> };

export default async function DatasetInShotPage({ params }: Params) {
  const { id } = await params;
  return <DatasetDetail id={id} />;
}
