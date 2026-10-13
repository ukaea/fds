import { SimulationBrowser } from '@/components/simulation-browser';

export default function SimulationsPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">Simulations</h1>
        <p className="text-muted-foreground max-w-2xl">
          Runs of simulation codes and the data they produced, whether they modelled a shot or
          predicted one that has not happened. Filter by the code that ran, the device, or what a
          run says it simulated.
        </p>
      </div>
      <SimulationBrowser />
    </div>
  );
}
