import { redirect } from 'next/navigation';

// The identifier of the catalogue of everything this FDS holds. Its devices are
// what it lists, so a person is sent to them; a client asking for JSON-LD gets
// the catalogue itself.
export default function CatalogPage() {
  redirect('/devices');
}
