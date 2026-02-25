/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // API proxying is now handled by API Route Handlers in app/api/v1/[...path]/route.ts
  // Trigger rebuild
};

export default nextConfig;
