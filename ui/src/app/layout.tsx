import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Link from 'next/link';
import { Providers } from "@/components/providers";
import { UserMenu } from "@/components/user-menu";

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Fusion Data Service',
  description: 'Default UI for the Fusion Data Service',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          <div className="min-h-screen flex flex-col">
            <nav className="glass sticky top-0 z-50 border-b border-border">
              <div className="container mx-auto h-16 flex items-center justify-between gap-4">
                <div className="flex items-center gap-8">
                  <Link href="/" className="text-foreground hover:text-muted-foreground transition-colors">
                    <span className="text-lg font-bold tracking-tight">Fusion Data Service</span>
                  </Link>
                  <div className="hidden md:flex items-center gap-8 text-sm font-medium text-muted-foreground">
                    <Link href="/devices" className="hover:text-foreground transition-colors">
                      Devices
                    </Link>
                    <Link href="/datasets" className="hover:text-foreground transition-colors">
                      Datasets
                    </Link>
                    <Link href="/collections" className="hover:text-foreground transition-colors">
                      Collections
                    </Link>
                    <Link href="/sources" className="hover:text-foreground transition-colors">
                      Data Sources
                    </Link>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <UserMenu />
                </div>
              </div>
            </nav>

            <main className="flex-1 py-8">
               {children}
            </main>

            <footer className="border-t border-border py-8 mt-auto">
              <div className="container mx-auto text-center text-sm text-muted-foreground">
                Fusion Data Service
              </div>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
