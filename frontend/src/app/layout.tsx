import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Link from 'next/link';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'UKAEA Data',
  description: 'Advanced data access for fusion experiments',
};

import { Providers } from "@/components/providers";
import { UserMenu } from "@/components/user-menu";

// ... (imports)

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
            <nav className="glass sticky top-0 z-50 border-b border-white/10">
              <div className="container mx-auto h-32 flex items-center justify-between gap-4">
                <div className="flex items-center gap-8">
                  <Link href="/" className="flex flex-col md:flex-row items-center md:gap-4 text-white hover:text-primary transition-colors group">
                    {/* Logo Image: Larger square logo (h-24) for clear visibility */}
                    <div className="relative h-16 w-16 md:h-24 md:w-24">
                      <img
                        src="/Authority_WHITE_SML_AW.png"
                        alt="UKAEA Logo"
                        className="object-contain h-full w-full"
                      />
                    </div>

                    {/* Text: Larger and clearer */}
                    <span className="text-xs md:text-3xl font-bold tracking-tight mt-1 md:mt-0">UKAEA Data</span>
                  </Link>
                  <div className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-300">
                    <Link href="/devices" className="hover:text-primary transition-colors">
                      Devices
                    </Link>
                    <Link href="/datasets" className="hover:text-primary transition-colors">
                      Datasets
                    </Link>
                    <Link href="/sources" className="hover:text-primary transition-colors">
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

            <footer className="border-t border-white/10 py-8 mt-auto bg-slate-900/50">
              <div className="container mx-auto text-center text-sm text-slate-500">
                &copy; {new Date().getFullYear()} UK Atomic Energy Authority. Powered by the Fusion Data Service.
              </div>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
